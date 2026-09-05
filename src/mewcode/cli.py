"""Load the project configuration and restore a readable terminal transcript."""

import sys

from rich.console import Console

from mewcode.config import ConfigError, load
from mewcode.tui import MewCodeApp


def main() -> None:
    try:
        config = load(".mewcode/config.yaml")
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        raise SystemExit(1) from None
    app = MewCodeApp(config.providers)
    try:
        result = app.run(inline=True, inline_no_clear=False)
    except KeyboardInterrupt:
        result = None
    except Exception:
        print("界面运行失败，请检查终端环境。", file=sys.stderr)
        raise SystemExit(1) from None
    # RichLog is an in-app viewport. Replay after terminal restoration so all
    # completed blocks remain available in native terminal/tmux scrollback.
    console = Console()
    for block in app.transcript:
        console.print(block)
    if result:
        raise SystemExit(result)
