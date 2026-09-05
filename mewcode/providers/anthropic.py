"""Anthropic 协议 Provider（Messages API + SSE）。"""

from __future__ import annotations

import json
import sys
from typing import AsyncIterator
from urllib.parse import urlsplit

import httpx

from mewcode.config import ProviderConfig
from mewcode.providers.base import (
    ChatMessage,
    ContentBlock,
    Provider,
    ProviderError,
    StreamDone,
    StreamEvent,
    TextBlock,
    TextDelta,
    ThinkingBlock,
    ThinkingDelta,
)
from mewcode.providers.sse import iter_sse

ANTHROPIC_VERSION = "2023-06-01"
MAX_TOKENS = 8192
BUDGET_TOKENS = 4096  # legacy 模型：1024 <= budget < max_tokens

# thinking: true 支持的模型清单（精确匹配）
DEEPSEEK_MODELS = {"deepseek-v4-pro", "deepseek-v4-pro[1m]", "deepseek-v4-flash"}

CLAUDE_ADAPTIVE_MODELS = {
    "claude-fable-5-1",
    "claude-mythos-5-1",
    "claude-fable-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
}

CLAUDE_BUDGET_MODELS = {
    "claude-haiku-4-5",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-3-7-sonnet",
    "claude-3-5-sonnet",
    "claude-3-5-haiku",
    "claude-3-opus",
    "claude-3-sonnet",
    "claude-3-haiku",
}

# thinking: false 时默认开启且支持显式关闭的模型
CLAUDE_DISABLEABLE = {"claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-5"}
# thinking: false 时默认开启且不可关闭（显式 disabled 返回 400）
CLAUDE_ALWAYS_ON = {"claude-fable-5-1", "claude-mythos-5-1", "claude-fable-5"}


def _service_for(base_url: str) -> str:
    host = (urlsplit(base_url).hostname or "").lower()
    if host == "api.deepseek.com":
        return "deepseek"
    if host == "api.anthropic.com":
        return "claude"
    return "unknown"


