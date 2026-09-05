"""Textual application: select, compose, stream, and exit."""

import asyncio
import os
import time
from contextlib import suppress
from enum import Enum

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message as UIMessage
from textual.widgets import OptionList, Static, TextArea

from mewcode import __version__
from mewcode.config import ProviderConfig
from mewcode.conversation import Conversation
from mewcode.llm import new_provider
from mewcode.prompt import render_banner

from .select import ProviderSelect
from .stream import StreamMixin
from .view import ConversationLog, error_block, status_bar, user_block


class SessionState(Enum):
    SELECTING = "selecting"
    IDLE = "idle"
    STREAMING = "streaming"


class MessageInput(TextArea):
    BINDINGS = [
        Binding("enter", "send", "Send", priority=True),
        Binding("alt+enter", "newline", "New line", priority=True),
    ]

    class Submitted(UIMessage):
        def __init__(self, text):
            super().__init__()
            self.text = text

    def action_send(self):
        if not self.read_only:
            self.post_message(self.Submitted(self.text))

    def action_newline(self):
        if not self.read_only:
            self.insert("\n")


class MewCodeApp(StreamMixin, App):
    TITLE = "MewCode"
    BINDINGS = [Binding("ctrl+c", "quit", "Quit", priority=True)]
    CSS = """
    Screen { background: #17191d; color: #e3e4e8; }
    Screen:inline { height: 100%; }
    #log { height: 1fr; padding: 0 1; scrollbar-size: 1 1; }
    #providers { height: 1fr; margin: 1; }
    #selection-title { height: auto; padding: 1; color: #83cfce; }
    #streaming { height: auto; max-height: 40%; padding: 0 1; }
    #reply { height: auto; width: 1fr; }
    #progress { height: 1; padding: 0 1; }
    #composer { height: 5; border: round #638f91; margin: 0 1; }
    #chevron { width: 3; padding: 0 1; color: #83cfce; }
    #input { width: 1fr; height: 1fr; border: none; background: #17191d; }
    #input:focus { border: none; }
    #hint { height: 1; padding: 0 1; color: #9296a0; }
    #statusbar { height: 1; padding: 0 1; }
    """

    def __init__(self, providers: list[ProviderConfig]):
        super().__init__()
        if not providers:
            raise ValueError("At least one provider is required")
        self.providers = providers
        self.provider = None
        self.state = SessionState.SELECTING
        self.conv = Conversation()
        self.cur_reply = ""
        self.turn_start = 0.0
        self._stream_task = None
        self._timer = None
        self._session_closing = False
        self.transcript = []

    def compose(self) -> ComposeResult:
        yield Static(
            "Choose a provider · ↑/↓ move · Enter select", id="selection-title"
        )
        yield ProviderSelect(self.providers)
        yield ConversationLog(id="log")
        with VerticalScroll(id="streaming"):
            yield Static("", id="reply", markup=False)
        yield Static("", id="progress", markup=False)
        with Horizontal(id="composer"):
            yield Static("❯", id="chevron")
            yield MessageInput(
                id="input", placeholder="Send a message...", show_line_numbers=False
            )
        yield Static(
            "Enter send · Alt+Enter new line · /exit or Ctrl+C quit", id="hint"
        )
        yield Static("", id="statusbar", markup=False)

    @property
    def history(self) -> ConversationLog:
        return self.query_one("#log", ConversationLog)

    @property
    def editor(self) -> MessageInput:
        return self.query_one("#input", MessageInput)

    def on_mount(self):
        self.history.append(Text(render_banner(__version__, os.getcwd())))
        self.query_one("#streaming").display = False
        self.query_one("#progress").display = False
        if len(self.providers) == 1:
            self._select(0)
        else:
            self._show_selection(True)
            self.query_one(ProviderSelect).focus()

    def _show_selection(self, selecting):
        for selector in ("#providers", "#selection-title"):
            self.query_one(selector).display = selecting
        for selector in ("#log", "#composer", "#hint", "#statusbar"):
            self.query_one(selector).display = not selecting

    def _select(self, index):
        try:
            self.provider = new_provider(self.providers[index])
        except Exception as exc:
            self.history.append(error_block(exc))
            self.exit(1)
            return
        self.state = SessionState.IDLE
        self._show_selection(False)
        self.query_one("#statusbar", Static).update(
            status_bar(self.provider.name, self.provider.model)
        )
        self.editor.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        self._select(event.option_index)

    async def on_message_input_submitted(self, event: MessageInput.Submitted):
        await self.submit(event.text)

    async def submit(self, text: str):
        if text.strip() == "/exit":
            await self.action_quit()
            return
        if self.state != SessionState.IDLE or not text.strip() or self._session_closing:
            return
        self.conv.add_user(text)
        self.history.append(user_block(text))
        self.editor.clear()
        self.editor.read_only = True
        self.cur_reply = ""
        self.turn_start = time.monotonic()
        self.state = SessionState.STREAMING
        self.query_one("#streaming").display = True
        self.query_one("#progress").display = True
        self._tick()
        self._timer = self.set_interval(0.1, self._tick)
        self._stream_task = asyncio.create_task(self._consume_stream())

    async def _cleanup(self):
        if self._session_closing:
            return
        self._session_closing = True
        if self._timer:
            self._timer.stop()
        if self._stream_task:
            self._stream_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._stream_task
        if self.provider:
            with suppress(Exception):
                await self.provider.aclose()

    async def action_quit(self):
        self.transcript = list(self.history.blocks)
        if self.cur_reply:
            self.transcript.append(Text(self.cur_reply))
        await self._cleanup()
        self.exit()

    async def on_unmount(self):
        await self._cleanup()
