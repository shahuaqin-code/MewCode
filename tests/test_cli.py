import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "content", [None, "providers: []", "providers: [api_key: secret"]
)
def test_cli_invalid_configuration(tmp_path, content):
    if content is not None:
        folder = tmp_path / ".mewcode"
        folder.mkdir()
        (folder / "config.yaml").write_text(content)
    result = subprocess.run(
        [sys.executable, "-m", "mewcode"], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "配置错误" in result.stderr
    assert "Traceback" not in result.stderr and "secret" not in result.stderr


@pytest.mark.skipif(os.name != "posix", reason="PTY verification requires POSIX")
@pytest.mark.parametrize("keys", [b"/exit\r", b"\x03"])
def test_real_terminal_exit(tmp_path, keys):
    import pty
    import select
    import termios
    import time

    folder = tmp_path / ".mewcode"
    folder.mkdir()
    (folder / "config.yaml").write_text(
        "providers:\n  - name: test\n    protocol: openai\n"
        "    api_key: fake-credential\n    model: test-model\n"
    )
    master, slave = pty.openpty()
    termios.tcsetwinsize(slave, (30, 90))
    before = termios.tcgetattr(slave)
    proc = subprocess.Popen(
        [sys.executable, "-m", "mewcode"],
        cwd=tmp_path,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={**os.environ, "TERM": "xterm-256color"},
    )
    output = b""
    startup = b""
    try:
        deadline = time.monotonic() + 10
        sent = False
        key_index = 0
        next_key_at = 0.0
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.05)[0]:
                chunk = os.read(master, 65536)
                output += chunk
                if b"\x1b[6n" in chunk:
                    os.write(master, b"\x1b[1;1R")
            if (
                not sent
                and b"Send a message" in output
                and b"MewCode v0.1.0" in output
                and b"( o.o )" in output
                and time.monotonic() >= next_key_at
            ):
                if key_index == 0:
                    startup = output
                os.write(master, keys[key_index : key_index + 1])
                key_index += 1
                sent = key_index == len(keys)
                next_key_at = time.monotonic() + 0.15
            if proc.poll() is not None:
                break
        assert sent, output.decode(errors="replace")
        assert b"MewCode v0.1.0" in startup
        assert b"( o.o )" in startup
        assert proc.poll() == 0, output.decode(errors="replace")
        assert termios.tcgetattr(slave) == before
        assert b"fake-credential" not in output and b"Traceback" not in output
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        os.close(master)
        os.close(slave)
