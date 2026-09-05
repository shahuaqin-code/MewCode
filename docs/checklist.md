# 多协议 LLM 终端对话客户端 Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为；括号内为验证方式。

## 实现完整性
- [x] 配置加载：合法 `.mewcode/config.yaml` 能解析出 providers 列表（验证：单测 + 启动进入对话）。(AC1/F1)
- [x] 配置校验：缺密钥/非法 protocol/文件缺失时给出可读错误并非零退出，无未捕获堆栈（验证：删字段/改 protocol/删文件分别运行 `python -m mewcode`）。(AC1/N4)
- [x] 单 provider 直进：仅一条配置时启动直接进入对话（验证：单条配置运行）。(AC2/F2)
- [x] 多 provider 选择：多条配置时出现方向键 `OptionList`，选定后进入对话（验证：两条配置运行、上下选择 + Enter）。(AC2/F2)
- [x] 内置 system prompt 与历史随请求发送（验证：问"你的角色/规则"，回答体现内置 prompt；多轮见 AC6）。(AC4/F4)
- [x] thinking：anthropic 配 `thinking: true` 时启用，且界面不出现任何思考文本（验证：开启后观察仅最终回复）。(AC5/F5)
- [x] 流式逐字：回复以纯文本逐字出现（验证：长回复肉眼可见逐步输出）。(AC5/F8)
- [x] markdown 定型：回复结束后整段以 markdown 渲染（代码块/列表/强调正确）（验证：让模型输出含代码块与列表的内容）。(AC8/F8)
- [x] 多行输入：Alt+Enter 换行、Enter 提交、提交后输入框清空（验证：输入两行后提交）。(AC9/F9)
- [x] 响应计时：自提交即显示 `Imagining… (Ns)` 且秒数递增，结束后显示总耗时（验证：发一条慢回复观察）。(AC12/F12)
- [x] 错误反馈：错误 key/不存在模型时，错误在对话区可区分样式（红色）显示且不退出（验证：改坏 key 运行后再正常发一条）。(AC11/F11)
- [x] 退出：`/exit` 与 Ctrl+C 均能安全退出，终端恢复正常（验证：两种方式各试一次，观察无残留/错乱）。(AC10/F10/N7)
- [x] 界面布局：启动含猫 banner + 名称版本 + cwd + 就绪提示行 + 输入框（含 `❯` 与占位符）+ 状态栏（左 name 右 model）（验证：启动截图比对）。(AC7/F7)

## 集成
- [x] TUI 通过统一 `Provider` Protocol 驱动两种协议，切换协议不改变上层交互（验证：分别用 anthropic / openai 配置跑同一组对话，行为一致）。(AC3/N3)
- [x] 多轮上下文携带：先告知信息、后追问，模型能正确引用前文；退出再启动后历史为空（验证：两轮对话 + 重启验证）。(AC6/F6)
- [x] 流式不阻塞：等待/流式期间界面仍响应、不冻结（验证：长回复期间界面持续刷新；asyncio event loop 不阻塞）。(AC13/N1)
- [ ] scrollback 渲染（Claude Code 风格）：完成的消息（用户输入/助手回复/错误）追加到 `RichLog`，可用终端原生滚轮/Textual 滚动回看，退出后内容保留在终端历史中；动态区仅含输入框 + 正在流式的回复 + 状态栏（验证：tmux 多轮后回滚查看历史 + 退出后历史仍在）。
- [x] base_url 覆盖：为某 provider 配自定义 `base_url`（兼容端点）可正常收发（验证：配一个兼容端点跑通一轮）。(F3)
- [x] 窗口自适应：缩放终端宽度后输入框/对话区/markdown 不错版（验证：运行中调整终端宽度）。(N6)

## 编译与测试
- [x] `python -m mewcode` 能正常启动（在合法配置下进入 TUI）。
- [x] `ruff check .` 无告警。
- [x] `ruff format --check .` 通过（或本地 `ruff format .` 已统一格式）。
- [x] `pytest` 通过（`tests/test_config.py`、`tests/test_conversation.py`）。
- [ ] （可选）`mypy src/mewcode` 通过（启用 strict 子集亦可）。
- [x] 密钥不回显/不打印：对话区与任何输出均不出现 `api_key`（验证：通读运行输出、检索无明文 key）。(N5)

## 端到端场景
- [ ] 场景 1（anthropic 多轮）：单条 anthropic 配置启动 → 连续两轮、第二轮引用第一轮 → 流式 + 计时 + markdown 定型 → `/exit` 退出。
- [ ] 场景 2（openai 流式）：openai 协议配置 → 发一条含代码块的请求 → 流式逐字后 markdown 渲染正确。
- [ ] 场景 3（多 provider 选择）：两条配置 → 启动出现列表 → 选第二条 → 状态栏显示其 name/model → 正常对话。
- [ ] 场景 4（错误恢复）：错误 key 触发失败 → 对话区红色错误、程序不退出 → 修正后（重启）继续正常对话。

## 本次重建验证记录（2026-09-05）

勾选项表示已通过对应自动化验证，不代表完成了条目中举例的真实 API 人工联调。

- `tests/test_config.py`：配置结构、字段、可选端点、布尔类型、YAML 错误脱敏、环境变量密钥引用与缺失校验。
- `tests/test_conversation.py`：历史顺序、副本隔离、失败回滚、重启空历史。
- `tests/test_providers.py`：真实官方 SDK + HTTP MockTransport；双协议自定义端点、系统提示词与完整历史、思考过滤、限流不重试、取消传播及客户端关闭。
- `tests/test_tui.py`：单项直进、多项方向键选择、Alt+Enter 多行、提交锁定、等待计时、Markdown 完成、错误恢复、35 列窄屏、退出清理；SVG 截图已检查。
- `tests/test_cli.py`：独立进程配置错误，以及 POSIX PTY 中 `/exit`、Ctrl+C 的正常退出码、终端属性恢复和密钥不泄露。
- `ruff check .`、`ruff format --check .`：通过；需求文档不参与代码格式化。

保留待验收：真实 Anthropic/OpenAI 服务的四个端到端场景、模型语义上引用前文、真实服务逐字观感，以及 tmux 原生历史人工检查。没有使用真实密钥发起请求。可选 mypy 未执行。

实现说明：RichLog 保存可重排的渲染块用于窄屏重排；退出后向终端重放内容以保留原生滚动历史，运行中通过 RichLog 回看。失败轮次显示在界面但从模型上下文回滚，保持成功历史的 user/assistant 交替。thinking 按 plan/task 仅对 Anthropic 生效。

### 后续修复：环境变量密钥与启动横幅

- api_key 支持 `${DEEPSEEK_API_KEY}` / `$DEEPSEEK_API_KEY`；缺失或空值启动报错，密钥值不回显。
- inline 屏幕使用终端可用高度，避免 RichLog 被自动高度布局压成一行；PTY 回归测试在发送退出按键之前确认猫咪和版本号已输出。
- 用户的环境变量要求覆盖初始文档中“不展开环境变量”的限制。
