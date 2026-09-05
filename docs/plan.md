# MewCode Plan

## 架构概览

单进程、分层架构，自上而下：

**CLI 入口层** — 解析命令行参数（`--config`、`--provider`），驱动配置加载，随后启动 TUI。

**配置层** — 读取 YAML 配置文件（`yaml.safe_load`），解析 `${ENV_VAR}` 引用，校验六个字段，产出 `ProviderConfig` 列表；负责启动时警告（如 openai 协议 + thinking: true）。

**Provider 层** — 协议抽象核心。定义统一接口 `Provider`（输入历史消息，输出流式事件流），内含两个实现：`AnthropicProvider`（Messages API + `/v1/messages`）与 `OpenAIProvider`（chat completions + `/v1/chat/completions`）。通过注册表按 `protocol` 字段选择实现，新增协议只需实现接口并注册。

**传输层（HTTP/SSE）** — 基于 httpx 的异步客户端与共享 SSE 帧解析器，两种协议共用；处理超时与网络错误分类。

**对话层（Session）** — 内存中的消息历史管理与请求构造；仅在流正常结束后把当前用户消息与完整助手消息追加进历史。

**TUI 层** — Textual 应用，三个界面：Provider 选择页（多配置且未指定时）、对话页（历史滚动区 + 输入框 + 流式渲染）、错误提示（内嵌于对话页）。思考内容暗色斜体渲染、回答正常渲染、截断提示醒目展示。

数据流：`Input 提交 → Session 构造请求 → Provider 发起 SSE → 增量事件驱动 TUI 逐字渲染 → 正常结束后历史落账 → 等待下一轮`。

## 核心数据结构

```python
# ---------- 配置 ----------
@dataclass(frozen=True)
class ProviderConfig:
    name: str          # 供应商标识名
    protocol: str      # "anthropic" | "openai"（加载时已校验）
    model: str
    base_url: str      # 服务根地址（已去掉末尾斜杠）
    api_key: str = field(repr=False)  # 已解析的环境变量值；repr 不显示，绝不打印/写盘
    thinking: bool     # 缺省 False
```

```python
# ---------- 会话消息（有序内容块） ----------
@dataclass
class ThinkingBlock:
    text: str                        # 思考文本（可为空字符串）
    signature: str | None = None     # 该块签名；无则序列化时省略字段，不写 null、不伪造

@dataclass
class TextBlock:
    text: str

ContentBlock = ThinkingBlock | TextBlock

@dataclass
class ChatMessage:
    role: str                        # "user" | "assistant"
    blocks: tuple[ContentBlock, ...] # 有序内容块，顺序与 API 返回一致；多个 thinking 块不合并，各自持有 signature
```

```python
# ---------- 流式事件 ----------
@dataclass
class ThinkingDelta:
    text: str          # 思考增量 → TUI 暗色斜体渲染

@dataclass
class TextDelta:
    text: str          # 回答增量 → TUI 正常渲染

@dataclass
class StreamDone:
    message: ChatMessage      # 完整助手消息（有序内容块），交回 Session 存历史
    truncated: bool = False   # True 表示因输出上限被截断 → TUI 显示截断提示

StreamEvent = ThinkingDelta | TextDelta | StreamDone
```

```python
# ---------- Provider 统一接口 ----------
class Provider(ABC):
    def __init__(self, config: ProviderConfig): ...

    @abstractmethod
    async def stream_chat(
        self, messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        """发送历史消息（含当前用户消息），流式产出事件。

        流正常结束（收到协议结束事件）时产出恰好一次 StreamDone 后返回；
        流内 error 事件、连接意外断开、超时、HTTP 错误一律抛 ProviderError，
        不得产出 StreamDone。
        """

    @abstractmethod
    async def aclose(self) -> None:
        """关闭底层 httpx AsyncClient；须在在途请求结束后调用。"""
```

