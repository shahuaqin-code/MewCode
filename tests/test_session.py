"""Session 测试。"""

from mewcode.providers.base import ChatMessage, TextBlock
from mewcode.session import Session


def test_build_request_includes_history_and_current_once():
    s = Session()
    req = s.build_request("第一问")
    assert len(req) == 1
    assert req[0].role == "user"
    assert req[0].blocks == (TextBlock("第一问"),)

    s.commit("第一问", ChatMessage(role="assistant", blocks=(TextBlock("答一"),)))
    req2 = s.build_request("第二问")
    assert [m.role for m in req2] == ["user", "assistant", "user"]
    assert req2[-1].blocks == (TextBlock("第二问"),)


def test_failed_turn_does_not_append_history():
    s = Session()
    s.commit("问一", ChatMessage(role="assistant", blocks=(TextBlock("答一"),)))
    # 第二轮请求后失败（未 commit），历史不变
    _ = s.build_request("问二")
    assert len(s.messages) == 2
    assert s.messages[-1].blocks == (TextBlock("答一"),)


def test_commit_appends_user_and_assistant_in_order():
    s = Session()
    s.commit("问", ChatMessage(role="assistant", blocks=(TextBlock("答"),)))
    assert [m.role for m in s.messages] == ["user", "assistant"]
    assert s.messages[0].blocks == (TextBlock("问"),)
    assert s.messages[1].blocks == (TextBlock("答"),)


def test_build_request_snapshot_is_isolated():
    s = Session()
    req = s.build_request("问")
    s.commit("问", ChatMessage(role="assistant", blocks=(TextBlock("答"),)))
    assert len(req) == 1  # 快照不受后续 commit 影响
