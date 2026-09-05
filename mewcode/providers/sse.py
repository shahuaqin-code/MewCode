"""共享 SSE 帧解析器：只分帧，不做 JSON 解析。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

import httpx


@dataclass
class SSEFrame:
    event: str | None  # event: 字段（无则 None）
    data: str          # 多行 data: 按 SSE 标准以 \n 连接合并


async def iter_sse(response: httpx.Response) -> AsyncIterator[SSEFrame]:
    """按 SSE 标准解析响应：识别 event/data 字段、合并多行 data、以空行分帧。

    只做帧级解析，不解 JSON；[DONE] 等协议级结束标记、JSON 解析、
    协议事件映射均在各 Provider 内部处理。
    """
    event: str | None = None
    data_lines: list[str] = []

    async for raw_line in response.aiter_lines():
        line = raw_line.rstrip("\r")
        if line == "":
            if data_lines:
                yield SSEFrame(event=event, data="\n".join(data_lines))
            event = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue  # SSE 注释行
        if line.startswith("event:"):
            event = line[len("event:"):].strip() or None
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].lstrip(" "))

    if data_lines:
        yield SSEFrame(event=event, data="\n".join(data_lines))
