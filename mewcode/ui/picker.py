"""Provider 选择页。"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from mewcode.config import ProviderConfig


class ProviderPickerScreen(Screen[ProviderConfig | None]):
    """多配置且未指定 --provider 时的交互选择页。"""

    def __init__(self, configs: list[ProviderConfig]):
        super().__init__()
        self._configs = configs

    def compose(self) -> ComposeResult:
        yield Static("选择 provider（↑↓ 移动，回车选定）：", id="picker-title")
        yield OptionList(
            *[
                Option(f"{c.name} — {c.model}（{c.protocol}）", id=c.name)
                for c in self._configs
            ],
            id="picker",
        )

    @on(OptionList.OptionSelected)
    def on_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self._configs[event.option_index])
