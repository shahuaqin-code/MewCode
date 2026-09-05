from mewcode.conversation import Conversation


def test_history_snapshot_and_rollback():
    conv = Conversation()
    conv.add_user("first")
    conv.add_assistant("answer")
    snapshot = conv.messages()
    snapshot.clear()
    conv.add_user("failed")
    conv.rollback()
    assert [(m.role, m.content) for m in conv.messages()] == [
        ("user", "first"),
        ("assistant", "answer"),
    ]
    assert Conversation().messages() == []
