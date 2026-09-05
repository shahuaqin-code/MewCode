import asyncio
import json

import httpx
import pytest

from mewcode.config import ProviderConfig
from mewcode.llm import Message, new_provider
from mewcode.prompt import SYSTEM_PROMPT


def sse(data, event=None):
    return (f"event: {event}\n" if event else "") + f"data: {json.dumps(data)}\n\n"


def response_body(protocol):
    if protocol == "openai":
        return "".join(
            [
                sse({"choices": []}),
                sse(
                    {
                        "choices": [
                            {"index": 0, "delta": {"reasoning_content": "HIDDEN"}}
                        ]
                    }
                ),
                sse({"choices": [{"index": 0, "delta": {"content": "Hello"}}]}),
                sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}),
                "data: [DONE]\n\n",
            ]
        )
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "m",
                "type": "message",
                "role": "assistant",
                "model": "m",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 0},
            },
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking", "thinking": "", "signature": ""},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "HIDDEN"},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "text", "text": ""},
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "text_delta", "text": "Hello"},
        },
        {"type": "content_block_stop", "index": 1},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 1},
        },
        {"type": "message_stop"},
    ]
    return "".join(sse(event, event["type"]) for event in events)


@pytest.mark.parametrize("protocol", ["openai", "anthropic"])
async def test_sdk_stream_request_and_filter(protocol):
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            text=response_body(protocol),
            headers={"content-type": "text/event-stream"},
        )

    cfg = ProviderConfig(
        "test", protocol, "secret", "model", "https://compatible.test/v1", True
    )
    provider = new_provider(cfg)
    await provider._client._client.aclose()
    provider._client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    history = [
        Message("user", "first"),
        Message("assistant", "answer"),
        Message("user", "second"),
    ]
    events = [event async for event in provider.stream(history)]
    assert "".join(e.text for e in events) == "Hello"
    assert events[-1].done and all(e.err is None for e in events)
    payload = json.loads(requests[0].content)
    assert requests[0].url.host == "compatible.test"
    assert payload["messages"][-3:] == [
        {"role": m.role, "content": m.content} for m in history
    ]
    if protocol == "anthropic":
        assert payload["system"] == SYSTEM_PROMPT
        assert payload["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    else:
        assert payload["messages"][0]["content"] == SYSTEM_PROMPT
        assert "thinking" not in payload
    await provider.aclose()
    assert provider._client.is_closed()


@pytest.mark.parametrize("protocol", ["openai", "anthropic"])
async def test_no_retry_and_recoverable_error(protocol):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            429, json={"error": {"message": "secret", "type": "rate_limit_error"}}
        )

    provider = new_provider(ProviderConfig("test", protocol, "secret", "model"))
    await provider._client._client.aclose()
    provider._client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    events = [event async for event in provider.stream([Message("user", "hi")])]
    assert calls == 1 and events[-1].err is not None and not events[-1].done
    from mewcode.llm.errors import safe_error

    assert "secret" not in safe_error(events[-1].err)
    await provider.aclose()


@pytest.mark.parametrize("protocol", ["openai", "anthropic"])
async def test_cancellation_propagates(protocol):
    async def handler(request):
        raise asyncio.CancelledError

    provider = new_provider(ProviderConfig("test", protocol, "secret", "model"))
    await provider._client._client.aclose()
    provider._client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(asyncio.CancelledError):
        _ = [e async for e in provider.stream([Message("user", "hi")])]
    await provider.aclose()
