"""OpenAI 协议 Provider（chat completions + SSE）。"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from mewcode.config import ProviderConfig
from mewcode.providers.base import (
    ChatMessage,
    Provider,
    ProviderError,
    StreamDone,
    StreamEvent,
    TextBlock,
    TextDelta,
    ThinkingDelta,
)
from mewcode.providers.sse import iter_sse

MAX_TOKENS = 8192


class OpenAIProvider(Provider):
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0)
        )

    def _serialize_message(self, message: ChatMessage) -> dict:
        text = "".join(b.text for b in message.blocks if isinstance(b, TextBlock))
        return {"role": message.role, "content": text}

    @staticmethod
    def _describe_http_error(status: int, detail: str) -> str:
        if status == 401:
            msg = "API 认证失败（api_key 无效或过期）"
        elif status == 429:
            msg = "触发限流（429），请稍后重试"
        elif 500 <= status < 600:
            msg = f"服务端错误（{status}）"
        else:
            msg = f"API 返回错误状态 {status}"
        return f"{msg}：{detail}" if detail else msg

    async def stream_chat(
        self, messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        url = f"{self.config.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.config.model,
            "stream": True,
            "max_tokens": MAX_TOKENS,
            "messages": [self._serialize_message(m) for m in messages],
        }
        try:
            response = await self._client.post(url, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise ProviderError(f"网络错误: {exc}") from exc

        if response.status_code != 200:
            detail = ""
            try:
                data = response.json()
                if isinstance(data, dict) and isinstance(data.get("error"), dict):
                    detail = data["error"].get("message", "")
                elif isinstance(data, dict) and isinstance(data.get("error"), str):
                    detail = data["error"]
            except Exception:
                pass
            raise ProviderError(self._describe_http_error(response.status_code, detail))

        text_parts: list[str] = []
        finish_reason = ""
        got_done = False

        try:
            async for frame in iter_sse(response):
                if frame.data == "[DONE]":
                    got_done = True
                    break
                try:
                    chunk = json.loads(frame.data)
                except json.JSONDecodeError as exc:
                    raise ProviderError(f"SSE 帧 JSON 解析失败: {exc}") from exc

                if "error" in chunk and isinstance(chunk.get("error"), dict):
                    raise ProviderError(f"API 错误: {chunk['error'].get('message', chunk['error'])}")

                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    reasoning = delta.get("reasoning_content")
                    if reasoning:
                        yield ThinkingDelta(reasoning)
                    content = delta.get("content")
                    if content:
                        text_parts.append(content)
                        yield TextDelta(content)
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
        except httpx.HTTPError as exc:
            raise ProviderError(f"连接中断: {exc}") from exc

        if not got_done:
            raise ProviderError("连接在回复完成前中断，回复不完整")

        message = ChatMessage(
            role="assistant", blocks=(TextBlock(text="".join(text_parts)),)
        )
        yield StreamDone(message=message, truncated=finish_reason == "length")

    async def aclose(self) -> None:
        await self._client.aclose()
