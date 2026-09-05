# MewCode Checklist

> 每一项通过运行代码或观察行为来验证，聚焦系统行为。

## 实现完整性

- [ ] 配置加载与校验可用（验证：合法 / 非法 YAML 分别运行 `load_config`，行为符合 spec F1）
- [ ] SSE 帧解析器对两种协议的事件流正确分帧（验证：SSE 相关单元测试全绿）
- [ ] Anthropic 协议 Provider 产出正确事件序列与 thinking 参数（验证：provider 相关单元测试全绿）
- [ ] OpenAI 协议 Provider 产出正确事件序列（验证：同上）
- [ ] Session 成功才追加的历史语义（验证：session 相关单元测试全绿）

## 集成

- [ ] PROTOCOLS 注册表包含 anthropic 与 openai，两实现经统一 Provider 接口驱动（验证：pytest 全绿）
- [ ] TUI 与 Provider 仅通过 StreamEvent 流交互（验证：FakeProvider 冒烟——替换真实 Provider 不改动 TUI 代码）
- [ ] 退出清理链路：取消任务 → await 任务结束 → `provider.aclose()`（验证：退出时无挂起任务告警、进程干净退出）

## 编译与测试

- [ ] 全部单元测试通过（验证：`.venv/bin/pytest` 全绿）
- [ ] 全部模块可编译（验证：`.venv/bin/python -m py_compile` 全部通过）
- [ ] lint 检查通过（如有配置）——当前无 lint 配置，跳过

## 端到端场景

- [ ] 场景 1（AC1/AC6）：DeepSeek 配置（`api_key: ${DEEPSEEK_API_KEY}`）启动 → 输入问题 → 回复逐字流式出现并完整显示
- [ ] 场景 2（AC3）：第一轮问「请解释什么是装饰器」→ 第二轮问「用一句话总结你刚才的解释」→ 回答正确引用第一轮内容
- [ ] 场景 3（AC4）：DeepSeek + `thinking: true` 对话 → 先暗色斜体实时显示思考内容，随后正常样式显示回答
- [ ] 场景 4（AC7/AC8/AC9/AC10）：四种非法输入——缺 `model`、`protocol` 非法、`api_key` 引用未设置的环境变量、`--provider` 名字不存在 → 各自显示指明配置项的可读错误并以退出码 1 退出
- [ ] 场景 5（AC5）：openai 协议 + `thinking: true` 启动 → 打印警告，对话照常进行
- [ ] 场景 5b：官方 Claude 不可关闭组模型（如 `claude-fable-5-1`）+ `thinking: false` 启动 → 打印「该模型默认启用思考且不支持关闭」警告
- [ ] 场景 6（AC11）：多配置且不带 `--provider` 启动 → 出现交互选择界面，选定后进入对话
- [ ] 场景 7（AC12）：`/exit`、Ctrl+C、Ctrl+D 三种方式均干净退出
- [ ] 场景 8（AC13）：无效 api_key 发起对话 → 显示可读的认证错误，程序不崩溃，可继续输入或正常退出
- [ ] 场景 9（AC14）：`base_url` 不可达 → 显示可读的网络错误，程序不崩溃
- [ ] 场景 10（AC2）：openai 协议 provider 指向 DeepSeek OpenAI 兼容接口（`base_url: https://api.deepseek.com`，`model: deepseek-v4-pro`）→ 回复正常流式出现
- [ ] 场景 11（AC15）：上述全部运行过程（含报错输出）中，屏幕与日志不出现完整 api_key 明文
- [ ] 场景 12（截断提示）：FakeProvider 产出 `truncated=True` 的 StreamDone → 回答后显示「⚠ 回答达到输出上限，已截断」

## spec 验收标准覆盖映射

| spec AC | checklist 条目 |
|---------|---------------|
| AC1 / AC6 | 场景 1 |
| AC2 | 场景 10 |
| AC3 | 场景 2 |
| AC4 | 场景 3 |
| AC5 | 场景 5 |
| AC7–AC10 | 场景 4 |
| AC11 | 场景 6 |
| AC12 | 场景 7 |
| AC13 | 场景 8 |
| AC14 | 场景 9 |
| AC15 | 场景 11 |
