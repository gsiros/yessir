#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Regression checks and a real tmux/PTY integration test; no model requests."""
import ctypes
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import select
import shlex
import subprocess
import sys
import tempfile
import time
import tty
import unittest

HELPER = Path(__file__).resolve().parents[1] / "bin/claude-tmux-yes"
loader = importlib.machinery.SourceFileLoader("claude_tmux_yes", str(HELPER))
spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)

BASH = """Bash command
  printf hello
Do you want to proceed?
❯ 1. Yes
  2. Yes, and switch to auto mode
  3. No
Esc to cancel · Tab to amend
"""
EDIT = """Edit file
  +hello
Do you want to make this edit to example.py?
❯ 1. Yes
  2. Yes, and allow all edits this session
  3. No
Esc to cancel
"""
CHAT = "Claude Code\n❯ Write me a function\nManual mode\n"


class Recognition(unittest.TestCase):
    def test_command_and_edit(self):
        for screen in (BASH, EDIT, EDIT.replace("make this edit to", "create"),
                       EDIT.replace("make this edit to", "overwrite"),
                       EDIT.replace("example.py?", "very-long-name\n  .py?"),
                       BASH.replace("❯ 1. Yes", "❯ Yes"),
                       "╭────────╮\n" + "\n".join("│ " + x + " │" for x in BASH.splitlines()) + "\n╰────────╯\n"):
            with self.subTest(screen=screen):
                self.assertIsNotNone(helper.approval_screen(screen))

    def test_does_not_submit_other_dialogs_or_chat(self):
        for screen in (CHAT, BASH + CHAT, BASH.replace("❯ 1. Yes", "  1. Yes").replace("  3. No", "❯ 3. No"),
                       BASH.replace("❯ 1. Yes", "❯ 1. Yes, and switch to auto mode"),
                       "Do you trust this folder?\n❯ 1. Yes, I trust this folder\n  2. No\nEsc to cancel\n",
                       "Which style?\n❯ 1. Yes\n  2. No\nEsc to cancel\n",
                       BASH.replace("Esc to cancel", "tell Claude what to do next\nEsc to cancel"),
                       BASH.replace("Esc to cancel", "")):
            with self.subTest(screen=screen):
                self.assertIsNone(helper.approval_screen(screen))


def fixture(root):
    # A local terminal fixture with the same process name; it never runs commands.
    ctypes.CDLL(None).prctl(15, b"claude", 0, 0, 0)
    tty.setraw(sys.stdin.fileno())
    root = Path(root)
    screen = None
    (root / "ready").write_text(str(os.getpid()))
    while not (root / "exit").exists():
        desired = (root / "screen").read_text()
        if desired != screen:
            sys.stdout.write("\x1b[2J\x1b[H" + desired.replace("\n", "\r\n"))
            sys.stdout.flush()
            screen = desired
        if select.select([sys.stdin], [], [], 0.05)[0]:
            data = os.read(sys.stdin.fileno(), 1024)
            with (root / "keys").open("ab") as log:
                log.write(data)
    sys.stdout.write("\x1b[2J\x1b[Hfixture ended\r\n")
    sys.stdout.flush()


class Integration(unittest.TestCase):
    def test_tmux_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix="claude-yes-test-") as directory:
            root = Path(directory)
            socket = str(root / "tmux.sock")
            tmux = ["tmux", "-S", socket]
            home = root / "home"
            home.mkdir()
            env = dict(os.environ, HOME=str(home))
            env.pop("TMUX", None)
            env.pop("TMUX_PANE", None)
            def run(*args):
                return subprocess.run([*tmux, *args], env=env, text=True, capture_output=True, check=True)
            def cli(action):
                return subprocess.run([sys.executable, str(HELPER), action, "--socket", socket,
                                       "--pane", pane], env=env, text=True, capture_output=True)
            def wait_for(predicate, timeout=4):
                end = time.monotonic() + timeout
                while time.monotonic() < end:
                    if predicate():
                        return
                    time.sleep(0.05)
                screen = run("capture-pane", "-p", "-t", pane).stdout
                self.fail("timed out waiting for terminal fixture:\n" + screen)
            def keys():
                return (root / "keys").read_bytes() if (root / "keys").exists() else b""
            (root / "screen").write_text(CHAT)
            try:
                run("-f", "/dev/null", "new-session", "-d", "-s", "test", "-x", "100", "-y", "35", "/bin/sh")
                pane = run("display-message", "-p", "#{pane_id}").stdout.strip()
                self.assertNotEqual(cli("on").returncode, 0, "must refuse a shell")
                launch = shlex.join([sys.executable, str(Path(__file__).resolve()), "fixture", directory])
                run("send-keys", "-t", pane, launch, "Enter")
                wait_for(lambda: (root / "ready").exists())
                enabled = cli("on")
                self.assertEqual(enabled.returncode, 0, enabled.stderr)
                # The wrapper finds both its sibling helper and the current pane.
                wrapper_output = root / "wrapper-result"
                wrapper_command = shlex.join([str(HELPER.with_name("yessir")), "--status"])
                run("run-shell", wrapper_command + " > " + shlex.quote(str(wrapper_output)))
                self.assertEqual(wrapper_output.read_text().strip(),
                                 f"Claude approval helper: ON for {pane}")
                time.sleep(0.6)
                self.assertEqual(keys(), b"", "must not send Enter to chat")
                (root / "screen").write_text(BASH)
                wait_for(lambda: keys() == b"\r")
                time.sleep(0.8)
                self.assertEqual(keys(), b"\r", "must send once to an unchanged prompt")
                # A different approval can follow immediately, without an idle chat screen.
                (root / "screen").write_text(EDIT)
                wait_for(lambda: keys() == b"\r\r")
                run("copy-mode", "-t", pane)
                (root / "screen").write_text(BASH.replace("printf hello", "printf second"))
                time.sleep(0.8)
                self.assertEqual(keys(), b"\r\r", "must pause in tmux copy mode")
                run("send-keys", "-t", pane, "-X", "cancel")
                wait_for(lambda: keys() == b"\r\r\r")
                self.assertEqual(cli("toggle").returncode, 0)
                (root / "screen").write_text(EDIT.replace("example.py", "another.py"))
                time.sleep(0.8)
                self.assertEqual(keys(), b"\r\r\r", "off must stop injection")
                self.assertIn("OFF", cli("status").stdout)
                self.assertEqual(cli("toggle").returncode, 0)
                wait_for(lambda: keys() == b"\r\r\r\r")
                (root / "exit").touch()
                wait_for(lambda: "OFF" in cli("status").stdout)
                self.assertEqual(keys(), b"\r\r\r\r")
            finally:
                subprocess.run([*tmux, "kill-server"], env=env, capture_output=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "fixture":
        fixture(sys.argv[2])
    else:
        unittest.main()
