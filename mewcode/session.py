"""对话层：内存历史管理。"""

from __future__ import annotations

from mewcode.providers.base import ChatMessage, TextBlock


class Session:
    """一次会话的消息历史；仅在流正常结束后 commit，失败保持可重试状态。"""

    def __init__(self) -> None:
        self._messages: list[ChatMessage] = []

    def build_request(self, user_msg: str) -> list[ChatMessage]:
        """返回「历史 + 当前用户消息」快照；当前消息只出现一次。"""
        return [*self._messages, ChatMessage(role="user", blocks=(TextBlock(user_msg),))]

    def commit(self, user_msg: str, done_msg: ChatMessage) -> None:
        """流正常结束后把用户消息与完整助手消息追加进历史。"""
        self._messages.append(ChatMessage(role="user", blocks=(TextBlock(user_msg),)))
        self._messages.append(done_msg)

    @property
    def messages(self) -> list[ChatMessage]:
        """历史的副本。"""
        return list(self._messages)
