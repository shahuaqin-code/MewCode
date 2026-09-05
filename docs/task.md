# MewCode Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `pyproject.toml` | 元数据、运行时/开发依赖、console script `mewcode` |
| 新建 | `README.md` | 安装、配置、密钥环境变量、启动方式 |
| 新建 | `config.example.yaml` | DeepSeek anthropic 兼容接口示例 |
| 新建 | `mewcode/__init__.py` | 包初始化 |
| 新建 | `mewcode/__main__.py` | `python -m mewcode` 入口 |
| 新建 | `mewcode/cli.py` | argparse、main() |
| 新建 | `mewcode/config.py` | ProviderConfig、load_config、ConfigError |
| 新建 | `mewcode/session.py` | Session |
| 新建 | `mewcode/providers/__init__.py` | PROTOCOLS 注册表 |
| 新建 | `mewcode/providers/base.py` | Provider、StreamEvent、ProviderError |
| 新建 | `mewcode/providers/sse.py` | SSEFrame、iter_sse |
| 新建 | `mewcode/providers/anthropic.py` | AnthropicProvider |
| 新建 | `mewcode/providers/openai.py` | OpenAIProvider |
| 新建 | `mewcode/ui/__init__.py` | 包初始化 |
| 新建 | `mewcode/ui/app.py` | MewCodeApp |
| 新建 | `mewcode/ui/chat.py` | ChatScreen |
| 新建 | `mewcode/ui/picker.py` | ProviderPickerScreen |
| 新建 | `tests/__init__.py` | 测试包 |
| 新建 | `tests/test_config.py` | 配置测试 |
| 新建 | `tests/test_sse.py` | SSE 帧解析测试 |
| 新建 | `tests/test_providers.py` | provider 测试 |
| 新建 | `tests/test_session.py` | session 测试 |

## T1: 项目脚手架

