import asyncio
import time

import pytest
from textual.widgets import Static

from mewcode.config import ProviderConfig
from mewcode.llm import StreamEvent
from mewcode.tui import MewCodeApp, SessionState


class FakeProvider:
    def __init__(self, cfg):
        self.name, self.model = cfg.name, cfg.model
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self.requests = []
        self.fail = False
        self.closed = False
        self.cancelled = False

    async def stream(self, messages):
        self.requests.append(messages)
        self.started.set()
        try:
            await self.release.wait()
            yield StreamEvent(text="**hello**\n\n```python\nprint(1)\n```\n- item")
            if self.fail:
                yield StreamEvent(err=RuntimeError("secret"))
            else:
                yield StreamEvent(done=True)
        finally:
            self.cancelled = True

    async def aclose(self):
        self.closed = True


@pytest.fixture
def configs(monkeypatch):
    monkeypatch.setattr("mewcode.tui.app.new_provider", FakeProvider)
    return [
        ProviderConfig("one", "openai", "secret", "model1"),
        ProviderConfig("two", "anthropic", "secret", "model2"),
    ]


async def test_selection(configs):
    app = MewCodeApp(configs)
    async with app.run_test() as pilot:
        assert app.state == SessionState.SELECTING
        await pilot.press("down", "enter")
        assert app.state == SessionState.IDLE
        assert app.provider.name == "two"
        assert app.provider.model == "model2"


async def test_multiline_timer_history_recovery_and_resize(configs):
    app = MewCodeApp(configs[:1])
    async with app.run_test(size=(90, 30)) as pilot:
        await pilot.press("h", "i", "alt+enter", "x", "enter")
        await app.provider.started.wait()
        assert app.state == SessionState.STREAMING
        assert app.editor.text == "" and app.editor.read_only
        assert app.provider.requests[0][-1].content == "hi\nx"
        app.turn_start = time.monotonic() - 5
        app._tick()
        assert "(5s)" in str(app.query_one("#progress", Static).render())
        await app.submit("ignored")
        assert len(app.provider.requests) == 1
        app.provider.release.set()
        await pilot.pause()
        assert app.state == SessionState.IDLE
        assert len(app.conv.messages()) == 2
        assert not app.editor.read_only
        await pilot.resize_terminal(35, 20)
        await pilot.pause()
        assert app.editor.region.width <= 35
        assert app.history.virtual_size.width <= app.history.size.width
        app.provider.fail = True
        await app.submit("failure")
        await pilot.pause()
        assert len(app.conv.messages()) == 2
        assert "secret" not in str(app.history.blocks)
        app.provider.fail = False
        await app.submit("next")
        await pilot.pause()
        assert len(app.provider.requests[-1]) == 3
        assert len(app.conv.messages()) == 4
        app.save_screenshot(filename="mewcode-tui.svg", path="/tmp")
        await app.submit("/exit")
        assert app.provider.closed


async def test_ctrl_c_during_wait(configs):
    app = MewCodeApp(configs[:1])
    async with app.run_test() as pilot:
        await app.submit("wait")
        await app.provider.started.wait()
        await pilot.press("ctrl+c")
        assert app.provider.closed and app.provider.cancelled
        assert app._stream_task.done()
