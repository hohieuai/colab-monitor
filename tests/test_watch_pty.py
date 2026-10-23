"""`colab-monitor watch` in a real terminal: it draws, quits cleanly, and puts the terminal back."""

import os
import select
import signal
import subprocess
import sys
import threading
import time

import pytest

from colab_monitor.server import make_server

from .e2e.fixtures import build_data, sample_dashboard

fcntl = pytest.importorskip("fcntl")
pty = pytest.importorskip("pty")
termios = pytest.importorskip("termios")

ENTER_SCREEN = b"\x1b[?1049h"
LEAVE_SCREEN = b"\x1b[?1049l"
SHOW_CURSOR = b"\x1b[?25h"


def _controlling_terminal():
    """Make the pty the child's controlling terminal, so Ctrl-C sends it SIGINT."""
    os.setsid()
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)


class Terminal:
    """Runs `colab-monitor watch` on a pseudo-terminal and collects what it draws."""

    def __init__(self, args, home):
        self.master, slave = pty.openpty()
        self.saved = termios.tcgetattr(slave)
        env = {**os.environ, "HOME": str(home), "COLUMNS": "100", "LINES": "40", "TERM": "xterm-256color"}
        env.pop("NO_COLOR", None)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "colab_monitor", "watch", *args],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=env,
            preexec_fn=_controlling_terminal,
        )
        self.slave = slave
        self.output = b""

    def read_until(self, needle: bytes, count: int = 1, timeout: float = 15) -> bytes:
        """Read until `needle` has been drawn `count` times."""
        deadline = time.monotonic() + timeout
        while self.output.count(needle) < count:
            left = deadline - time.monotonic()
            if left <= 0:
                raise AssertionError(f"{needle!r} never appeared in {self.output[-2000:]!r}")
            ready, _, _ = select.select([self.master], [], [], left)
            if ready:
                try:
                    self.output += os.read(self.master, 65536)
                except OSError:  # the child closed the terminal
                    break
        return self.output

    def finish(self, timeout: float = 10) -> int:
        """Wait for the exit, reading all the while so a full terminal never blocks the child."""
        deadline = time.monotonic() + timeout
        while self.proc.poll() is None and time.monotonic() < deadline:
            self._drain(0.1)
        self._drain(0.2)
        return self.proc.wait(timeout=1)

    def _drain(self, wait: float) -> None:
        while select.select([self.master], [], [], wait)[0]:
            try:
                chunk = os.read(self.master, 65536)
            except OSError:
                return
            if not chunk:
                return
            self.output += chunk
            wait = 0

    def close(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        os.close(self.master)
        os.close(self.slave)


@pytest.fixture
def local_args(tmp_path):
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "train.log").write_text("epoch 3/10 loss=0.42\n")
    return [
        "--no-api",
        "--refresh",
        "1",
        "--history-dir",
        str(tmp_path / "history"),
        "--log-dir",
        str(tmp_path / "runs"),
        "--usage-log",
        str(tmp_path / "usage.jsonl"),
    ]


@pytest.fixture
def terminal_factory(tmp_path):
    made = []

    def make(args):
        made.append(Terminal(args, tmp_path))
        return made[-1]

    yield make
    for t in made:
        t.close()


def _assert_restored(t: Terminal):
    tail = t.output[t.output.rindex(ENTER_SCREEN) :]
    assert SHOW_CURSOR in tail and LEAVE_SCREEN in tail
    assert tail.rindex(LEAVE_SCREEN) > tail.rindex(b"Compute units")
    modes = termios.ECHO | termios.ICANON
    assert termios.tcgetattr(t.master)[3] & modes == t.saved[3] & modes  # echo and line mode are back


def test_draws_and_quits_on_q(terminal_factory, local_args):
    t = terminal_factory(local_args)
    out = t.read_until(b"q to quit")
    assert ENTER_SCREEN in out and b"Compute units" in out and b"train.log" in out
    assert b"30%" in out  # epoch 3/10
    os.write(t.master, b"q")
    assert t.finish() == 0
    _assert_restored(t)


def test_redraws_on_its_own(terminal_factory, local_args):
    t = terminal_factory(local_args)
    t.read_until(b"q to quit", count=2)  # --refresh 1
    os.write(t.master, b"q")
    assert t.finish() == 0


def test_ctrl_c_quits_cleanly(terminal_factory, local_args):
    t = terminal_factory(local_args)
    t.read_until(b"q to quit")
    os.write(t.master, b"\x03")
    assert t.finish() == 0
    assert b"Traceback" not in t.output
    _assert_restored(t)


def test_sigterm_quits_cleanly(terminal_factory, local_args):
    t = terminal_factory(local_args)
    t.read_until(b"q to quit")
    t.proc.send_signal(signal.SIGTERM)
    assert t.finish() == 0
    _assert_restored(t)


def test_reads_a_running_dashboard(terminal_factory, tmp_path):
    (tmp_path / "data").mkdir()
    app = sample_dashboard(build_data(tmp_path / "data"))
    server = make_server(app, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        t = terminal_factory(["--port", str(server.server_address[1]), "--refresh", "1"])
        out = t.read_until(b"from the dashboard")
        assert b"train-gpu" in out and b"NEEDS ATTENTION" in out
        os.write(t.master, b"q")
        assert t.finish() == 0
    finally:
        server.shutdown()
        server.server_close()
