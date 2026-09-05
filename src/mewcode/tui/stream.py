"""Asynchronous streaming lifecycle and elapsed-time feedback."""

import asyncio
import time
from contextlib import aclosing

from rich.text import Text
from textual.widgets import Static

from .view import error_block, render_markdown


class StreamMixin:
    async def _consume_stream(self):
        try:
            async with aclosing(self.provider.stream(self.conv.messages())) as stream:
                async for event in stream:
                    if event.err is not None:
                        self._finish(event.err)
                        return
                    if event.text:
                        self.cur_reply += event.text
                        self.query_one("#reply", Static).update(Text(self.cur_reply))
                        viewport = self.query_one("#streaming")
                        if viewport.is_vertical_scroll_end:
                            viewport.scroll_end(animate=False)
                    if event.done:
                        self._finish()
                        return
            self._finish(RuntimeError("Incomplete stream"))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._finish(exc)

    def _tick(self):
        elapsed = time.monotonic() - self.turn_start
        frame = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(elapsed * 10) % 10]
        self.query_one("#progress", Static).update(
            Text(f"{frame} Imagining… ({int(elapsed)}s)", style="cyan")
        )

    def _finish(self, error=None):
        from .app import SessionState

        elapsed = time.monotonic() - self.turn_start
        if error is None:
            self.history.append(render_markdown(self.cur_reply))
            self.conv.add_assistant(self.cur_reply)
        else:
            if self.cur_reply:
                self.history.append(Text("● " + self.cur_reply))
            self.history.append(error_block(error))
            self.conv.rollback()
        self.history.append(
            Text(
                f"Completed in {elapsed:.1f}s"
                if error is None
                else f"Failed after {elapsed:.1f}s",
                style="dim",
            )
        )
        self._timer.stop()
        self._timer = None
        self._stream_task = None
        self.cur_reply = ""
        self.query_one("#reply", Static).update("")
        self.query_one("#streaming").display = False
        self.query_one("#progress").display = False
        self.state = SessionState.IDLE
        self.editor.read_only = False
        self.editor.focus()
