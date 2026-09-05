"""UI 冒烟测试：FakeProvider 注入，验证三态渲染、禁用/恢复、选择页与退出清理。"""

import asyncio

from mewcode.config import ProviderConfig
from mewcode.providers.base import (
    ChatMessage,
    Provider,
    StreamDone,
    StreamEvent,
    TextBlock,
    TextDelta,
    ThinkingDelta,
)
from mewcode.ui import app as app_module
from mewcode.ui.app import MewCodeApp
from mewcode.ui.chat import ChatScreen
from mewcode.ui.picker import ProviderPickerScreen
from textual.widgets import Input, OptionList, Static


class FakeProvider(Provider):
    def __init__(self, config):
        self.config = config
        self.closed = False

    async def stream_chat(self, messages):
        await asyncio.sleep(0.05)  # 慢速化，便于观察生成中的禁用态
        yield ThinkingDelta("思考")
        await asyncio.sleep(0.05)
        yield TextDelta("你好")
        yield StreamDone(ChatMessage(role="assistant", blocks=(TextBlock("你好"),)))

    async def aclose(self):
        self.closed = True


class TruncatedProvider(FakeProvider):
    async def stream_chat(self, messages):
        yield TextDelta("被截断")
        yield StreamDone(
            ChatMessage(role="assistant", blocks=(TextBlock("被截断"),)), truncated=True
        )


class FailingProvider(FakeProvider):
    async def stream_chat(self, messages):
        from mewcode.providers.base import ProviderError

        yield TextDelta("前半")
        raise ProviderError("模拟网络错误")


def make_app(configs, provider_name=None, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(
            app_module, "PROTOCOLS", {"anthropic": FakeProvider, "openai": FakeProvider}
        )
    return MewCodeApp(configs, provider_name)


async def test_chat_flow_renders_three_states(monkeypatch):
    """FakeProvider 冒烟：思考暗色/回答正常渲染、禁用后恢复、历史落账。"""
    config = ProviderConfig(
        name="fake", protocol="anthropic", model="m", base_url="https://x", api_key="k"
    )
    app = make_app([config], monkeypatch=monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen  # ChatScreen 被 push 在默认屏幕之上
        assert isinstance(screen, ChatScreen)
        prompt = screen.query_one("#prompt", Input)
        prompt.value = "hello"
        prompt.post_message(Input.Submitted(prompt, "hello"))
        await pilot.pause()  # 让提交处理器执行
        assert prompt.disabled is True  # 生成期间禁止重复提交
        while screen._task is not None and not screen._task.done():
            await pilot.pause()
        assert prompt.disabled is False  # finally 恢复

        history = screen.query_one("#history")
        rendered = [str(w.render()) for w in history.query(Static)]
        joined = "\n".join(rendered)
        assert "hello" in joined
        assert "💭 思考" in joined
        assert "你好" in joined
        # 思考块与回答块为不同 widget，各自样式类
        assert history.query(".thinking")
        assert history.query(".answer")
        # 历史落账：用户 + 助手
        assert [m.role for m in app._session.messages] == ["user", "assistant"]


async def test_truncated_warning_shown(monkeypatch):
    config = ProviderConfig(
        name="fake", protocol="anthropic", model="m", base_url="https://x", api_key="k"
    )
    app = make_app([config], monkeypatch=monkeypatch)
    monkeypatch.setattr(app_module, "PROTOCOLS", {"anthropic": TruncatedProvider})
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        prompt = screen.query_one("#prompt", Input)
        prompt.value = "hi"
        prompt.post_message(Input.Submitted(prompt, "hi"))
        while screen._task is not None and not screen._task.done():
            await pilot.pause()
        history = screen.query_one("#history")
        joined = "\n".join(str(w.render()) for w in history.query(Static))
        assert "回答达到输出上限，已截断" in joined


async def test_provider_error_shows_and_history_unchanged(monkeypatch):
    config = ProviderConfig(
        name="fake", protocol="anthropic", model="m", base_url="https://x", api_key="k"
    )
    app = make_app([config], monkeypatch=monkeypatch)
    monkeypatch.setattr(app_module, "PROTOCOLS", {"anthropic": FailingProvider})
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        prompt = screen.query_one("#prompt", Input)
        prompt.value = "hi"
        prompt.post_message(Input.Submitted(prompt, "hi"))
        while screen._task is not None and not screen._task.done():
            await pilot.pause()
        history = screen.query_one("#history")
        joined = "\n".join(str(w.render()) for w in history.query(Static))
        assert "模拟网络错误" in joined
        assert app._session.messages == []  # 失败不追加历史
        assert prompt.disabled is False


async def test_picker_screen_selects_provider(monkeypatch):
    """多配置无 --provider → 选择页 → 选定后进入对话。"""
    configs = [
        ProviderConfig(name="a", protocol="anthropic", model="m1", base_url="https://x", api_key="k"),
        ProviderConfig(name="b", protocol="anthropic", model="m2", base_url="https://x", api_key="k"),
    ]
    app = make_app(configs, monkeypatch=monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ProviderPickerScreen)
        picker = app.screen.query_one("#picker", OptionList)
        picker.highlighted = 1
        picker.action_select()
        for _ in range(5):
            if isinstance(app.screen, ChatScreen):
                break
            await pilot.pause()
        chat = app.screen
        assert isinstance(chat, ChatScreen)
        assert chat.provider.config.name == "b"  # 选中的配置被实例化


async def test_quit_closes_provider_and_exits(monkeypatch):
    config = ProviderConfig(
        name="fake", protocol="anthropic", model="m", base_url="https://x", api_key="k"
    )
    app = make_app([config], monkeypatch=monkeypatch)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ChatScreen)
        provider = screen.provider
        assert isinstance(provider, FakeProvider)
        await screen.action_quit()  # 内部：取消任务 → await → aclose → exit
        assert provider.closed is True  # aclose 已调用
