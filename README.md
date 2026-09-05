# MewCode

MewCode 是一个终端 AI 助手（Coding Agent），当前版本支持纯对话：流式逐字输出、多轮上下文、Anthropic / OpenAI 双协议、thinking 思考展示。

## 安装

```bash
git clone <repo> mewcode   # 或直接进入项目目录
cd mewcode
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"   # 只运行不加 [dev]
```

## 配置

默认配置文件路径为 `~/.mewcode/config.yaml`，可用 `--config <path>` 覆盖。格式：

```yaml
providers:
  - name: deepseek          # 必填：供应商标识名，区分多个配置
    protocol: anthropic     # 必填：anthropic | openai
    model: deepseek-v4-pro  # 必填：请求使用的模型
    base_url: https://api.deepseek.com/anthropic  # 必填：服务根地址
    api_key: ${DEEPSEEK_API_KEY}  # 必填：认证密钥，支持 ${ENV_VAR} 引用
    thinking: true          # 可选：启用思考输出，默认 false
```

- **密钥安全**：推荐 `api_key: ${ENV_VAR}` 从环境变量注入，不要在 YAML 中保存明文密钥。程序不会把解析后的密钥写回任何文件。
- **thinking 说明**：`protocol: anthropic` 且模型在支持清单内时启用思考输出；`protocol: openai` 时该字段被忽略（启动时警告）。

环境变量在启动前设置：

```bash
export DEEPSEEK_API_KEY=sk-xxx
```

## 启动

```bash
.venv/bin/mewcode                          # 使用默认配置
.venv/bin/mewcode --config ./my.yaml       # 指定配置文件
.venv/bin/mewcode --provider deepseek      # 指定 provider（多配置时）
```

- 配置多个 provider 且不带 `--provider` 时，启动后出现交互选择界面。
- 只有一个 provider 时直接进入对话。
- 退出方式：输入 `/exit`、Ctrl+C 或 Ctrl+D。

## 开发

```bash
.venv/bin/pytest          # 运行全部测试
.venv/bin/python -m mewcode  # 直接运行入口
```
