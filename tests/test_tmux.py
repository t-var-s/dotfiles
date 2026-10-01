"""Exercise actual key bindings in an isolated tmux server and attached PTY.

Set TMUX_BINARY to test another existing binary, including tmux 1.8.
"""
import errno
import fcntl
import os
from pathlib import Path
import pty
import select
import shlex
import shutil
import signal
import struct
import subprocess
import termios
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TmuxTests(unittest.TestCase):
    def command(self, *arguments, check=True):
        result = subprocess.run(
            [self.binary, "-L", self.socket, *arguments], env=self.env,
            cwd=self.home, capture_output=True, text=True, timeout=5,
        )
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def drain(self):
        while select.select([self.terminal], [], [], 0)[0]:
            try:
                if not os.read(self.terminal, 65536):
                    break
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.drain()
            if predicate():
                return
            time.sleep(0.02)
        self.fail("Timed out waiting for tmux state")

    def panes(self):
        output = self.command("list-panes", "-t", "test:0", "-F",
                              "#{pane_id}\t#{pane_pid}\t#{pane_width}\t#{pane_active}\t#{pane_current_path}")
        return [line.split("\t") for line in output.splitlines()]

    def key(self, key):
        os.write(self.terminal, b"\x02" + key.encode())

    def setUp(self):
        self.binary = shutil.which(os.environ.get("TMUX_BINARY", "tmux"))
        if not self.binary:
            self.skipTest("Requested tmux binary is not available")
        self.temp_base = Path(os.environ.get("TMPDIR", "/tmp")).resolve()
        self.run_tmp = Path(subprocess.check_output(
            ["mktemp", "-d", str(self.temp_base / "codex-tmux-tests.XXXXXX")], text=True
        ).strip()).resolve()
        (self.run_tmp / ".codex-task-temp").touch()
        self.addCleanup(self.cleanup)
        self.home = self.run_tmp / "home"
        self.home.mkdir()
        shutil.copy2(ROOT / ".tmux.conf", self.home / ".tmux.conf")
        test_bin = self.run_tmp / "bin"
        test_bin.mkdir()
        (test_bin / "tmux").symlink_to(self.binary)
        self.env = dict(os.environ, HOME=str(self.home), TMUX="", TERM="xterm-256color",
                        PATH=str(test_bin) + ":" + os.environ["PATH"])
        self.socket = "dotfiles-test-" + self.run_tmp.name
        self.assertEqual(self.command("-f", str(self.home / ".tmux.conf"), "new-session",
                                      "-d", "-s", "test", "-x", "160", "-y", "40",
                                      "exec /bin/sh"), "")
        self.command("set-option", "-g", "default-shell", "/bin/sh")
        self.client_pid, self.terminal = pty.fork()
        if self.client_pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 160, 0, 0))
            os.chdir(self.home)
            os.execve(self.binary, [self.binary, "-L", self.socket, "attach-session", "-t", "test"], self.env)
        self.wait_for(lambda: self.command("display-message", "-p", "#{session_attached}") == "1")
        # 1.8 may accept new-session before its asynchronous startup config finishes.
        self.wait_for(lambda: "window_panes" in self.command("list-keys"))

    def cleanup(self):
        if hasattr(self, "socket"):
            self.command("kill-server", check=False)
        if hasattr(self, "terminal"):
            os.close(self.terminal)
            finished, _ = os.waitpid(self.client_pid, os.WNOHANG)
            if not finished:
                try:
                    os.kill(self.client_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(self.client_pid, 0)
        target = self.run_tmp.resolve()
        forbidden = {Path("/"), Path.home().resolve(), ROOT, self.temp_base}
        if os.environ.get("CODEX_HOME"):
            forbidden.add(Path(os.environ["CODEX_HOME"]).resolve())
        if (target in forbidden or target.parent != self.temp_base
                or not target.name.startswith("codex-tmux-tests.")
                or not (target / ".codex-task-temp").is_file()):
            raise RuntimeError(f"Refusing cleanup; test files remain at {target}")
        subprocess.run(["/bin/rm", "-rf", str(target)], check=True)

    def test_mouse_and_reload(self):
        # Probe capabilities, so the same test runs against legacy and modern tmux.
        probe = subprocess.run([self.binary, "-L", self.socket, "show-options", "-g", "mouse"],
                               env=self.env, capture_output=True, timeout=5)
        options = ["mouse"] if probe.returncode == 0 else [
            "mouse-select-pane", "mouse-resize-pane", "mouse-select-window", "mode-mouse"
        ]
        for option in options:
            with self.subTest(option=option):
                scope = "-gwv" if option == "mode-mouse" else "-gv"
                self.assertEqual(self.command("show-options", scope, option), "on")
                self.command("set-option", "-g", option, "off")
        before = self.panes()
        self.key("r")
        self.wait_for(lambda: all(self.command("show-options", "-gwv" if option == "mode-mouse" else "-gv", option) == "on"
                                  for option in options))
        self.assertEqual(self.panes(), before)
        self.assertEqual(self.command("show-options", "-gv", "status-left"), "")

    def test_centered_workspace_navigation_zoom_and_guard(self):
        work = self.home / 'work "quotes" and \'apostrophes\''
        work.mkdir()
        os.write(self.terminal, ("cd " + shlex.quote(str(work)) + "\n").encode())
        self.wait_for(lambda: self.panes()[0][4] == str(work))
        original = self.panes()[0]
        self.key("m")
        self.wait_for(lambda: len(self.panes()) == 3 and self.panes()[1][3] == "1")
        self.wait_for(lambda: all(pane[4] == str(work) for pane in self.panes()))
        panes = self.panes()
        self.assertEqual(panes[1][:2], original[:2])  # Original pane and shell PID.
        width = sum(int(pane[2]) for pane in panes) + 2  # Include borders.
        for pane, fraction in zip(panes, (0.2, 0.6, 0.2)):
            self.assertLessEqual(abs(int(pane[2]) - width * fraction), 3)
        self.key("h")
        self.wait_for(lambda: self.panes()[0][3] == "1")
        self.key("l")
        self.wait_for(lambda: self.panes()[1][3] == "1")
        self.key("z")
        self.wait_for(lambda: int(self.panes()[1][2]) == width)
        self.key("z")
        self.wait_for(lambda: self.panes()[1][2] == panes[1][2])
        before = self.panes()
        layout = self.command("display-message", "-p", "#{window_layout}")
        self.key("m")
        self.wait_for(lambda: "Layout already has multiple panes" in self.command("show-messages"))
        self.assertEqual(self.panes(), before)
        self.assertEqual(self.command("display-message", "-p", "#{window_layout}"), layout)
        self.key("r")
        self.wait_for(lambda: "Config reloaded" in self.command("show-messages"))
        self.assertEqual(self.panes(), before)

    def test_vertical_navigation_and_existing_layout_guard(self):
        self.command("split-window", "-v", "exec /bin/sh")
        self.key("k")
        self.wait_for(lambda: self.panes()[0][3] == "1")
        self.key("j")
        self.wait_for(lambda: self.panes()[1][3] == "1")
        before = self.panes()
        self.key("m")
        self.wait_for(lambda: "Layout already has multiple panes" in self.command("show-messages"))
        self.assertEqual(self.panes(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
