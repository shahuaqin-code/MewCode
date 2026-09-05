from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from mewcode.config import ProviderConfig
from mewcode.prompt import SYSTEM_PROMPT

from . import Message, StreamEvent


class AnthropicProvider:
    def __init__(self, cfg: ProviderConfig):
        self.name, self.model = cfg.name, cfg.model
        self._thinking = cfg.thinking
        self._client = AsyncAnthropic(
            api_key=cfg.api_key,
            base_url=cfg.base_url or "https://api.anthropic.com",
            max_retries=0,
        )

    async def stream(self, msgs: list[Message]) -> AsyncIterator[StreamEvent]:
        try:
            options = {}
            if self._thinking:
                options["thinking"] = {"type": "enabled", "budget_tokens": 2048}
            complete = False
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": m.role, "content": m.content} for m in msgs],
                **options,
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield StreamEvent(text=event.delta.text)
                    elif event.type == "message_stop":
                        complete = True
            if not complete:
                raise RuntimeError("Incomplete stream")
            yield StreamEvent(done=True)
        except Exception as exc:
            yield StreamEvent(err=exc)

    async def aclose(self) -> None:
        await self._client.close()
