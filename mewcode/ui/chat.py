"""对话页：历史滚动区 + 输入框 + 流式渲染。"""

from __future__ import annotations

import asyncio

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Static

from mewcode.providers.base import (
    Provider,
    ProviderError,
    StreamDone,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
)
from mewcode.session import Session


class ChatScreen(Screen):
    BINDINGS = [
        Binding("ctrl+c", "quit", "退出", priority=True),
        Binding("ctrl+d", "quit", "退出", priority=True),
    ]

    def __init__(self, provider: Provider, session: Session):
        super().__init__()
        self.provider = provider
        self.session = session
        self._task: asyncio.Task | None = None
        self._exiting = False
        self._thinking_widget: Static | None = None
        self._answer_widget: Static | None = None
        self._thinking_text = ""
        self._answer_text = ""

    def compose(self) -> ComposeResult:
        yield VerticalScroll(
            Static("欢迎使用 MewCode。输入问题回车发送；/exit 退出。", classes="hint"),
            id="history",
        )
        yield Input(placeholder="输入问题，回车发送；/exit 退出", id="prompt")

    # ---------- 渲染 ----------

    @property
    def _history(self) -> VerticalScroll:
        return self.query_one("#history", VerticalScroll)

    def _scroll(self) -> None:
        self._history.scroll_end(animate=False)

    def _append_user(self, text: str) -> None:
        self._history.mount(Static(f"🧑 {text}", classes="user"))
        self._scroll()

    def _append_thinking(self, delta: str) -> None:
        if self._thinking_widget is None:
            self._thinking_widget = Static("", classes="thinking")
            self._thinking_text = "💭 "
            self._history.mount(self._thinking_widget)
        self._thinking_text += delta
        self._thinking_widget.update(self._thinking_text)
        self._scroll()

    def _append_answer(self, delta: str) -> None:
        if self._answer_widget is None:
            self._answer_widget = Static("", classes="answer")
            self._answer_text = ""
            self._history.mount(self._answer_widget)
        self._answer_text += delta
        self._answer_widget.update(self._answer_text)
        self._scroll()

    def _append_error(self, text: str) -> None:
        self._history.mount(Static(f"❌ {text}", classes="error"))
        self._scroll()

    def _append_warning(self, text: str) -> None:
        self._history.mount(Static(text, classes="warning"))
        self._scroll()

    # ---------- 对话轮次 ----------

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value.strip()
        event.input.clear()
        if not user_text:
            return
        if user_text == "/exit":
            asyncio.create_task(self.action_quit())
            return
        self._append_user(user_text)
        event.input.disabled = True  # 生成期间禁止重复提交
        self._task = asyncio.create_task(self._run_turn(user_text))

    async def _run_turn(self, user_text: str) -> None:
        try:
            messages = self.session.build_request(user_text)
            done: StreamDone | None = None
            try:
                async for event in self.provider.stream_chat(messages):
                    if isinstance(event, ThinkingDelta):
                        self._append_thinking(event.text)
                    elif isinstance(event, TextDelta):
                        self._append_answer(event.text)
                    elif isinstance(event, StreamDone):
                        done = event
            except ProviderError as exc:
                self._append_error(f"错误: {exc}")
                return
            if done is None:
                self._append_error("错误: 未收到完整回复")
                return
            if done.truncated:
                self._append_warning("⚠ 回答达到输出上限，已截断")
            self.session.commit(user_text, done.message)
        except Exception as exc:  # 防御：任务内异常不击穿 UI
            self._append_error(f"内部错误: {exc}")
        finally:
            if not self._exiting:
                self._thinking_widget = None
                self._answer_widget = None
                prompt = self.query_one("#prompt", Input)
                prompt.disabled = False
                prompt.focus()

    # ---------- 退出 ----------

    async def action_quit(self) -> None:
        if self._exiting:
            return
        self._exiting = True
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        await self.provider.aclose()
        self.app.exit()
