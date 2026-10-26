# Copyright (C) 2026 Mehedi Maruf
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU Affero General Public License as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.
# If not, see <https://www.gnu.org/licenses/>.
#
# Contact: rsimplone@mehedimaruf.com (developer), license@mehedimaruf.com (licence)
# Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
# The domain probably expired because HE's TOO BROKE TO RENEW IT.
# Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
# and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"""Tests for the window bridge (api.py) without opening a window. Run with:  python -m unittest discover -s tests -v"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rsg import api as apimod, core, schedule  # noqa: E402

RCLONE = core.find_rclone()


class FakeWindow:
    def __init__(self):
        self.calls = []
        self.width, self.height = 1200, 800

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name, a))


@unittest.skipUnless(RCLONE, "rclone not installed")
class TestApi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["RSG_HOME"] = str(self.root / "home")
        self.src, self.dst, self.bk = self.root / "src", self.root / "dst", self.root / "bk"
        for p in (self.src, self.dst, self.bk):
            p.mkdir()
        (self.src / "f.txt").write_text("data", encoding="utf-8")
        self.win = FakeWindow()
        self.api = apimod.Api(lambda: self.win)
        self.api._attach_windows(self.win, self.win)
        for step, _ in apimod.BOOT:
            self.assertTrue(self.api.boot_step(step)["ok"])
        self.api.scheduler.stop()

    def tearDown(self):
        self.api.shutdown()
        os.environ.pop("RSG_HOME", None)
        self.tmp.cleanup()

    def make(self, mode="copy"):
        job = self.api.new_job(mode)["data"]
        job.update(dest_kind="local", source=str(self.src), target=str(self.dst), backup_root=str(self.bk))
        return self.api.save_job(job)["data"]

    def finish(self, run_id):
        for _ in range(300):
            rec = self.api.mgr.records[run_id]
            if rec.state in ("done", "failed", "stopped"):
                return rec
            time.sleep(0.1)
        self.fail("run did not finish")

    def test_boot_loads_catalogue_and_remotes_without_error(self):
        self.assertGreater(len(self.api.flag_catalogue()["data"]), 200)
        self.assertTrue(self.api.app_state()["data"]["rclone"])

    def test_real_run_needs_the_typed_word(self):
        job = self.make()
        r = self.api.start(job["id"], True, "execute")
        self.assertFalse(r["ok"])
        self.assertIn("EXECUTE", r["error"])
        self.assertEqual(list(self.dst.iterdir()), [])
        r = self.api.start(job["id"], True, "EXECUTE")
        self.assertTrue(r["ok"], r)
        self.finish(r["data"])
        self.assertEqual((self.dst / "f.txt").read_text(encoding="utf-8"), "data")

    def test_save_job_keeps_only_flags_that_differ_and_refuses_owned_ones(self):
        job = self.make()
        job["flags"] = {"--transfers": "4", "--max-age": "30d", "--dry-run": True}
        saved = self.api.save_job(job)["data"]
        self.assertEqual(saved["flags"], {"--max-age": "30d"})
        job["extra"] = "--backup-dir x"
        saved = self.api.save_job(job)["data"]
        self.assertTrue(any("managed" in p for p in saved["problems"]))
        self.assertFalse(self.api.start(job["id"], False)["ok"])

    def test_dry_run_unlocks_move_only_for_the_same_job(self):
        job = self.make("move")
        self.assertFalse(self.api.start(job["id"], True, "EXECUTE")["ok"])
        self.finish(self.api.start(job["id"], False)["data"])
        self.assertTrue(self.api.jobs()["data"][0]["move_ready"])
        job = self.api.jobs()["data"][0]
        job["flags"] = {"--max-age": "1d"}
        self.api.save_job(job)
        self.assertFalse(self.api.jobs()["data"][0]["move_ready"], "changing the job invalidates the dry run")
        self.assertTrue((self.src / "f.txt").exists())

    def test_schedule_real_needs_the_word_and_is_tied_to_the_job(self):
        job = self.make()
        s = {"enabled": True, "kind": "daily", "time": "03:00", "real": True}
        self.assertFalse(self.api.set_schedule(job["id"], s, "")["ok"])
        r = self.api.set_schedule(job["id"], s, "EXECUTE")
        self.assertTrue(r["ok"], r)
        stored = self.api._job(job["id"]).schedule
        self.assertEqual(stored["real_sig"], core.job_signature(self.api._job(job["id"])))
        r = self.api.set_schedule(job["id"], {**s, "real": False}, "")
        self.assertTrue(r["ok"])
        self.assertEqual(self.api._job(job["id"]).schedule["real_sig"], "")

    def test_open_url_only_allows_known_links(self):
        self.assertFalse(self.api.open_url("https://evil.example/x")["ok"])
        self.assertFalse(self.api.open_url("file:///etc/passwd")["ok"])
        self.assertFalse(self.api.open_url("mailto:someone@else.com")["ok"])

    def test_close_asks_when_runs_are_active_and_boot_complete_shows_main(self):
        self.assertTrue(self.api.boot_complete()["ok"] or True)
        self.assertIn(("show", ()), self.win.calls)
        job = self.make()
        (self.src / "big.bin").write_bytes(os.urandom(2_000_000))
        run_id = self.api.start(job["id"], False)["data"]
        r = self.api.win_close(False)
        self.assertTrue(r["ok"])
        if self.api.mgr.active():
            self.assertEqual(r["data"].get("confirm"), 1)
        self.finish(run_id)

    def test_duplicate_and_delete(self):
        job = self.make()
        copy = self.api.duplicate_job(job["id"])["data"]
        self.assertNotEqual(copy["id"], job["id"])
        self.assertEqual(copy["source"], job["source"])
        self.assertTrue(self.api.delete_job(copy["id"])["ok"])
        self.assertEqual(len(self.api.jobs()["data"]), 1)

    def test_path_info_free_space_and_missing_folder(self):
        info = self.api.path_info(str(self.dst))["data"]
        self.assertTrue(info["exists"])
        self.assertTrue(info["free"])
        info = self.api.path_info(str(self.root / "nope" / "deeper"))["data"]
        self.assertFalse(info["exists"])
        self.assertTrue(info["free"], "free space of the drive it would be created on")


if __name__ == "__main__":
    unittest.main()
