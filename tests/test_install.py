#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Install under a temporary user directory; fake only the GitHub download."""
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"


class Installation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="yessir-install-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "user home"
        self.home.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), TMPDIR=str(self.root))
        self.env.pop("TMUX", None)
        self.env.pop("TMUX_PANE", None)

    def run_install(self, *args, piped=False):
        if piped:
            command = ["bash", "-s", "--", *args]
            source = INSTALLER.read_text()
        else:
            command = ["bash", str(INSTALLER), *args]
            source = None
        return subprocess.run(command, input=source, text=True, capture_output=True, env=self.env)

    def assert_installed(self, prefix):
        for name in ("yessir", "claude-tmux-yes"):
            path = prefix / "bin" / name
            self.assertEqual(path.read_bytes(), (ROOT / "bin" / name).read_bytes())
            self.assertEqual(path.stat().st_mode & 0o777, 0o755)
        self.assertEqual((prefix / "share/yessir/LICENSE").read_bytes(), (ROOT / "LICENSE").read_bytes())
        help_result = subprocess.run([str(prefix / "bin/yessir"), "--help"],
                                     env=self.env, text=True, capture_output=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        result = subprocess.run([str(prefix / "bin/yessir"), "--on"],
                                env=self.env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("run inside tmux", result.stderr)
        self.assertNotIn("helper missing", result.stderr)

    def fake_download(self, ref="main", failure=False):
        archive = self.root / "download.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for relative in ("bin/yessir", "bin/claude-tmux-yes", "LICENSE"):
                tar.add(ROOT / relative, arcname="yessir-source/" + relative)
        tools = self.root / "tools"
        tools.mkdir()
        script = tools / "curl"
        script.write_text("#!/bin/sh\n" + (
            "exit 22\n" if failure else
            "found=0\noutput=''\nwhile [ \"$#\" -gt 0 ]; do\n"
            f"  if [ \"$1\" = {shlex.quote('https://codeload.github.com/gsiros/yessir/tar.gz/' + ref)} ]; then found=1; fi\n"
            "  if [ \"$1\" = '--output' ]; then shift; output=\"$1\"; fi\n"
            "  shift\ndone\n[ \"$found\" = 1 ] && [ -n \"$output\" ] || exit 23\n"
            f"cp -- {shlex.quote(str(archive))} \"$output\"\n"
        ))
        script.chmod(0o755)
        self.env["PATH"] = str(tools) + os.pathsep + self.env["PATH"]

    def test_local_default_and_update(self):
        prefix = self.home / ".local"
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_installed(prefix)
        (prefix / "bin/yessir").write_text("old version")
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_installed(prefix)
        self.assertEqual(list(self.root.glob("yessir-install.*")), [])

    def test_custom_prefix_and_path_message(self):
        prefix = self.home / "my tools"
        result = self.run_install("--prefix", str(prefix))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_installed(prefix)
        self.assertIn("Add this command", result.stdout)
        self.assertFalse((self.home / ".bashrc").exists())
        self.assertFalse((self.home / ".tmux.conf").exists())

    def test_piped_installer_downloads_source(self):
        self.fake_download()
        result = self.run_install(piped=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_installed(self.home / ".local")

    def test_reference_selects_download_even_from_checkout(self):
        self.fake_download(ref="feature/test")
        result = self.run_install("--ref", "feature/test")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_installed(self.home / ".local")

    def test_failed_download_leaves_existing_files(self):
        self.fake_download(failure=True)
        prefix = self.home / ".local"
        (prefix / "bin").mkdir(parents=True)
        existing = prefix / "bin/yessir"
        existing.write_text("keep me")
        result = self.run_install(piped=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(existing.read_text(), "keep me")
        self.assertFalse((prefix / "bin/claude-tmux-yes").exists())
        self.assertEqual(list(self.root.glob("yessir-install.*")), [])

    def test_invalid_arguments(self):
        for args in (("--prefix",), ("--prefix", ""), ("--ref",),
                     ("--ref", "../bad"), ("--ref", "--bad"), ("--unknown",)):
            with self.subTest(args=args):
                result = self.run_install(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.home / ".local").exists())


if __name__ == "__main__":
    unittest.main()
