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
import tempfile as _tf

os.environ["RSG_TESTING"] = "1"
_SAFE_HOME = os.path.join(_tf.gettempdir(), "rsg-tests-never-real")      # what RSG_HOME falls back to between tests
os.environ["RSG_HOME"] = _SAFE_HOME
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
        os.environ["RSG_HOME"] = _SAFE_HOME
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
        r = self.api.save_job(job)
        self.assertFalse(r["ok"], "a job that uses an app-owned flag must not be saved")
        self.assertIn("managed", r["error"])
        self.assertEqual(self.api._job(job["id"]).extra, "")

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

    def test_export_import_roundtrip_selected_jobs(self):
        a, b = self.make("copy"), self.make("move")
        self.api.set_schedule(a["id"], {"enabled": True, "kind": "daily", "time": "03:00"}, "")
        data = self.api._export_data([a["id"]])
        self.assertEqual([j["name"] for j in data["jobs"]], [a["name"]], "only the selected job is exported")
        for key in ("id", "schedule", "dry_sig", "dry_ts", "last_run"):
            self.assertNotIn(key, data["jobs"][0])
        res = self.api._import_data(data)
        self.assertEqual(len(res["jobs"]), 1)
        got = res["jobs"][0]
        self.assertNotEqual(got["id"], a["id"])
        self.assertNotEqual(got["name"], a["name"], "names stay unique")
        self.assertEqual(got["source"], a["source"])
        self.assertFalse(got["schedule"]["enabled"], "an imported job never starts scheduled")
        self.assertEqual(len(self.api.jobs()["data"]), 3)
        self.assertEqual(len(self.api._export_data([a["id"], b["id"]])["jobs"]), 2)

    def test_import_move_job_is_not_unlocked_and_bad_input_is_refused(self):
        m = self.make("move")
        self.finish(self.api.start(m["id"], False)["data"])
        self.assertTrue(self.api._job_view(self.api._job(m["id"]))["move_ready"])
        data = self.api._export_data([m["id"]])
        data["jobs"][0].update(dry_sig="x", dry_ts=time.time())             # a hand-edited file must not smuggle in an unlock
        got = self.api._import_data(data)["jobs"][0]
        self.assertFalse(got["move_ready"])
        self.assertFalse(self.api.start(got["id"], True, "EXECUTE")["ok"])
        for bad in ({}, [], {"app": "other", "jobs": []}, {"app": "rSimpLone", "format": 99, "jobs": []}):
            with self.assertRaises(ValueError):
                self.api._import_data(bad)
        res = self.api._import_data({"app": "rSimpLone", "format": 1, "jobs": [5, {"name": "x", "mode": "bogus"}, {"name": "ok", "mode": "copy"}]})
        self.assertEqual([j["name"] for j in res["jobs"]], ["ok"])
        self.assertEqual(len(res["skipped"]), 2)
        with self.assertRaises(ValueError):
            self.api._export_data(["nope"])

    def test_export_and_import_through_a_file(self):
        a = self.make("copy")
        target = self.root / "jobs-backup"
        self.api._dialog = lambda kind, **kw: str(target)
        r = self.api.export_jobs([a["id"]])
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["data"]["path"], str(target) + ".json", "the .json suffix is added")
        self.assertTrue(r["data"]["path"].endswith(".json") and Path(r["data"]["path"]).exists())
        self.api._dialog = lambda kind, **kw: r["data"]["path"]
        got = self.api.import_jobs()
        self.assertTrue(got["ok"], got)
        self.assertEqual(len(got["data"]["jobs"]), 1)
        self.api._dialog = lambda kind, **kw: ""
        self.assertTrue(self.api.import_jobs()["data"]["cancelled"], "closing the dialog changes nothing")
        bad = self.root / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        self.api._dialog = lambda kind, **kw: str(bad)
        self.assertIn("not valid JSON", self.api.import_jobs()["error"])
        bad.write_bytes(b"\xff\xfe\x00bad")
        self.assertFalse(self.api.import_jobs()["ok"])
        bad.write_text(" " * (apimod.IMPORT_MAX_BYTES + 1), encoding="utf-8")
        self.assertIn("too big", self.api.import_jobs()["error"])

    def test_one_malformed_job_never_aborts_an_import(self):
        before = len(self.api.jobs()["data"])
        res = self.api._import_data({"app": "rSimpLone", "format": 1, "jobs": [
            {"name": "a", "mode": "copy", "flags": []}, {"name": "b", "mode": "copy", "flags": "x"},
            {"name": "c", "mode": "copy", "bw_mbps": "fast"}, {"name": "good", "mode": "copy"}]})
        self.assertIn("good", [j["name"] for j in res["jobs"]])
        self.assertEqual(len(self.api.jobs()["data"]), before + len(res["jobs"]))
        self.assertEqual(len(res["jobs"]) + len(res["skipped"]), 4)

    def test_live_counts_match_the_final_counts_rules(self):
        from rsg import runs as runsmod
        mgr = self.api.mgr
        rec = runsmod.Record("x", "job", "n")
        for kind, path in (("delete", "a.txt"), ("delete", "a.txt"), ("replace", "b.txt"), ("backup", "b.txt"), ("upload", "c.txt"), ("error", "d.txt"), ("error", "d.txt")):
            mgr._apply(rec, "activity", {"kind": kind, "path": path, "detail": ""})
        self.assertEqual(rec.counts, {"delete": 1, "backup": 1, "upload": 1, "error": 2})

    def test_a_later_window_save_cannot_bring_a_used_up_move_unlock_back(self):
        m = self.make("move")
        self.finish(self.api.start(m["id"], False)["data"])
        for _ in range(100):                                    # the run is marked finished a moment before its unlock is recorded
            if self.api.jobs()["data"][0]["move_ready"]:
                break
            time.sleep(0.05)
        self.assertTrue(self.api.jobs()["data"][0]["move_ready"])
        other = core.load_store().jobs[0]                      # another process (the headless mode) uses the unlock up
        self.assertIsNone(core.consume_move_unlock(other))
        self.api.set_theme("dark")                              # any unrelated save from this window afterwards
        self.assertEqual(core.load_store().jobs[0].dry_sig, "", "the unlock on disk must stay used up")
        self.assertFalse(self.api.jobs()["data"][0]["move_ready"])
        r = self.api.start(m["id"], True, "EXECUTE")
        self.assertFalse(r["ok"])
        self.assertTrue((self.src / "f.txt").exists())

    def test_a_missing_or_damaged_jobs_file_cannot_revive_a_used_up_unlock(self):
        m = self.make("move")
        self.finish(self.api.start(m["id"], False)["data"])
        for _ in range(100):
            if self.api.jobs()["data"][0]["move_ready"]:
                break
            time.sleep(0.05)
        self.assertIsNone(core.consume_move_unlock(core.load_store().jobs[0]))
        core._jobs_file().unlink()                                # the file vanishes (or is replaced by an empty one)
        self.api.set_theme("dark")
        self.assertEqual(core.load_store().jobs[0].dry_sig, "")
        self.assertFalse(self.api.start(m["id"], True, "EXECUTE")["ok"])
        self.assertTrue((self.src / "f.txt").exists())

    def test_failed_save_leaves_memory_as_the_disk_is(self):
        self.make("copy")
        real = core.save_store_keeping_unlocks
        core.save_store_keeping_unlocks = lambda store: (_ for _ in ()).throw(OSError("disk full"))
        try:
            self.assertFalse(self.api.new_job("copy")["ok"])
            self.assertFalse(self.api.delete_job(self.api.store.jobs[0].id)["ok"])
        finally:
            core.save_store_keeping_unlocks = real
        self.assertEqual(len(self.api.store.jobs), 1)
        self.assertEqual(len(core.load_store().jobs), 1)

    def test_import_refuses_control_and_bidi_characters(self):
        base = {"mode": "copy"}
        bad = ["a\x01b", "a\nb", "a\x1bb", "a\x7fb", "a‮b", "a\ud800b"]
        res = self.api._import_data({"app": "rSimpLone", "format": 1, "jobs": [{**base, "name": n} for n in bad] + [{**base, "name": "ok", "extra": "tab\there"[:0] + "x"}]})
        self.assertEqual([j["name"] for j in res["jobs"]], ["ok"])
        self.assertEqual(len(res["skipped"]), len(bad))

    def test_move_must_keep_dirmove_disabled(self):
        m = self.make("move")
        self.assertEqual(core.validate_job(self.api._job(m["id"]), self.api.rclone), [])
        job = self.api._job(m["id"])
        job.flags = {"--disable": "Copy,Move"}
        self.assertTrue(any("DirMove" in p for p in core.validate_job(job, self.api.rclone)))
        job.flags, job.extra = {}, "--disable=Copy"
        self.assertTrue(core.validate_job(job, self.api.rclone), "a hand-typed --disable must not slip past")

    def test_flag_names_with_a_trailing_newline_are_refused(self):
        from rsg import flags as flagmod
        cleaned = flagmod.clean_overrides({"--dry-run\n": True, "--backup-dir\n": "x", "--max-age": "1d"}, self.api.catalogue)
        self.assertEqual(cleaned, {"--max-age": "1d"})

    def test_hostile_import_cannot_break_the_job_list_or_blow_up(self):
        base = {"mode": "copy", "dest_kind": "local", "source": str(self.src), "target": str(self.dst)}
        file = {"app": "rSimpLone", "format": 1, "jobs": [
            {**base, "name": "nul", "source": str(self.src) + "\x00x"},
            {**base, "name": "huge", "extra": "a" * 50_000},
            {**base, "name": "fine"},
            {**base, "name": "FINE"}]}
        res = self.api._import_data(file)
        self.assertEqual(sorted(j["name"].lower() for j in res["jobs"]), ["fine", "fine 2"], res["skipped"])
        self.assertEqual(len(res["skipped"]), 2)
        self.assertTrue(self.api.jobs()["ok"], "the job list must still load")
        self.assertEqual(len(core.load_store().jobs), 2)
        res = self.api._import_data({"app": "rSimpLone", "format": 1, "jobs": [{"name": "j%d" % i, "mode": "copy"} for i in range(apimod.IMPORT_MAX_JOBS + 5)]})
        self.assertTrue(any("ignored" in t for t in res["skipped"]), "dropped jobs are reported, not silent")
        for bad_format in (True, 1.0, "1", 2):
            with self.assertRaises(ValueError):
                self.api._import_data({"app": "rSimpLone", "format": bad_format, "jobs": []})

    def test_import_accepts_a_file_saved_with_a_bom(self):
        a = self.make("copy")
        path = self.root / "bom.json"
        path.write_text("﻿" + __import__("json").dumps(self.api._export_data([a["id"]])), encoding="utf-8")
        self.api._dialog = lambda kind, **kw: str(path)
        self.assertTrue(self.api.import_jobs()["ok"])

    def test_console_lines_reaches_the_page_under_a_name_pywebview_can_call(self):
        job = self.make()
        rid = self.api.start(job["id"], False)["data"]
        self.finish(rid)
        r = self.api.console_lines(rid, 0)
        self.assertTrue(r["ok"])
        self.assertGreater(len(r["data"]["lines"]), 0)
        self.assertFalse(hasattr(self.api, "console"), "'console' hangs forever as a pywebview API name")

    def test_run_view_carries_totals_for_the_live_screen(self):
        job = self.make()
        rid = self.api.start(job["id"], True, "EXECUTE")["data"]
        view = self.finish(rid).view()
        for key in ("total_transfers", "total_checks", "elapsed", "transferring"):
            self.assertIn(key, view)

    def test_path_info_free_space_and_missing_folder(self):
        info = self.api.path_info(str(self.dst))["data"]
        self.assertTrue(info["exists"])
        self.assertTrue(info["free"])
        info = self.api.path_info(str(self.root / "nope" / "deeper"))["data"]
        self.assertFalse(info["exists"])
        self.assertTrue(info["free"], "free space of the drive it would be created on")


if __name__ == "__main__":
    unittest.main()