```python
# ---------- 注册表 ----------
PROTOCOLS: dict[str, type[Provider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}
# 新增协议 = 实现 Provider + 在此注册一行
```

```python
# ---------- 共享 SSE 帧解析器 ----------
@dataclass
class SSEFrame:
    event: str | None    # event: 字段（无则 None）
    data: str            # 多行 data: 按 SSE 标准以 \n 连接合并

async def iter_sse(response: httpx.Response) -> AsyncIterator[SSEFrame]:
    """按 SSE 标准解析：识别 event/data 字段、合并多行 data、以空行分帧。

    只做帧级解析，不解 JSON；[DONE] 等协议级结束标记、JSON 解析、
    协议事件映射均在各 Provider 内部处理。
    """
```

## 模块设计

**模块 A：`config`（配置层）**

- **职责：** 用 `yaml.safe_load` 加载 YAML、校验六个字段、解析 `${ENV_VAR}`、base_url 去尾斜杠、openai+thinking 警告
- **对外接口：** `load_config(path) -> list[ProviderConfig]`（校验失败抛 `ConfigError`，信息指明具体配置项）
- **依赖：** 仅标准库 + PyYAML

**模块 B：`providers.base` + `providers.sse`（传输与抽象）**

- **职责：** Provider 抽象类（含 `aclose()`）、StreamEvent 类型、SSEFrame 与 `iter_sse` 帧解析器、`ProviderError`（携带面向用户的中文可读信息）
- **接口契约：** 流正常结束（收到协议结束事件）后，产出恰好一次 StreamDone 后返回；连接意外断开、超时、HTTP 错误、流内 error 事件一律抛 `ProviderError`，**不得视为成功**，不得产出 StreamDone
- **依赖：** httpx

**模块 C：`providers.anthropic`（Anthropic 协议）**

- **职责：** 构造 Messages API 请求（`POST {base_url}/v1/messages`，头 `x-api-key`、`anthropic-version: 2023-06-01`）；按服务与模型解析 thinking 请求参数（见技术决策）；把 SSE 帧映射为 ThinkingDelta/TextDelta（`content_block_delta` 中的 `thinking_delta`/`text_delta`）；从 `content_block_delta` 的 `signature_delta` 收集思考块 signature；流内 `error` 事件 → ProviderError；收到 `message_stop` 后产出 StreamDone；`stop_reason == "max_tokens"` 时标记 `truncated=True`
- **序列化：** assistant 历史消息 → content 数组，按 `blocks` 顺序逐个序列化：ThinkingBlock → `thinking` 块（signature 为 None 时省略该字段；空文本 + 有 signature 的块照常保留），TextBlock → `text` 块；多个 thinking 块不合并，各自按序输出；user 消息 → text
- **thinking 参数解析：** 按 base_url 主机名区分服务，thinking: true / false 分别按映射表（见技术决策）构造参数；模型不在清单内或配置无法满足 → 按映射表明确报错或启动警告，不静默发送
- **依赖：** base + sse

**模块 D：`providers.openai`（OpenAI 协议）**

- **职责：** 构造 chat completions 请求（`POST {base_url}/v1/chat/completions`，头 `Authorization: Bearer`）；流式解析 chunk：`delta.content` → TextDelta，`delta.reasoning_content`（DeepSeek 兼容服务）→ ThinkingDelta；`data: [DONE]` 为结束标记，产出 StreamDone（`finish_reason == "length"` 时 `truncated=True`）；`[DONE]` 前连接断开 → ProviderError
- **序列化：** 消息 → `{"role", "content"}`，content 拼接全部 TextBlock 文本，忽略 ThinkingBlock
- **依赖：** base + sse

**模块 E：`session`（对话层）**

- **职责：** 持有消息历史；`build_request(user_msg)` 返回「历史 + 当前用户消息」快照（当前消息只出现一次）；`commit(user_msg, done_msg)` 仅在收到 StreamDone 后调用，把两者追加进历史；失败或中断不追加，历史保持可重试状态
- **依赖：** base（仅类型）

