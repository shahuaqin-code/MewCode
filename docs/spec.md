# MewCode Spec

## 背景

用户需要一个属于自己的命令行 AI 助手（MewCode，类 Claude Code），本阶段从零搭建第一个可运行版本：纯对话能力。当前无任何已有代码，Python 实现，单进程架构。

第一版优先验收 DeepSeek 官方 Anthropic 兼容接口：

| 配置项 | 值 |
|--------|-----|
| base_url | `https://api.deepseek.com/anthropic` |
| model | `deepseek-v4-pro` |
| api_key | `${DEEPSEEK_API_KEY}` 环境变量引用，不在 YAML 中保存明文 |

## 目标

- 用户在终端启动 MewCode，进入交互式对话界面（TUI），输入问题后 LLM 回复以流式逐字打印
- 支持多轮对话，同一会话内模型能记住之前说过的内容
- 支持 Anthropic 协议与 OpenAI 协议两种 API 后端，通过 YAML 配置切换；Anthropic 协议后端同时覆盖 Claude 官方接口与 DeepSeek 等 Anthropic 兼容接口
- Provider 层抽象为统一接口，新增后端只需实现接口，不改动对话逻辑
- 支持具备推理能力的 provider 的 thinking/reasoning 输出（首个实现以 DeepSeek V4 Pro 为准），思考内容以暗色样式实时展示

## 功能需求

- **F1 — 启动与配置加载**

  启动 `mewcode` 后加载 YAML 配置文件（默认 `~/.mewcode/config.yaml`，可用 `--config <path>` 覆盖）。配置含一个或多个 provider，每个 provider 六个字段：

  | 字段 | 必填 | 说明 |
  |------|------|------|
  | `name` | 是 | 供应商标识名，用于区分多个配置 |
  | `protocol` | 是 | 协议类型，取值 `anthropic` 或 `openai` |
  | `model` | 是 | 请求使用的模型名 |
  | `base_url` | 是 | 服务根地址（协议路径由程序统一追加，见 F5/F6） |
  | `api_key` | 是 | 认证密钥，支持 `${ENV_VAR}` 引用，启动时解析为环境变量值 |
  | `thinking` | 否 | 是否启用思考输出，默认 false |

  - 配置校验：`protocol` 取值非法、必填字段缺失、`api_key` 引用的环境变量未设置、YAML 格式错误等，均给出指明具体配置项的错误信息并退出
  - 多个 provider 时：`--provider <name>` 指定使用哪个；指定不存在的名字报错退出；未指定则进入 TUI 后交互选择

- **F2 — 交互式对话界面（TUI）**

  启动后进入交互式对话界面：用户输入问题、回车发送；LLM 回复以流式逐字打印，界面保留本次会话的全部历史；支持 `/exit` 命令、Ctrl+C、Ctrl+D 三种方式退出程序。

- **F3 — 多轮对话上下文**

  每次发送请求时，messages 为：之前已保存的历史消息 + 当前用户消息，当前消息在请求中只出现一次；收到完整回复后，再将助手回复追加到历史。模型可引用之前的内容作答。上下文仅保存在内存中，退出程序即丢弃。

- **F4 — 统一 Provider 接口**

  所有后端实现同一套抽象接口（发送消息、流式回调）。新增后端只需实现该接口并完成注册，TUI 与对话逻辑零改动。

- **F5 — Anthropic 协议后端**

  使用 Anthropic Messages API 通过 SSE 流式获取回复。`base_url` 为服务根地址，请求时统一追加 `/v1/messages`（处理末尾斜杠，避免路径重复）。同一后端覆盖两类地址：Anthropic 官方接口（`api.anthropic.com`）与 Anthropic 兼容接口（如 DeepSeek `https://api.deepseek.com/anthropic`）。**第一版优先验收 DeepSeek V4 Pro 通过此接口的完整对话流。**

- **F6 — OpenAI 协议后端**

  使用 OpenAI chat completions API 通过 SSE 流式获取回复。`base_url` 为服务根地址，请求时统一追加 `/v1/chat/completions`（处理末尾斜杠，避免路径重复）。