class AnthropicProvider(Provider):
    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._service = _service_for(config.base_url)
        self._thinking_param = self._resolve_thinking_param()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0)
        )

    def _resolve_thinking_param(self) -> dict | None:
        """返回请求体中的 thinking 参数；None 表示不携带该字段。"""
        model = self.config.model

        if self._service == "deepseek":
            if not self.config.thinking:
                return None
            if model not in DEEPSEEK_MODELS:
                raise ProviderError(
                    f"模型 {model} 不在 DeepSeek thinking 支持清单中"
                    f"（{'、'.join(sorted(DEEPSEEK_MODELS))}）"
                )
            return {"type": "enabled"}

        if self._service == "claude":
            if self.config.thinking:
                if model in CLAUDE_ADAPTIVE_MODELS:
                    return {"type": "adaptive", "display": "summarized"}
                if model in CLAUDE_BUDGET_MODELS:
                    return {"type": "enabled", "budget_tokens": BUDGET_TOKENS}
                raise ProviderError(
                    f"模型 {model} 不在官方 Claude thinking 支持清单中，无法构造 thinking 参数"
                )
            # thinking: false
            if model in CLAUDE_DISABLEABLE:
                return {"type": "disabled"}
            if model in CLAUDE_ALWAYS_ON:
                print(
                    f"警告: 模型 {model} 默认启用思考且不支持关闭，思考输出仍会显示",
                    file=sys.stderr,
                )
            return None

        # 未知主机
        if self.config.thinking:
            raise ProviderError(
                f"base_url {self.config.base_url} 为未知兼容端点，无法确认 thinking 参数形状，"
                "请在清单内服务中使用 thinking"
            )
        return None

    def _serialize_message(self, message: ChatMessage) -> dict:
        if message.role == "user":
            text = "".join(b.text for b in message.blocks if isinstance(b, TextBlock))
            return {"role": "user", "content": text}

        content: list[dict] = []
        for block in message.blocks:
            if isinstance(block, ThinkingBlock):
                item: dict = {"type": "thinking", "thinking": block.text}
                if block.signature is not None:
                    item["signature"] = block.signature
                content.append(item)
            else:  # TextBlock
                content.append({"type": "text", "text": block.text})
        return {"role": "assistant", "content": content}

    def _build_body(self, messages: list[ChatMessage]) -> dict:
        body: dict = {
            "model": self.config.model,
            "max_tokens": MAX_TOKENS,
            "stream": True,
            "messages": [self._serialize_message(m) for m in messages],
        }
        if self._thinking_param is not None:
            body["thinking"] = self._thinking_param
        return body

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

    @staticmethod
    def _parse_error_frame(data: str) -> str:
        try:
            event = json.loads(data)
            err = event.get("error", {})
            message = err.get("message", "") if isinstance(err, dict) else ""
            return f"服务端返回错误: {message}" if message else "服务端返回错误"
        except json.JSONDecodeError:
            return "服务端返回错误"

    async def stream_chat(
        self, messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        url = f"{self.config.base_url}/v1/messages"
        headers = {
            "x-api-key": self.config.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            response = await self._client.post(
                url, headers=headers, json=self._build_body(messages)
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"网络错误: {exc}") from exc

        if response.status_code != 200:
            detail = ""
            try:
                data = response.json()
                if isinstance(data, dict) and isinstance(data.get("error"), dict):
                    detail = data["error"].get("message", "")
            except Exception:
                pass
            raise ProviderError(self._describe_http_error(response.status_code, detail))

        blocks: list[ContentBlock] = []
        thinking_parts: list[str] = []
        thinking_signature: str | None = None
        text_parts: list[str] = []
        block_kind: str | None = None  # 当前进行中的块类型
        stop_reason = ""
        got_stop = False

        try:
            async for frame in iter_sse(response):
                if frame.event == "error":
                    raise ProviderError(self._parse_error_frame(frame.data))
                if frame.data == "[DONE]":
                    break
                try:
                    event = json.loads(frame.data)
                except json.JSONDecodeError as exc:
                    raise ProviderError(f"SSE 帧 JSON 解析失败: {exc}") from exc

                etype = event.get("type")
                if etype == "message_start":
                    continue
                if etype == "content_block_start":
                    block_kind = event.get("content_block", {}).get("type")
                elif etype == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "thinking_delta":
                        if block_kind is None:
                            block_kind = "thinking"
                        text = delta.get("thinking", "")
                        thinking_parts.append(text)
                        yield ThinkingDelta(text)
                    elif delta.get("type") == "text_delta":
                        if block_kind is None:
                            block_kind = "text"
                        text = delta.get("text", "")
                        text_parts.append(text)
                        yield TextDelta(text)
                    elif delta.get("type") == "signature_delta":
                        thinking_signature = delta.get("signature", "")
                elif etype == "content_block_stop":
                    if block_kind == "thinking":
                        blocks.append(
                            ThinkingBlock(text="".join(thinking_parts), signature=thinking_signature)
                        )
                        thinking_parts = []
                        thinking_signature = None
                    elif block_kind == "text":
                        blocks.append(TextBlock(text="".join(text_parts)))
                        text_parts = []
                    block_kind = None
                elif etype == "message_delta":
                    stop_reason = event.get("delta", {}).get("stop_reason", stop_reason)
                elif etype == "message_stop":
                    got_stop = True
                    break
                # 其余事件（ping 等）忽略
        except httpx.HTTPError as exc:
            raise ProviderError(f"连接中断: {exc}") from exc

        if not got_stop:
            raise ProviderError("连接在回复完成前中断，回复不完整")

        message = ChatMessage(role="assistant", blocks=tuple(blocks))
        yield StreamDone(message=message, truncated=stop_reason == "max_tokens")

    async def aclose(self) -> None:
        await self._client.aclose()
