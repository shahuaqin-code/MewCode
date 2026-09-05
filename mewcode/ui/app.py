"""MewCode 应用组装：Provider 实例化时机、退出清理。"""

from __future__ import annotations

import sys

from textual.app import App

from mewcode.config import ProviderConfig
from mewcode.providers import PROTOCOLS
from mewcode.providers.base import ProviderError
from mewcode.session import Session
from mewcode.ui.chat import ChatScreen
from mewcode.ui.picker import ProviderPickerScreen


class MewCodeApp(App):
    TITLE = "MewCode"
    CSS = """
    #history {
        height: 1fr;
        padding: 1 2;
    }
    #prompt {
        dock: bottom;
        margin: 1 2;
    }
    .hint { color: $text-muted; }
    .user { color: $text; margin-top: 1; }
    .answer { color: $text; }
    .thinking { color: $text-muted; text-style: italic; }
    .error { color: $error; }
    .warning { color: $warning; }
    #picker-title { margin: 1 2; }
    #picker { margin: 0 2 1 2; height: 1fr; }
    """

    def __init__(self, configs: list[ProviderConfig], provider_name: str | None = None):
        super().__init__()
        self._configs = configs
        self._provider_name = provider_name
        self._provider = None
        self._session = Session()

    def on_mount(self) -> None:
        if self._provider_name is not None:
            config = next((c for c in self._configs if c.name == self._provider_name), None)
            if config is None:
                print(f"错误: 未找到名为 {self._provider_name} 的 provider", file=sys.stderr)
                self.exit(1)
                return
            self._start_chat(config)
        elif len(self._configs) == 1:
            self._start_chat(self._configs[0])
        else:
            self.push_screen(ProviderPickerScreen(self._configs), self._start_chat)

    def _start_chat(self, config: ProviderConfig | None) -> None:
        """用户选定配置后才实例化 Provider。"""
        if config is None:
            self.exit()
            return
        try:
            self._provider = PROTOCOLS[config.protocol](config)
        except ProviderError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            self.exit(1)
            return
        self.push_screen(ChatScreen(self._provider, self._session))