**模块 F：`ui.app` / `ui.chat` / `ui.picker`（TUI 层）**

- **职责：** Textual App 组装。启动流程：`--provider` 指定 → 校验存在 → 实例化；单配置且未指定 → 直接用唯一配置实例化；多配置且未指定 → ProviderPicker 选择页，**用户选定后才实例化对应 Provider**。ChatScreen 对话页——滚动历史区 + 单行 Input，提交后创建异步任务消费 Provider 事件流：ThinkingDelta 暗色斜体渲染（前缀「💭」），TextDelta 正常渲染，`StreamDone.truncated` 时在回答后显示「⚠ 回答达到输出上限，已截断」，流结束后定格；错误以红色信息行显示，不崩溃
- **并发控制：** 生成期间 Input 置为 disabled，**禁止重复提交**，确保同一时刻至多一个在途请求；生成结束（成功或失败）后在 finally 中恢复 Input 并重新聚焦（应用退出时除外）
- **退出清理：** 退出时（含 `/exit`、Ctrl+C、Ctrl+D）取消在途异步任务、await 等待任务结束后调用 `provider.aclose()`，再结束 App
- **依赖：** session + providers

**模块 G：`cli`（入口层）**

- **职责：** argparse（`--config` 默认 `~/.mewcode/config.yaml`、`--provider`）；加载校验；把解析好的 ProviderConfig 列表传给 App（Provider 的实例化发生在 App 内选定配置之后，见模块 F）
- **依赖：** config + ui

## 模块交互

**启动流**

```
cli 解析参数
  → config.load_config(path)          # 校验 + ${ENV_VAR} 解析 + 警告
  → ui.App(configs, selected_name)
       ├─ --provider 指定     → 名字存在校验 → 实例化对应 Provider
       ├─ 单配置且未指定       → 直接用唯一配置实例化
       └─ 多配置且未指定       → PickerScreen 交互选择 → 用户选定后实例化
  → ChatScreen 进入对话循环
```

**对话轮次流**（每轮请求）

```
Input.Submitted (ChatScreen)
  → Input disabled                            # 生成期间禁止重复提交
  → messages = session.build_request(user_msg)  # 历史快照 + 当前用户消息
  → provider.stream_chat(messages)            # 异步任务
      → httpx POST {base_url}/v1/... (SSE)
      → iter_sse 产帧 → 协议事件映射
      → ThinkingDelta ──→ TUI 暗色斜体渲染（💭 前缀）
      → TextDelta     ──→ TUI 正常渲染
      → 流内 error 事件 / 网络断开 / HTTP 错误 ──→ ProviderError（不产出 StreamDone）
  → 收到协议结束事件 → StreamDone(message, truncated)
      → truncated=True ──→ TUI 显示「⚠ 回答达到输出上限，已截断」
      → session.commit(user_msg, done_msg)    # 仅此时追加历史
  → finally（非退出时）→ Input 恢复并重新聚焦
  → ProviderError → 红色错误行显示，不 commit
```

**退出流**

```
/exit 命令 | Ctrl+C | Ctrl+D
  → 取消在途异步任务 → await 等待任务结束 → provider.aclose() → App 退出
```

## 文件组织

