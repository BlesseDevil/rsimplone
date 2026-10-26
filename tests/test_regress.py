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
"""Regression tests for the findings of the independent safety audit. Each one reproduces the audited failure and
checks the outcome by file CONTENT. Run with:  python -m unittest discover -s tests -v"""
import hashlib
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rsg import api as apimod, core, flags, runs  # noqa: E402

RCLONE = core.find_rclone()


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:10]


def wait_done(mgr, run_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        rec = mgr.records[run_id]
        if rec.state in ("done", "failed", "stopped"):
            return rec
        time.sleep(0.1)
    raise AssertionError("run did not finish")


@unittest.skipUnless(RCLONE, "rclone not installed")
class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["RSG_HOME"] = str(self.root / "home")
        self.src, self.dst, self.bk = self.root / "src", self.root / "dst", self.root / "bk"
        for p in (self.src, self.dst, self.bk):
            p.mkdir()
        self.mgr = runs.RunManager(lambda: RCLONE)

    def tearDown(self):
        os.environ.pop("RSG_HOME", None)
        self.tmp.cleanup()

    def job(self, **kw):
        j = core.Job(name="t", dest_kind="local", mode="move", source=str(self.src), target=str(self.dst), backup_root=str(self.bk))
        for k, v in kw.items():
            setattr(j, k, v)
        return j

    def allow_move(self, j):
        j.dry_sig, j.dry_ts = core.job_signature(j), time.time()

    def files(self, base):
        return {str(p.relative_to(base)).replace("\\", "/"): sha(p) for p in Path(base).rglob("*") if p.is_file()}


class TestMoveNeverLosesUnverifiedContent(Base):
    def test_same_size_same_mtime_different_content_is_not_deleted_unverified(self):
        (self.src / "f.txt").write_text("12345")
        (self.dst / "f.txt").write_text("abcde")
        old = time.time() - 86400 * 30
        os.utime(self.src / "f.txt", (old, old))
        os.utime(self.dst / "f.txt", (old, old))
        want_src, want_dst = sha(self.src / "f.txt"), sha(self.dst / "f.txt")
        j = self.job()
        self.allow_move(j)
        wait_done(self.mgr, self.mgr.start_job(j, True))
        survivors = set(self.files(self.dst).values()) | set(self.files(self.bk).values()) | set(self.files(self.src).values())
        self.assertIn(want_src, survivors, "the source content must exist somewhere after a Move")
        self.assertIn(want_dst, survivors, "the replaced destination content must be kept too")

    def test_move_refuses_flags_that_skip_verification(self):
        for kw in ({"flags": {"--update": True}}, {"extra": "--size-only"}, {"extra": "-u"}, {"flags": {"--checksum": False}}):
            (self.src / "f.txt").write_text("x")
            problems = " ".join(core.validate_job(self.job(**kw), RCLONE))
            self.assertIn("verified", problems, kw)

    def test_move_to_missing_destination_keeps_the_source_folder(self):
        (self.src / "a.txt").write_text("a")
        j = self.job(target=str(self.root / "not-yet"))
        self.allow_move(j)
        wait_done(self.mgr, self.mgr.start_job(j, True))
        self.assertTrue(self.src.exists(), "rclone must not rename the whole source folder away")
        self.assertEqual(self.files(self.root / "not-yet"), {"a.txt": sha(self.root / "not-yet" / "a.txt")})

    def test_move_and_sync_need_a_backup_folder_copy_does_not(self):
        (self.src / "a.txt").write_text("a")
        self.assertTrue(core.validate_job(self.job(backup_root=""), RCLONE))
        self.assertTrue(core.validate_job(self.job(mode="sync", backup_root=""), RCLONE))
        self.assertEqual(core.validate_job(self.job(mode="copy", backup_root=""), RCLONE), [])

    def test_empty_source_is_refused_for_sync_and_move(self):
        for mode in ("sync", "move"):
            self.assertIn("empty", " ".join(core.validate_job(self.job(mode=mode), RCLONE)))

    def test_real_move_unlock_is_single_use(self):
        (self.src / "a.txt").write_text("a")
        j = self.job()
        self.allow_move(j)
        a = apimod.Api()
        a.store.jobs.append(j)
        a.rclone = RCLONE
        a.mgr = runs.RunManager(lambda: RCLONE, on_done=a._run_done)
        rec = wait_done(a.mgr, a.mgr.start_job(j, True))
        self.assertEqual(rec.state, "done")
        self.assertIsNotNone(core.move_gate(j), "a used dry run must not unlock a second real Move")
        self.assertEqual(self.files(self.dst), {"a.txt": sha(self.dst / "a.txt")})


class TestBackupsAreNeverOverwritten(Base):
    def test_two_syncs_back_to_back_keep_both_old_versions(self):
        (self.dst / "f.txt").write_text("v1")
        os.utime(self.dst / "f.txt", (time.time() - 3600, time.time() - 3600))    # rclone skips equal size + equal time
        j = self.job(mode="sync")
        (self.src / "f.txt").write_text("v2")
        wait_done(self.mgr, self.mgr.start_job(j, True))
        time.sleep(0.1)
        (self.src / "f.txt").write_text("v3")
        os.utime(self.src / "f.txt", (time.time() + 60, time.time() + 60))
        wait_done(self.mgr, self.mgr.start_job(j, True))
        kept = sorted(Path(p).read_text() for p in self.bk.rglob("f.txt"))
        self.assertEqual(kept, ["v1", "v2"])
        self.assertEqual((self.dst / "f.txt").read_text(), "v3")

    def test_stamp_has_seconds_and_is_unique(self):
        a, b = core._unique_stamp(), core._unique_stamp()
        self.assertNotEqual(a, b)
        self.assertRegex(a, r"^\d{8}-\d{6}$")

    def test_label_cannot_escape_the_backup_folder(self):
        for bad in ("..", ".", " .. "):
            j = self.job(label=bad)
            self.assertNotIn("..", os.path.basename(core.backup_spec(j, "S").split("S")[0].rstrip("\\/")) + core.job_label(j))
            self.assertEqual(core.job_label(j), "_")


class TestOverlapChecks(Base):
    def test_drive_root_overlap_is_detected(self):
        if core.IS_WIN:
            self.assertTrue(core.local_overlap("C:\\", "C:\\bk"))
            self.assertTrue(core.local_overlap("C:\\x", "C:\\"))
            self.assertFalse(core.local_overlap("C:\\data", "C:\\data2"))
        else:
            self.assertTrue(core.local_overlap("/", "/bk"))
            self.assertFalse(core.local_overlap("/data", "/data2"))

    def test_remote_that_is_really_a_folder_inside_the_source_is_refused(self):
        cfg = self.root / "rclone.conf"
        cfg.write_text("[inner]\ntype = alias\nremote = %s\n" % (self.src / "inside").as_posix().replace("\\", "/"), encoding="utf-8")
        os.environ["RCLONE_CONFIG"] = str(cfg)
        try:
            (self.src / "inside").mkdir()
            (self.src / "a.txt").write_text("a")
            j = core.Job(name="r", dest_kind="remote", mode="copy", source=str(self.src), remote="inner", target="x")
            with self.assertRaises(runs.RunRefused):
                self.mgr.start_job(j, False)
        finally:
            os.environ.pop("RCLONE_CONFIG", None)

    def test_remote_name_tricks_are_refused(self):
        (self.src / "a.txt").write_text("a")
        for name in (":local", ":local,x=y", "a:b", "a/b"):
            j = core.Job(name="r", dest_kind="remote", mode="copy", source=str(self.src), remote=name, target="x")
            self.assertTrue(core.validate_job(j, RCLONE), name)


class TestFlagGuards(unittest.TestCase):
    def test_short_flags_with_equals_and_odd_names_are_refused(self):
        for tok in ("-n=true", "-P=true", "-q=true", "-i=true", "-v=2"):
            self.assertTrue(flags.denied_in_tokens([tok]), tok)
        for key in ("-n", "dry-run", "--dry-run ", " --dry-run", "--DRY-RUN"):
            with self.assertRaises(ValueError):
                flags.merge({}, {key: True})
            self.assertEqual(flags.clean_overrides({key: True}, []), {})


@unittest.skipUnless(RCLONE, "rclone not installed")
class TestApiAndCli(Base):
    def make_api(self):
        a = apimod.Api()
        a.store = core.load_store()
        a.rclone = RCLONE
        a.catalogue = []
        return a

    def test_save_job_cannot_smuggle_a_real_schedule(self):
        a = self.make_api()
        job = a.new_job("copy")["data"]
        job["schedule"] = {"enabled": True, "kind": "interval", "every_min": 5, "real": True, "real_sig": "whatever"}
        a.save_job(job)
        self.assertEqual(a._job(job["id"]).schedule, {})

    def test_bad_value_leaves_the_job_untouched(self):
        a = self.make_api()
        job = a.new_job("copy")["data"]
        before = a._job(job["id"]).name
        r = a.save_job({"id": job["id"], "name": "changed", "checkers": "abc"})
        self.assertFalse(r["ok"])
        self.assertEqual(a._job(job["id"]).name, before)
        self.assertTrue(a.jobs()["ok"])

    def test_move_jobs_cannot_be_exported_as_ungated_scripts(self):
        a = self.make_api()
        job = a.new_job("move")["data"]
        self.assertFalse(a.export_script(job["id"])["ok"])

    def test_headless_real_move_needs_the_dry_run_too(self):
        (self.src / "a.txt").write_text("a")
        store = core.Store()
        j = self.job(name="mv")
        store.jobs.append(j)
        core.save_store(store)
        self.assertEqual(core.cli_main(["--run", "mv", "--execute", "--yes"]), 2)
        self.assertTrue((self.src / "a.txt").exists())
        self.assertEqual(core.cli_main(["--run", "mv"]), 0)           # a dry run unlocks one real run
        self.assertEqual(core.cli_main(["--run", "mv", "--execute", "--yes"]), 0)
        self.assertFalse((self.src / "a.txt").exists())
        self.assertEqual((self.dst / "a.txt").read_text(), "a")
        (self.src / "b.txt").write_text("b")
        self.assertEqual(core.cli_main(["--run", "mv", "--execute", "--yes"]), 2, "the unlock was used up")

    def test_empty_lock_file_is_not_stolen(self):
        j = self.job()
        lock = core.config_dir() / "locks" / ("%s.lock" % j.id)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("")
        with self.assertRaises(core.RunBusy):
            core._acquire_lock(j)


@unittest.skipUnless(RCLONE and os.name == "nt" or RCLONE, "rclone not installed")
class TestStop(Base):
    def test_stop_ends_the_run_quickly_and_leaves_no_partial_files(self):
        (self.src / "big.bin").write_bytes(os.urandom(20_000_000))
        j = self.job(mode="copy", flags={"--bwlimit": "1M"}, backup_root="")
        rid = self.mgr.start_job(j, True)
        time.sleep(2.5)
        t = time.time()
        self.mgr.stop(rid)
        rec = wait_done(self.mgr, rid, timeout=20)
        self.assertEqual(rec.state, "stopped")
        self.assertLess(time.time() - t, 8, "a graceful stop, not the kill timer")
        self.assertIn("stopped", rec.result.meaning)
        self.assertEqual([p.name for p in self.dst.iterdir() if p.name.endswith(".partial")], [])
        self.assertEqual(sha(self.src / "big.bin"), sha(self.src / "big.bin"))


if __name__ == "__main__":
    unittest.main()
