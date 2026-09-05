"""Fixed application resources."""

SYSTEM_PROMPT = (
    "You are MewCode, a helpful terminal AI assistant. "
    "Respond clearly in the user's language. Use Markdown where useful. "
    "You can discuss code, but cannot access files or execute tools."
)
CAT_BANNER = r""" /\_/\
( o.o )
 > ^ <"""


def render_banner(version: str, cwd: str) -> str:
    return f"{CAT_BANNER}\nMewCode v{version}\n{cwd}\nReady — let's make something."
