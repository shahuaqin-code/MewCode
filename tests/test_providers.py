"""Provider 测试：请求构造、thinking 参数映射、事件映射、多块序列化。"""

import json

import httpx
import pytest

from mewcode.config import ProviderConfig
from mewcode.providers.anthropic import AnthropicProvider
from mewcode.providers.base import (
    ChatMessage,
    ProviderError,
    StreamDone,
    TextBlock,
    TextDelta,
    ThinkingBlock,
    ThinkingDelta,
)
from mewcode.providers.openai import OpenAIProvider

# ---------- 工具 ----------


def make_config(**overrides) -> ProviderConfig:
    base = dict(
        name="t",
        protocol="anthropic",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com/anthropic",
        api_key="test-key",
        thinking=False,
    )
    base.update(overrides)
    return ProviderConfig(**base)


@pytest.fixture
def mock_http(monkeypatch):
    """把 httpx.AsyncClient 替换为带 MockTransport 的客户端，并捕获请求。"""
    state: dict = {}

    def install(payload: bytes = b"", status: int = 200):
        def handler(request: httpx.Request) -> httpx.Response:
            state["url"] = str(request.url)
            state["headers"] = dict(request.headers)
            state["body"] = json.loads(request.content) if request.content else None
            return httpx.Response(status, content=payload)

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient

        def factory(**kwargs):
            return real_client(transport=transport, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", factory)

    state["install"] = install
    return state


def sse(*lines: str) -> bytes:
    # 每项为一帧（可含 event+data 多行），帧间以空行分隔，末尾以空行结束
    return ("\n\n".join(lines) + "\n\n").encode()


def frame(data: dict, event: str | None = None) -> str:
    line = f"data: {json.dumps(data, ensure_ascii=False)}"
    return f"event: {event}\n{line}" if event else line


ANTHROPIC_TEXT_STREAM = sse(
    frame({"type": "message_start", "message": {"id": "m1", "type": "message", "role": "assistant", "model": "m", "content": [], "stop_reason": None, "usage": {}}}, "message_start"),
    frame({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}, "content_block_start"),
    frame({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "你好"}}, "content_block_delta"),
    frame({"type": "content_block_stop", "index": 0}, "content_block_stop"),
    frame({"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 2}}, "message_delta"),
    frame({"type": "message_stop"}, "message_stop"),
)


async def collect(provider, user_text: str = "hi"):
    return [
        event
        async for event in provider.stream_chat(
            [ChatMessage(role="user", blocks=(TextBlock(user_text),))]
        )
    ]


# ---------- anthropic: thinking 参数映射 ----------


@pytest.mark.parametrize(
    "model,expected",
    [
        ("deepseek-v4-pro", {"type": "enabled"}),
        ("deepseek-v4-pro[1m]", {"type": "enabled"}),
        ("deepseek-v4-flash", {"type": "enabled"}),
        ("claude-opus-5", {"type": "adaptive", "display": "summarized"}),
        ("claude-opus-4-8", {"type": "adaptive", "display": "summarized"}),
        ("claude-sonnet-4-6", {"type": "adaptive", "display": "summarized"}),
        ("claude-fable-5-1", {"type": "adaptive", "display": "summarized"}),
        ("claude-haiku-4-5", {"type": "enabled", "budget_tokens": 4096}),
        ("claude-3-5-sonnet", {"type": "enabled", "budget_tokens": 4096}),
    ],
)
async def test_thinking_true_param_shapes(mock_http, model, expected):
    mock_http["install"](ANTHROPIC_TEXT_STREAM)
    host = "api.deepseek.com" if model.startswith("deepseek") else "api.anthropic.com"
    provider = AnthropicProvider(
        make_config(model=model, base_url=f"https://{host}/anthropic", thinking=True)
    )
    await collect(provider)
    assert mock_http["body"]["thinking"] == expected
    if expected.get("budget_tokens") is not None:
        assert 1024 <= expected["budget_tokens"] < 8192
    if model.startswith("deepseek"):
        assert "budget_tokens" not in mock_http["body"]["thinking"]


@pytest.mark.parametrize(
    "model,host,in_body",
    [
        ("deepseek-v4-pro", "api.deepseek.com", False),      # DeepSeek 默认无思考输出
        ("claude-opus-5", "api.anthropic.com", True),        # 显式关闭
        ("claude-fable-5-1", "api.anthropic.com", False),    # 不可关闭 → 省略 + 警告
        ("claude-opus-4-6", "api.anthropic.com", False),     # 默认关闭 → 省略
    ],
)
async def test_thinking_false_behaviors(mock_http, capsys, model, host, in_body):
    mock_http["install"](ANTHROPIC_TEXT_STREAM)
    provider = AnthropicProvider(
        make_config(model=model, base_url=f"https://{host}/anthropic", thinking=False)
    )
    await collect(provider)
    body = mock_http["body"]
    if in_body:
        assert body["thinking"] == {"type": "disabled"}
    else:
        assert "thinking" not in body
    err = capsys.readouterr().err
    if model == "claude-fable-5-1":
        assert "默认启用思考且不支持关闭" in err
    else:
        assert "默认启用思考" not in err


async def test_thinking_true_unknown_deepseek_model_errors():
    with pytest.raises(ProviderError, match="不在 DeepSeek thinking 支持清单"):
        AnthropicProvider(make_config(model="deepseek-chat", thinking=True))


async def test_thinking_true_unknown_claude_model_errors():
    with pytest.raises(ProviderError, match="不在官方 Claude thinking 支持清单"):
        AnthropicProvider(
            make_config(
                model="claude-opus-99",
                base_url="https://api.anthropic.com",
                thinking=True,
            )
        )


async def test_thinking_true_unknown_host_errors():
    with pytest.raises(ProviderError, match="未知兼容端点"):
        AnthropicProvider(
            make_config(base_url="https://example.com/anthropic", thinking=True)
        )


async def test_thinking_false_unknown_host_ok(mock_http):
    mock_http["install"](ANTHROPIC_TEXT_STREAM)
    provider = AnthropicProvider(
        make_config(base_url="https://example.com/anthropic", thinking=False)
    )
    events = await collect(provider)
    assert "thinking" not in mock_http["body"]
    assert isinstance(events[-1], StreamDone)


# ---------- anthropic: 序列化与事件映射 ----------


async def test_assistant_blocks_serialized_in_order_with_signatures(mock_http):
    mock_http["install"](ANTHROPIC_TEXT_STREAM)
    provider = AnthropicProvider(make_config())
    history = ChatMessage(
        role="assistant",
        blocks=(
            ThinkingBlock("思考一", "sig-1"),
            ThinkingBlock("", None),          # 空文本无签名：字段省略
            TextBlock("回答正文"),
        ),
    )
    messages = [history, ChatMessage(role="user", blocks=(TextBlock("继续"),))]
    _ = [e async for e in provider.stream_chat(messages)]
    serialized = mock_http["body"]["messages"]
    assert serialized[0]["content"] == [
        {"type": "thinking", "thinking": "思考一", "signature": "sig-1"},
        {"type": "thinking", "thinking": ""},
        {"type": "text", "text": "回答正文"},
    ]
    assert serialized[1] == {"role": "user", "content": "继续"}


async def test_thinking_stream_maps_events_and_keeps_blocks(mock_http):
    payload = sse(
        frame({"type": "message_start", "message": {}}, "message_start"),
        frame({"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}}, "content_block_start"),
        frame({"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "思考"}}, "content_block_delta"),
        frame({"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "中"}}, "content_block_delta"),
        frame({"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig-x"}}, "content_block_delta"),
        frame({"type": "content_block_stop", "index": 0}, "content_block_stop"),
        frame({"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}}, "content_block_start"),
        frame({"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "答"}}, "content_block_delta"),
        frame({"type": "content_block_stop", "index": 1}, "content_block_stop"),
        frame({"type": "message_delta", "delta": {"stop_reason": "end_turn"}}, "message_delta"),
        frame({"type": "message_stop"}, "message_stop"),
    )
    mock_http["install"](payload)
    provider = AnthropicProvider(make_config(thinking=True))
    events = await collect(provider)
    assert [e for e in events if isinstance(e, ThinkingDelta)] == [
        ThinkingDelta("思考"),
        ThinkingDelta("中"),
    ]
    done = events[-1]
    assert isinstance(done, StreamDone)
    assert done.truncated is False
    assert done.message.blocks == (
        ThinkingBlock("思考中", "sig-x"),
        TextBlock("答"),
    )


async def test_max_tokens_stop_reason_marks_truncated(mock_http):
    payload = sse(
        frame({"type": "message_start", "message": {}}, "message_start"),
        frame({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}, "content_block_start"),
        frame({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "x"}}, "content_block_delta"),
        frame({"type": "content_block_stop", "index": 0}, "content_block_stop"),
        frame({"type": "message_delta", "delta": {"stop_reason": "max_tokens"}}, "message_delta"),
        frame({"type": "message_stop"}, "message_stop"),
    )
    mock_http["install"](payload)
    provider = AnthropicProvider(make_config())
    events = await collect(provider)
    assert isinstance(events[-1], StreamDone)
    assert events[-1].truncated is True


async def test_anthropic_stream_without_message_stop_errors(mock_http):
    payload = sse(
        frame({"type": "message_start", "message": {}}, "message_start"),
        frame({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}, "content_block_start"),
        frame({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "x"}}, "content_block_delta"),
    )
    mock_http["install"](payload)
    provider = AnthropicProvider(make_config())
    events = []
    with pytest.raises(ProviderError, match="回复完成前中断"):
        async for event in provider.stream_chat(
            [ChatMessage(role="user", blocks=(TextBlock("hi"),))]
        ):
            events.append(event)
    assert not any(isinstance(e, StreamDone) for e in events)


async def test_anthropic_error_event_frame(mock_http):
    payload = sse(
        frame({"type": "error", "error": {"type": "overloaded_error", "message": "服务过载"}}, "error")
    )
    mock_http["install"](payload)
    provider = AnthropicProvider(make_config())
    with pytest.raises(ProviderError, match="服务过载"):
        async for _ in provider.stream_chat(
            [ChatMessage(role="user", blocks=(TextBlock("hi"),))]
        ):
            pass


async def test_anthropic_401_error(mock_http):
    mock_http["install"](status=401)
    provider = AnthropicProvider(make_config())
    with pytest.raises(ProviderError, match="认证失败"):
        async for _ in provider.stream_chat(
            [ChatMessage(role="user", blocks=(TextBlock("hi"),))]
        ):
            pass


async def test_aclose_idempotent(mock_http):
    mock_http["install"](ANTHROPIC_TEXT_STREAM)
    provider = AnthropicProvider(make_config())
    await provider.aclose()
    await provider.aclose()  # 第二次不应报错


# ---------- openai ----------


def openai_chunk(content: str | None = None, reasoning: str | None = None, finish: str | None = None) -> str:
    delta = {}
    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning_content"] = reasoning
    choice = {"index": 0, "delta": delta, "finish_reason": finish}
    return frame({"id": "c1", "object": "chat.completion.chunk", "choices": [choice]})


async def test_openai_stream_maps_content_and_reasoning(mock_http):
    payload = sse(
        openai_chunk(reasoning="想一下"),
        openai_chunk(content="你好"),
        openai_chunk(content="世界", finish="stop"),
        "data: [DONE]",
    )
    mock_http["install"](payload)
    provider = OpenAIProvider(make_config(protocol="openai", base_url="https://api.deepseek.com"))
    events = await collect(provider)
    assert [e for e in events if isinstance(e, ThinkingDelta)] == [ThinkingDelta("想一下")]
    assert [e for e in events if isinstance(e, TextDelta)] == [TextDelta("你好"), TextDelta("世界")]
    done = events[-1]
    assert isinstance(done, StreamDone)
    assert done.truncated is False
    # openai 历史只存 text，不回传 reasoning
    assert done.message.blocks == (TextBlock("你好世界"),)


async def test_openai_length_finish_marks_truncated(mock_http):
    payload = sse(
        openai_chunk(content="x", finish="length"),
        "data: [DONE]",
    )
    mock_http["install"](payload)
    provider = OpenAIProvider(make_config(protocol="openai", base_url="https://api.deepseek.com"))
    events = await collect(provider)
    assert isinstance(events[-1], StreamDone)
    assert events[-1].truncated is True


async def test_openai_missing_done_errors(mock_http):
    payload = sse(openai_chunk(content="x", finish="stop"))
    mock_http["install"](payload)
    provider = OpenAIProvider(make_config(protocol="openai", base_url="https://api.deepseek.com"))
    with pytest.raises(ProviderError, match="回复完成前中断"):
        async for _ in provider.stream_chat(
            [ChatMessage(role="user", blocks=(TextBlock("hi"),))]
        ):
            pass


async def test_openai_error_chunk(mock_http):
    payload = sse(frame({"error": {"message": "请求不合法", "type": "invalid_request_error"}}))
    mock_http["install"](payload)
    provider = OpenAIProvider(make_config(protocol="openai", base_url="https://api.deepseek.com"))
    with pytest.raises(ProviderError, match="请求不合法"):
        async for _ in provider.stream_chat(
            [ChatMessage(role="user", blocks=(TextBlock("hi"),))]
        ):
            pass


async def test_openai_request_body_and_headers(mock_http):
    payload = sse(openai_chunk(content="ok", finish="stop"), "data: [DONE]")
    mock_http["install"](payload)
    provider = OpenAIProvider(make_config(protocol="openai", base_url="https://api.deepseek.com"))
    history = ChatMessage(
        role="assistant",
        blocks=(ThinkingBlock("忽略我", "sig"), TextBlock("之前")),
    )
    _ = [e async for e in provider.stream_chat([history, ChatMessage(role="user", blocks=(TextBlock("hi"),))])]
    assert mock_http["url"].endswith("/v1/chat/completions")
    assert mock_http["headers"]["authorization"] == "Bearer test-key"  # httpx 头名规范化为小写
    assert mock_http["body"]["messages"] == [
        {"role": "assistant", "content": "之前"},  # ThinkingBlock 被忽略
        {"role": "user", "content": "hi"},
    ]
    assert mock_http["body"]["max_tokens"] == 8192
    assert mock_http["body"]["stream"] is True