```
mewcode/
├── pyproject.toml          — 元数据；运行时依赖 textual/httpx/PyYAML；
│                             开发依赖（optional-dependencies.dev）pytest/pytest-asyncio；
│                             console script `mewcode`
├── README.md               — 安装（venv + pip）、配置说明（六字段、${ENV_VAR} 密钥引用）、
│                             启动方式（--config / --provider / 交互选择）
├── config.example.yaml     — 配置示例（DeepSeek anthropic 兼容接口，api_key 用 ${DEEPSEEK_API_KEY}）
├── mewcode/
│   ├── __init__.py
│   ├── __main__.py         — `python -m mewcode` 入口
│   ├── cli.py              — 模块 G：argparse、main()
│   ├── config.py           — 模块 A：ProviderConfig、load_config、ConfigError
│   ├── session.py          — 模块 E：Session（build_request/commit）
│   ├── providers/
│   │   ├── __init__.py     — PROTOCOLS 注册表
│   │   ├── base.py         — 模块 B：Provider、StreamEvent 类型、ProviderError
│   │   ├── sse.py          — 模块 B：SSEFrame、iter_sse
│   │   ├── anthropic.py    — 模块 C：AnthropicProvider
│   │   └── openai.py       — 模块 D：OpenAIProvider
│   └── ui/
│       ├── __init__.py
│       ├── app.py          — 模块 F：MewCodeApp（Provider 实例化时机、退出清理）
│       ├── chat.py         — 模块 F：ChatScreen（历史区、Input、流式渲染、并发控制）
│       └── picker.py       — 模块 F：ProviderPickerScreen
├── tests/
│   ├── test_config.py      — 配置解析 / 校验 / ${ENV_VAR} / 警告
│   ├── test_sse.py         — SSE 帧解析（多行 data、event 字段、分帧边界）
│   ├── test_providers.py   — 两 provider 的请求构造、thinking 参数映射、事件映射、多块序列化（mock HTTP）
│   └── test_session.py     — build_request / commit / 失败不追加
└── docs/
    ├── spec.md
    ├── plan.md
    ├── task.md
    └── checklist.md
```

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 运行时与包管理 | Python 3.12 + pip + venv | 本机已装 3.12.10、无 uv；pyproject.toml 声明依赖 |
| 依赖划分 | 运行时：textual / httpx / PyYAML；开发（dev extras）：pytest / pytest-asyncio | 测试依赖不进运行环境 |
| API 调用方式 | 统一 raw HTTP（httpx），不用官方 SDK | 已选定；F4 统一接口、N4 依赖最小、DeepSeek 兼容端点的差异可控 |
| TUI 框架 | Textual | 异步架构与 SSE 流式天然契合；Input / 滚动区组件齐全；支持 Ctrl+C/Ctrl+D 绑定 |
| YAML 解析 | PyYAML + `yaml.safe_load` | 安全加载，杜绝任意对象构造 |
| SSE 解析 | 自研帧级解析器 `iter_sse`（只分帧），JSON 解析与事件映射留在各 Provider | 帧级逻辑两协议共用；`[DONE]`、`error` 事件等协议差异留在 Provider 层 |
| thinking 参数构造 | 按 base_url 主机 + 模型查表构造，绝不统一猜测 | 见下表 |
| 未知 thinking 组合 | 构造器内明确报错（ConfigError 语义的 ProviderError），不静默发送 | 不发送未经验证的请求 |
| thinking 历史回传 | assistant 消息按有序内容块回传，每个 thinking 块携带各自 signature；signature 为 None 时省略该字段，不写 null、不伪造；空文本 + 有 signature 的块保留 | Anthropic 语义要求；DeepSeek 兼容接口支持 thinking 块条目 |
| openai 协议历史 | 只存 text，不回传 reasoning | DeepSeek 官方文档明确 reasoning_content 会被 API 忽略 |
| max_tokens | 默认 8192（Provider 常量），可被输出上限截断 | 纯对话通常足够；截断有 UI 提示兜底 |
| 截断提示 | `stop_reason == "max_tokens"`（anthropic）/ `finish_reason == "length"`（openai）→ `truncated=True` → TUI 显示「⚠ 回答达到输出上限，已截断」 | 8192 是上限，不保证完整 |
| 超时 | 连接 30s / 读 120s | N3；thinking 期间容忍长静默，120s 无数据判超时 |
| 错误分类 | 401→认证失败、429→限流、5xx→服务错误、连接异常→网络错误，均映射为中文可读 ProviderError | N2 健壮性 |
| 密钥保护 | api_key 字段 `repr=False`；只进请求头，不进日志/界面/错误信息 | N6 |
| 历史追加语义 | 仅在 StreamDone 后 `commit(user_msg, done_msg)` | 失败或中断不追加，可重试 |
| 并发控制 | 生成期间 Input disabled，同一时刻至多一个在途请求 | 避免并发请求打乱历史 |
| Provider 实例化时机 | 用户选定配置后实例化（单配置直接实例化） | 避免无用连接 |
| 退出清理 | 取消在途任务 → await 任务结束 → `provider.aclose()`；Input 恢复置于 finally（退出时除外） | 无泄漏退出 |
| 文档 | README.md：安装、配置、密钥环境变量、启动方式 | 开箱可用 |

