"""SSE 帧解析器测试。"""

import httpx

from mewcode.providers.sse import SSEFrame, iter_sse


def make_response(payload: bytes) -> httpx.Response:
    return httpx.Response(
        200, content=payload, request=httpx.Request("POST", "https://example.test/")
    )


class ChunkedResponse(httpx.Response):
    """按指定块边界输出字节流，模拟网络分块到达。

    httpx 的 aiter_bytes 在存在 _content 属性时直接迭代缓存的 bytes，
    不经过 aiter_raw；删除该属性使其走 aiter_raw 分支。
    """

    def __init__(self, chunks: list[bytes]):
        super().__init__(200, request=httpx.Request("POST", "https://example.test/"))
        del self._content
        self._chunks = chunks

    async def aiter_raw(self):
        for chunk in self._chunks:
            yield chunk


async def collect(payload: bytes) -> list[SSEFrame]:
    return [frame async for frame in iter_sse(make_response(payload))]


async def test_simple_frame_with_event():
    payload = b'event: message\ndata: {"a": 1}\n\n'
    frames = await collect(payload)
    assert len(frames) == 1
    assert frames[0].event == "message"
    assert frames[0].data == '{"a": 1}'


async def test_frame_without_event_field():
    payload = b"data: hello\n\n"
    frames = await collect(payload)
    assert frames[0].event is None
    assert frames[0].data == "hello"


async def test_multi_line_data_merged_with_newline():
    payload = b'data: {"line1":\ndata: "line2"}\n\n'
    frames = await collect(payload)
    assert frames[0].data == '{"line1":\n"line2"}'


async def test_done_marker_is_ordinary_frame():
    payload = b"data: [DONE]\n\n"
    frames = await collect(payload)
    assert len(frames) == 1
    assert frames[0].data == "[DONE]"


async def test_last_frame_without_blank_line():
    payload = b"data: first\n\ndata: second"
    frames = await collect(payload)
    assert [f.data for f in frames] == ["first", "second"]


async def test_comment_lines_ignored():
    payload = b": keep-alive\ndata: real\n\n"
    frames = await collect(payload)
    assert len(frames) == 1
    assert frames[0].data == "real"


async def test_data_without_leading_space():
    payload = b"data:bare\n\n"
    frames = await collect(payload)
    assert frames[0].data == "bare"


async def test_frame_split_across_chunks():
    chunks = [b'data: {"te', b'xt": "hel', b'lo"}\n\n']
    response = ChunkedResponse(chunks)
    frames = [frame async for frame in iter_sse(response)]
    assert len(frames) == 1
    assert frames[0].data == '{"text": "hello"}'


async def test_crlf_line_endings():
    payload = b"event: x\r\ndata: 1\r\n\r\n"
    frames = await collect(payload)
    assert frames[0].event == "x"
    assert frames[0].data == "1"
