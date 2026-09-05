# MewCode

Python 3.12+ 的多协议终端对话客户端，按 `docs/spec.md`、`plan.md`、`task.md`、`checklist.md` 重建。

## 安装与运行

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .mewcode/config.yaml.example .mewcode/config.yaml
# 编辑 .mewcode/config.yaml，填写环境变量引用、model 和可选 base_url
export ANTHROPIC_API_KEY="你的密钥"
python -m mewcode
# 或 mewcode
```

程序只读取当前工作目录的 `.mewcode/config.yaml`。密钥支持 `${VARIABLE}` 或 `$VARIABLE` 环境变量引用，不提供命令行覆盖。配置文件已加入 Git 忽略。

## 配置

`providers` 必须是非空列表，每项需包含非空字符串 `name`、`protocol`、`api_key`、`model`。
`protocol` 为 `anthropic` 或 `openai`。可选 `base_url` 覆盖 SDK 默认地址；OpenAI 兼容服务通常需要以 `/v1` 结尾，具体以服务方要求为准。
`thinking` 为布尔值，默认为 false；按 plan/task，仅 Anthropic 开启扩展思考，OpenAI 忽略。思考增量不显示、不进入对话历史。

一项配置直接进入对话，多项配置用 ↑/↓ 和 Enter 选择。

例如使用 DeepSeek，在启动程序的同一个终端执行：

```sh
export DEEPSEEK_API_KEY="你的密钥"
```

配置中的密钥只写引用：

```yaml
api_key: "${DEEPSEEK_API_KEY}"
```

环境变量未设置或为空时，程序在启动阶段提示变量名，不发送无效密钥，也不回显密钥值。

## 操作

- Enter 提交；Alt+Enter 插入换行。
- 等待和流式期间输入框只读，仍可滚动查看对话；计时从提交开始。
- 回复过程中显示纯文本，结束后整体渲染 Markdown，并显示总耗时。
- `/exit` 或 Ctrl+C 退出，正在运行的连接会关闭，终端状态会恢复。
- 错误以红色显示，不自动重试。失败轮次保留在界面，但不提交进成功对话历史，避免下一轮出现不完整助手消息。

完成内容追加到 RichLog；窗口变宽或变窄时重新排版。退出时会把本次内容输出到终端滚动历史中，不写会话文件。重启后模型上下文为空。

## 结构

```text
src/mewcode/
  cli.py             配置装配与终端启动
  config.py          YAML 校验
  prompt.py          内置系统提示词与猫咪横幅
  conversation.py    进程内上下文
  llm/               统一事件接口、Anthropic/OpenAI 官方 SDK 适配器
  tui/               选择、状态机、异步流、计时、渲染
```

本期不包含工具调用、MCP、记忆、历史持久化、上下文压缩、运行时切换模型或取消单轮回复。

## 验证

```sh
pytest
ruff check .
ruff format --check .
```

协议测试使用真实 SDK 搭配 HTTP MockTransport，覆盖自定义端点、系统提示词与完整历史、思考过滤、错误不重试、取消传播。TUI 测试使用 Textual Pilot。POSIX 上还会在真实 PTY 中验证 `/exit`、Ctrl+C 和终端属性恢复。

验收证据与尚未完成的真实服务联调见 `docs/checklist.md`。`requirements.txt` 固定已验证环境中的运行依赖版本，可用 `pip install -r requirements.txt` 安装后再执行 `pip install -e . --no-deps`。
