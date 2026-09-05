from mewcode.llm import Message


class Conversation:
    """In-memory history; roll back unsuccessful turns to keep alternating roles."""

    def __init__(self) -> None:
        self._messages: list[Message] = []

    def add_user(self, text: str) -> None:
        self._messages.append(Message("user", text))

    def add_assistant(self, text: str) -> None:
        self._messages.append(Message("assistant", text))

    def rollback(self) -> None:
        if self._messages and self._messages[-1].role == "user":
            self._messages.pop()

    def messages(self) -> list[Message]:
        return list(self._messages)
