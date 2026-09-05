"""Protocol-independent messages and streaming contract."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

from mewcode.config import ProviderConfig


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class StreamEvent:
    text: str = ""
    done: bool = False
    err: Exception | None = None


class Provider(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...
    def stream(self, msgs: list[Message]) -> AsyncIterator[StreamEvent]: ...
    async def aclose(self) -> None: ...


def new_provider(cfg: ProviderConfig) -> Provider:
    from .anthropic_provider import AnthropicProvider
    from .openai_provider import OpenAIProvider

    if cfg.protocol == "anthropic":
        return AnthropicProvider(cfg)
    if cfg.protocol == "openai":
        return OpenAIProvider(cfg)
    raise ValueError("Unsupported protocol")