**文件：** `pyproject.toml`、`mewcode/__init__.py`、`mewcode/__main__.py`、`mewcode/ui/__init__.py`、`mewcode/providers/__init__.py`、`tests/__init__.py`
**依赖：** 无
**步骤：**
1. `pyproject.toml`：name=mewcode、requires-python>=3.12；dependencies = textual/httpx/PyYAML；`[project.optional-dependencies] dev = pytest, pytest-asyncio`；`[project.scripts] mewcode = "mewcode.cli:main"`
2. 创建 venv 并安装：`python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
3. `mewcode/__main__.py`：调用 `cli.main()`
4. 其余 `__init__.py` 建空文件（`providers/__init__.py` 暂空，T8 填注册表）
**验证：** `.venv/bin/python -c "import mewcode"` 无报错；`.venv/bin/pip list` 含 textual/httpx/PyYAML/pytest

## T2: 配置层

**文件：** `mewcode/config.py`
**依赖：** T1
**步骤：**
1. 定义 `ProviderConfig`（frozen dataclass；`api_key` 字段 `repr=False`）
2. 定义 `ConfigError`（信息指明具体配置项）
3. `load_config(path)`：`yaml.safe_load` → 校验必填字段（name/protocol/model/base_url/api_key）、protocol 取值、`thinking` 缺省 False、base_url 去尾斜杠
4. `${ENV_VAR}` 解析：字段以 `${` 开头且以 `}` 结尾时取环境变量值；环境变量未设置 → `ConfigError` 指明配置项
5. openai 协议 + thinking: true → 打印警告并忽略
**验证：** 用一份临时 YAML（含 ${ENV_VAR}）跑 `load_config`，字段正确；`repr(config)` 不含 api_key

## T3: Provider 抽象与事件类型

**文件：** `mewcode/providers/base.py`
**依赖：** T1
**步骤：**
1. 定义 `ThinkingDelta`、`TextDelta`、`StreamDone`（含 `truncated`）与联合类型 `StreamEvent`
2. 定义 `ThinkingBlock`（text、signature 可选）、`TextBlock`、`ContentBlock`、`ChatMessage`（有序 `blocks` 元组）
3. 定义 `Provider` ABC：`__init__(config)`、`stream_chat(messages) -> AsyncIterator[StreamEvent]`、`aclose()`
4. 定义 `ProviderError`（面向用户的中文可读信息）
**验证：** `.venv/bin/python -m py_compile mewcode/providers/base.py` 通过

## T4: SSE 帧解析器

**文件：** `mewcode/providers/sse.py`
**依赖：** T1
**步骤：**
1. 定义 `SSEFrame`（event、data）
2. `iter_sse(response)`：按行读取；解析 `event:`/`data:` 字段；多行 data 以 `\n` 连接；空行分帧产出 SSEFrame；只分帧，不做 JSON 解析
**验证：** 手写一个 SSE 字节流（多行 data、无 event 帧、含 `data: [DONE]`、末尾无空行），遍历输出帧序列正确

## T5: SSE 测试

**文件：** `tests/test_sse.py`
**依赖：** T4
**步骤：**
1. 用 mock 的 httpx.Response（`iter_bytes` 返回分块 SSE 字节）构造输入
2. 断言：多行 data 合并、event 字段提取、空行分帧、`data: [DONE]` 仍作为普通帧产出、末尾无换行也能产出最后一帧
**验证：** `.venv/bin/pytest tests/test_sse.py` 全绿

## T6: AnthropicProvider

**文件：** `mewcode/providers/anthropic.py`
**依赖：** T3、T4
**步骤：**
1. 构造器：按 base_url 主机名识别服务；按 plan 的 thinking 映射表校验——thinking: true 且模型不在清单 / 未知主机 → `ProviderError`；thinking: false 且模型在不可关闭组 → 打印启动警告
2. `stream_chat`：`POST {base_url}/v1/messages`；头 `x-api-key`、`anthropic-version: 2023-06-01`、`content-type: application/json`；body：model、max_tokens=8192、stream=true、messages 序列化（blocks 有序：thinking 块含 signature〔None 则省略该字段〕、text 块）、thinking 参数按映射表（含 disabled / 省略两种 false 行为）
3. SSE 事件映射：`content_block_delta` 的 `thinking_delta` → ThinkingDelta；`text_delta` → TextDelta；`signature_delta` → 当前块 signature；流内 `error` 事件 → ProviderError
4. `content_block_stop` 按序落块；`message_delta` 收 stop_reason；`message_stop` → 产出 StreamDone（`truncated = stop_reason == "max_tokens"`）后返回
5. HTTP 错误分类：401→认证失败、429→限流、5xx→服务错误、连接异常→网络错误，抛中文可读 ProviderError；`aclose()` 关闭 AsyncClient
**验证：** 用 mock 的 SSE 事件序列跑 `stream_chat`，断言事件顺序、StreamDone 内容与 truncated 标记

## T7: OpenAIProvider

**文件：** `mewcode/providers/openai.py`
**依赖：** T3、T4
**步骤：**
1. `stream_chat`：`POST {base_url}/v1/chat/completions`；头 `Authorization: Bearer`；body：model、stream=true、messages（content 拼接全部 TextBlock，忽略 ThinkingBlock）
2. chunk 解析：`delta.content` → TextDelta；`delta.reasoning_content` → ThinkingDelta；`finish_reason == "length"` 记 truncated
3. `data: [DONE]` → 产出 StreamDone 后返回；[DONE] 前断流 → ProviderError
4. HTTP 错误分类同 T6；`aclose()` 关闭 AsyncClient
**验证：** 用 mock 的 chunk 序列跑 `stream_chat`，断言事件顺序、StreamDone 内容与 truncated 标记

## T8: 注册表

**文件：** `mewcode/providers/__init__.py`
**依赖：** T6、T7
**步骤：**
1. `PROTOCOLS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider}`
**验证：** `.venv/bin/python -c "from mewcode.providers import PROTOCOLS; print(PROTOCOLS.keys())"`

## T9: provider 测试

**文件：** `tests/test_providers.py`
**依赖：** T6、T7、T8
**步骤：**
1. thinking: true × 清单内各模型 → 请求体 thinking 参数形状逐一断言（adaptive 含 display；enabled 含 budget 且 1024 ≤ budget < 8192；deepseek 不含 budget_tokens）
2. 未知模型 / 未知主机 + thinking: true → 构造器 ProviderError
3. thinking: false × 各行为组 → disabled / 省略正确；不可关闭组 → 启动警告
4. 多 thinking 块 + 各自 signature 的有序序列化；空文本 + signature 的块保留；signature 为 None 时字段省略
5. `data: [DONE]` 缺失 / 流中断 → ProviderError 且不产出 StreamDone；`aclose()` 幂等
**验证：** `.venv/bin/pytest tests/test_providers.py` 全绿（mock HTTP，不真实联网）

## T10: Session

**文件：** `mewcode/session.py`
**依赖：** T3
**步骤：**
1. `Session`：内部 `messages` 列表；`build_request(user_msg)` 返回「历史 + `ChatMessage(role=user, blocks=[TextBlock(user_msg)])`」快照，当前消息只出现一次
2. `commit(user_msg, done_msg)`：仅成功后调用，把两者追加进历史
**验证：** 脚本模拟：请求前历史不含当前消息；commit 后含用户+助手消息且顺序正确；不 commit 历史不变

## T11: session 测试

**文件：** `tests/test_session.py`
**依赖：** T10
**步骤：**
1. `build_request` 当前消息只出现一次；`commit` 后追加两者；不 commit 历史不变；多轮顺序正确
**验证：** `.venv/bin/pytest tests/test_session.py` 全绿

## T12: ChatScreen

**文件：** `mewcode/ui/chat.py`
**依赖：** T3、T6、T7、T10
**步骤：**
1. 布局：VerticalScroll 历史区 + 底部单行 Input；CSS：thinking 暗色斜体（💭 前缀）、错误行红色、截断提示黄色
2. `Input.Submitted`：清空输入 → 历史区挂载用户消息 → Input 置 disabled → 异步任务执行 `session.build_request(user_msg)` + `provider.stream_chat(messages)`
3. 事件渲染：ThinkingDelta 暗色斜体追加；TextDelta 正常追加；StreamDone 定格 + `truncated` 时显示「⚠ 回答达到输出上限，已截断」+ `session.commit(user_msg, done_msg)`
4. ProviderError → 红色错误行显示，不 commit
5. finally（非退出）→ Input 恢复并重新聚焦
6. `/exit` 命令、Ctrl+C、Ctrl+D 绑定退出
**验证：** 注入 FakeProvider（产出 ThinkingDelta/TextDelta/StreamDone）用 `app.run_test()` 冒烟，确认三态渲染与禁用/恢复调用路径正确

## T13: ProviderPickerScreen

**文件：** `mewcode/ui/picker.py`
**依赖：** T1
**步骤：**
1. SelectionList 展示 configs（name + model）；回车选定后返回选中 ProviderConfig
**验证：** `run_test()` 冒烟：选择项回调收到正确 config

## T14: MewCodeApp

**文件：** `mewcode/ui/app.py`
**依赖：** T12、T13、T8
**步骤：**
1. 构造：接收 configs + selected_name；选择逻辑——指定名 → 校验存在（不存在报错退出）；单配置且未指定 → 直接用；多配置且未指定 → push PickerScreen
2. 选定后才实例化对应 Provider；实例化报错（thinking 映射）→ 显示错误并退出
3. 退出流程：取消在途任务 → await 任务结束 → `provider.aclose()` → App 退出
**验证：** 单配置 run_test 冒烟通过；多配置流程走 PickerScreen

## T15: CLI 入口

**文件：** `mewcode/cli.py`
**依赖：** T2、T14
**步骤：**
1. argparse：`--config`（默认 `~/.mewcode/config.yaml`）、`--provider`（可选）
2. `main()`：`load_config`（ConfigError → stderr 可读报错、退出码 1）→ `MewCodeApp(configs, provider_name).run()`
**验证：** `--config 不存在的文件` 报错退出码 1；`--provider 不存在的名字` 报错退出码 1

## T16: 配置测试

**文件：** `tests/test_config.py`
**依赖：** T2
**步骤：**
1. 六字段解析、thinking 缺省 False、缺字段 / 非法 protocol / 坏 YAML → ConfigError 且指明配置项
2. `${ENV_VAR}` 解析成功；引用未设置的环境变量 → ConfigError
3. openai + thinking: true → 警告
4. `repr(config)` 不含 api_key
**验证：** `.venv/bin/pytest tests/test_config.py` 全绿

## T17: 示例配置与 README

**文件：** `config.example.yaml`、`README.md`
**依赖：** T2
**步骤：**
1. `config.example.yaml`：DeepSeek anthropic 配置——name/protocol: anthropic/model: deepseek-v4-pro/base_url: https://api.deepseek.com/anthropic/api_key: ${DEEPSEEK_API_KEY}/thinking: true
2. `README.md`：安装（venv + `pip install -e ".[dev]"`）、六字段配置说明、密钥用 `${ENV_VAR}` 环境变量、启动方式（`--config` / `--provider` / 交互选择）、退出方式（/exit、Ctrl+C、Ctrl+D）
**验证：** 通读 README 按步骤执行命令均无语法错误；`config.example.yaml` 可被 `load_config` 解析（环境变量存在时）

## 执行顺序

```
T1 ──→ T2 ──→ T16
 │      └──→ T17（可与 T16 并行）
 ├─→ T3 ──→ T10 ──→ T11
 │      └──→ T6 ──┐
 ├─→ T4 ──→ T5    ├─→ T8 ──→ T9
 │      └──→ T7 ──┘
 │
 └─→ T13 ──┐
T10/T6/T7 ──→ T12 ──→ T14 ──→ T15
```

- T2、T3、T4、T13 在 T1 后即可并行
- T6 依赖 T3+T4；T7 依赖 T3+T4；T8 依赖 T6+T7；T9 依赖 T8
- T10 依赖 T3；T12 依赖 T3+T6+T7+T10；T14 依赖 T12+T13+T8；T15 依赖 T2+T14