- **F7 — thinking/reasoning 输出**

  `protocol: anthropic` 且 `thinking: true` 时，请求启用思考输出；流式返回的思考内容以暗色样式实时展示，正式回答以正常样式展示。`protocol: openai` 且 `thinking: true` 时忽略该字段，启动时打印警告，对话照常进行。

## 非功能需求

- **N1 — 流式性：** 回复必须通过 SSE 流式获取，从首个 token 到达即开始显示，不允许等待完整回复生成后再统一输出。

- **N2 — 健壮性：** 网络错误、API 错误（如 401/429）、响应解析异常时，显示可读的错误信息，程序不崩溃，用户可继续对话或正常退出。

- **N3 — 超时处理：** 连接与请求设置有合理默认值的超时，超时给出明确提示。

- **N4 — 依赖最小化：** 仅使用 Python 实现所需的必要依赖，不引入重型框架或 agent 平台。

- **N5 — 配置驱动扩展：** 在已支持的 anthropic/openai 协议范围内，新增、删除、切换 provider 配置无需修改代码；新增一种全新协议仍需实现并注册 Provider 接口。

- **N6 — 密钥安全：** API Key 不得出现在日志、错误信息或界面输出中；配置示例优先使用 `${ENV_VAR}` 引用；任何需要显示密钥的场景只能脱敏显示；程序不得把解析后的密钥写回 YAML 或其他磁盘文件。

## 不做的事

本阶段明确不做以下内容，留给后续迭代：

- **Tool use / 函数调用**——模型不会调用任何工具
- **Agent 能力**——不做文件读写、代码编辑、命令执行
- **对话历史持久化**——不做跨会话保存与恢复
- **流式输出中止**——不做「停止生成」控制
- **Markdown 渲染**——回复以纯文本展示
- **多会话管理**——不做会话列表、切换、并行会话
- **OpenAI 协议的 reasoning 映射**——`thinking` 在 openai 协议下仅忽略+警告，不映射到 OpenAI reasoning 参数
- **HTTP 高级配置**——不做自定义请求头、代理设置

## 验收标准

| 编号 | 验收标准 | 对应需求 |
|------|---------|---------|
| AC1 | 使用 DeepSeek 配置（`base_url: https://api.deepseek.com/anthropic`，`model: deepseek-v4-pro`，`api_key: ${DEEPSEEK_API_KEY}`）启动，输入问题，回复逐字流式出现并完整显示 | F2/F5/N1 |
| AC2 | 切换到 openai 协议的 provider 启动，输入问题，回复正常流式出现 | F6 |
| AC3 | 多轮对话：第一轮问「请解释什么是装饰器」，第二轮问「用一句话总结你刚才的解释」，模型回答能正确引用第一轮内容 | F3 |
| AC4 | anthropic 协议 + `thinking: true` 对话时，界面先以暗色样式实时显示思考内容，随后以正常样式显示正式回答 | F7 |
| AC5 | openai 协议 + `thinking: true` 启动时打印警告，对话照常进行 | F7 |
| AC6 | `api_key` 配置为 `${DEEPSEEK_API_KEY}` 且环境变量已设置，能正常调用 | F1 |
| AC7 | 配置缺少必填字段（如缺 `model`）→ 启动报错，指明具体配置项后退出 | F1 |
| AC8 | `protocol` 为非法值 → 启动报错后退出 | F1 |
| AC9 | `api_key` 引用未设置的环境变量 → 启动报错后退出 | F1 |
| AC10 | `--provider` 指定不存在的 name → 启动报错后退出 | F1 |
| AC11 | 配置多个 provider 且不带 `--provider` 启动 → 出现交互选择界面，选定后进入对话 | F1 |
| AC12 | `/exit`、Ctrl+C、Ctrl+D 三种方式均能正常退出程序 | F2 |
| AC13 | API 返回 401（密钥无效）→ 显示可读错误信息，程序不崩溃，可继续输入或正常退出 | N2 |
| AC14 | `base_url` 不可达或网络断开 → 显示可读错误，程序不崩溃 | N2/N3 |
| AC15 | 整个运行过程（含报错输出）中，界面与日志不出现完整 API Key 明文 | N6 |
