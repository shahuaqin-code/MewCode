"""Presentation helpers and responsive conversation log."""

from rich.console import Group
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text
from textual import events
from textual.widgets import RichLog

from mewcode.llm.errors import safe_error


def user_block(text: str):
    return Text("● " + text, style="bold")


def render_markdown(text: str):
    return Group(Text("●", style="cyan"), Markdown(text))


def error_block(exc: Exception):
    return Text("● " + safe_error(exc), style="bold red")


def status_bar(name: str, model: str):
    table = Table.grid(expand=True)
    table.add_column(ratio=1, overflow="ellipsis", no_wrap=True)
    table.add_column(ratio=1, justify="right", overflow="ellipsis", no_wrap=True)
    table.add_row(Text(name), Text(model, style="dim"))
    return table


class ConversationLog(RichLog):
    """Retain renderables for width reflow and terminal scrollback on exit."""

    def __init__(self, **kwargs):
        super().__init__(wrap=True, min_width=1, **kwargs)
        self.blocks = []
        self._last_width = 0

    def append(self, block):
        self.blocks.append(block)
        self.write(block, scroll_end=True)

    def on_resize(self, event: events.Resize):
        if event.size.width != self._last_width:
            self._last_width = event.size.width
            at_end = self.is_vertical_scroll_end
            position = self.scroll_y
            self.clear()
            for block in self.blocks:
                self.write(block, scroll_end=False)
            if at_end:
                self.call_after_refresh(self.scroll_end, animate=False)
            else:
                self.call_after_refresh(self.scroll_to, y=position, animate=False)
