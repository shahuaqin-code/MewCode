from rich.text import Text
from textual.widgets import OptionList

from mewcode.config import ProviderConfig


class ProviderSelect(OptionList):
    def __init__(self, providers: list[ProviderConfig]):
        super().__init__(
            *(Text(f"{p.name} ({p.model})") for p in providers), id="providers"
        )
