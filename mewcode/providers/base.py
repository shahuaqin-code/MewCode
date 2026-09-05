"""Provider 抽象与流式事件类型。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

from mewcode.config import ProviderConfig


class ProviderError(Exception):
    """调用 API 失败，message 为面向用户的中文可读信息。"""


# ---------- 会话消息（有序内容块） ----------

@dataclass
class ThinkingBlock:
    text: str                     # 思考文本（可为空字符串）
    signature: str | None = None  # 该块签名；无则序列化时省略字段，不写 null、不伪造


@dataclass
class TextBlock:
    text: str


ContentBlock = ThinkingBlock | TextBlock


@dataclass
class ChatMessage:
    role: str                       # "user" | "assistant"
    blocks: tuple[ContentBlock, ...]  # 有序内容块，顺序与 API 返回一致；多个 thinking 块不合并


# ---------- 流式事件 ----------

@dataclass
class ThinkingDelta:
    text: str  # 思考增量 → TUI 暗色斜体渲染


@dataclass
class TextDelta:
    text: str  # 回答增量 → TUI 正常渲染


@dataclass
class StreamDone:
    message: ChatMessage    # 完整助手消息（有序内容块），交回 Session 存历史
    truncated: bool = False  # True 表示因输出上限被截断 → TUI 显示截断提示


StreamEvent = ThinkingDelta | TextDelta | StreamDone


class Provider(ABC):
    """所有后端的统一抽象接口。"""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    async def stream_chat(
        self, messages: list[ChatMessage],
    ) -> AsyncIterator[StreamEvent]:
        """发送历史消息（含当前用户消息），流式产出事件。

        流正常结束（收到协议结束事件）时产出恰好一次 StreamDone 后返回；
        流内 error 事件、连接意外断开、超时、HTTP 错误一律抛 ProviderError，
        不得产出 StreamDone。
        """

    @abstractmethod
    async def aclose(self) -> None:
        """关闭底层 httpx AsyncClient；须在在途请求结束后调用。"""