### thinking 参数映射表（anthropic 协议）

按 base_url 主机名识别服务；模型按**精确字符串**匹配清单，不在清单内 → 构造器明确报错。

**thinking: true**

| 服务 | 支持模型清单（精确匹配） | thinking 请求参数 |
|------|------------------------|------------------|
| DeepSeek（`api.deepseek.com`） | `deepseek-v4-pro`、`deepseek-v4-pro[1m]`、`deepseek-v4-flash` | `{"type": "enabled"}`（官方文档确认支持；budget_tokens 被忽略，不发送） |
| 官方 Claude（`api.anthropic.com`） | `claude-fable-5-1`、`claude-mythos-5-1`、`claude-fable-5`、`claude-opus-5`、`claude-opus-4-8`、`claude-opus-4-7`、`claude-opus-4-6`、`claude-sonnet-5`、`claude-sonnet-4-6` | `{"type": "adaptive", "display": "summarized"}`（display 保证思考内容可见） |
| 官方 Claude（`api.anthropic.com`） | `claude-haiku-4-5`、`claude-opus-4-5`、`claude-sonnet-4-5`、`claude-3-7-sonnet`、`claude-3-5-sonnet`、`claude-3-5-haiku`、`claude-3-opus`、`claude-3-sonnet`、`claude-3-haiku` | `{"type": "enabled", "budget_tokens": 4096}`（需满足 1024 ≤ budget < max_tokens=8192） |
| 未知主机 / 不在清单内的模型 | — | 构造器明确报错，不静默发送 |

**thinking: false（省略 ≠ 关闭，按目标模型能力处理）**

| 服务 / 模型组 | thinking: false 行为 |
|--------------|---------------------|
| DeepSeek 清单内模型 | 请求不携带 thinking 字段（DeepSeek 默认无思考输出） |
| 官方 Claude 默认开启组：`claude-opus-5`、`claude-opus-4-8`、`claude-opus-4-7`、`claude-sonnet-5` | 发送 `{"type": "disabled"}`（这些模型支持显式关闭） |
| 官方 Claude 默认开启且不可关闭：`claude-fable-5-1`、`claude-mythos-5-1`、`claude-fable-5` | 显式 disabled 返回 400 → 无法满足配置 → **启动时明确警告**「该模型默认启用思考且不支持关闭，思考输出仍会显示」 |
| 官方 Claude 默认关闭组：`claude-opus-4-6`、`claude-sonnet-4-6` 及 legacy 清单 | 请求不携带 thinking 字段（默认无思考输出） |
| 未知主机 / 不在清单内的模型 | 不携带 thinking 字段，正常对话（thinking: false 不要求模型在清单内） |

映射表为代码内常量；新模型/新服务支持 = 更新映射表（属于「协议知识变更」，符合 N5 的定义）。

### thinking 相关测试要求

- thinking: true × 清单内模型 → 参数形状逐一断言（adaptive 含 display；enabled 含 budget 且 1024 ≤ budget < max_tokens）
- 未知模型 / 未知主机 + thinking: true → 构造器报错
- thinking: false × 各行为组 → 参数 / 省略正确；不可关闭组 → 启动警告
- 多 thinking 块 + 各自 signature 的有序序列化；空文本 + signature 的块保留
- `aclose()` 幂等，关闭后不再发起请求
