# Copyright (C) 2026 Mehedi Maruf
# SPDX-License-Identifier: AGPL-3.0-or-later
# Contact: rsimplone@mehedimaruf.com (developer), license@mehedimaruf.com (licence)
# Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
# The domain probably expired because HE's TOO BROKE TO RENEW IT.
# Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
# and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"""Guided install: the plan is fixed, nothing from the page reaches a command, and rclone in a known place is found.
No test runs a real installer."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rsg import core, installer  # noqa: E402


class PlanTests(unittest.TestCase):
    def test_windows_prefers_winget_then_scoop_then_manual(self):
        with mock.patch.object(installer, "IS_WIN", True):
            with mock.patch.object(installer, "_which", lambda n: "C:/x/%s.exe" % n if n in ("winget", "scoop") else None):
                p = installer.plan()
                self.assertEqual((p["method"], p["can_run"]), ("winget", True))
                self.assertIn("Rclone.Rclone", p["command"])
            with mock.patch.object(installer, "_which", lambda n: "C:/x/scoop.cmd" if n == "scoop" else None):
                self.assertEqual(installer.plan()["method"], "scoop")
            with mock.patch.object(installer, "_which", lambda n: None):
                p = installer.plan()
                self.assertEqual((p["can_run"], p["command"], p["text"]), (False, [], ""))

    def test_unix_uses_brew_else_shows_script_without_running_it(self):
        with mock.patch.object(installer, "IS_WIN", False), mock.patch.object(installer.sys, "platform", "linux"):
            with mock.patch.object(installer, "_which", lambda n: "/opt/brew" if n == "brew" else None):
                self.assertEqual(installer.plan()["command"], ["/opt/brew", "install", "rclone"])
            with mock.patch.object(installer, "_which", lambda n: None):
                p = installer.plan()
                self.assertFalse(p["can_run"])
                self.assertEqual(p["text"], installer.LINUX_SCRIPT)
                with self.assertRaises(ValueError):
                    installer.start()

    def test_start_runs_only_the_planned_command_and_is_single_flight(self):
        fake = {"can_run": True, "command": ["tool", "install", "rclone"]}
        seen = []
        with mock.patch.object(installer, "plan", lambda: fake), \
                mock.patch.object(installer.threading, "Thread", lambda target, args, daemon: mock.Mock(start=lambda: seen.append(args))):
            installer._set(state="idle", tail=[], found="")
            self.assertEqual(installer.start()["state"], "running")
            self.assertEqual(seen, [(["tool", "install", "rclone"],)])
            with self.assertRaises(ValueError):
                installer.start()
        installer._set(state="idle")

    def test_output_is_tidied(self):
        self.assertEqual(installer._tidy("\r 10%\r\x1b[2K done \u2588\u2588"), "done")


class FindTests(unittest.TestCase):
    def test_finds_rclone_in_a_known_place_when_path_is_short(self):
        d = tempfile.mkdtemp()
        try:
            exe = os.path.join(d, "rclone.exe" if os.name == "nt" else "rclone")
            open(exe, "w").close()
            with mock.patch.object(core.shutil, "which", lambda n: None), mock.patch.object(core, "_known_rclone_places", lambda: ["/nope", exe]):
                self.assertEqual(core.find_rclone(""), exe)
            with mock.patch.object(core.shutil, "which", lambda n: None), mock.patch.object(core, "_known_rclone_places", lambda: ["/nope"]):
                self.assertIsNone(core.find_rclone(""))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
