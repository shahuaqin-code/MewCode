from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from mewcode.config import ProviderConfig
from mewcode.prompt import SYSTEM_PROMPT

from . import Message, StreamEvent


class OpenAIProvider:
    def __init__(self, cfg: ProviderConfig):
        self.name, self.model = cfg.name, cfg.model
        self._client = AsyncOpenAI(
            api_key=cfg.api_key,
            base_url=cfg.base_url or "https://api.openai.com/v1",
            max_retries=0,
        )

    async def stream(self, msgs: list[Message]) -> AsyncIterator[StreamEvent]:
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}]
                + [{"role": m.role, "content": m.content} for m in msgs],
                stream=True,
            )
            complete = False
            async with stream:
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if choice.delta.content:
                        yield StreamEvent(text=choice.delta.content)
                    if choice.finish_reason is not None:
                        complete = True
            if not complete:
                raise RuntimeError("Incomplete stream")
            yield StreamEvent(done=True)
        except Exception as exc:
            yield StreamEvent(err=exc)

    async def aclose(self) -> None:
        await self._client.close()
