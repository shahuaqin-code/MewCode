"""CLI 入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mewcode.config import ConfigError, load_config
from mewcode.ui.app import MewCodeApp

DEFAULT_CONFIG = Path.home() / ".mewcode" / "config.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mewcode", description="MewCode — 终端 AI 助手")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help=f"配置文件路径（默认 {DEFAULT_CONFIG}）",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="指定使用的 provider 名称（缺省时交互选择）",
    )
    args = parser.parse_args(argv)

    try:
        configs = load_config(args.config)
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 1

    if args.provider is not None and not any(c.name == args.provider for c in configs):
        names = "、".join(c.name for c in configs)
        print(f"错误: 未找到名为 {args.provider} 的 provider（可用: {names}）", file=sys.stderr)
        return 1

    app = MewCodeApp(configs, args.provider)
    app.run()
    return app.return_value or 0


if __name__ == "__main__":
    raise SystemExit(main())
