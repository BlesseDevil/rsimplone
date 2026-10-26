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
"""Tests for rsg_core. They run real rclone against a throwaway local 'alias' remote and check results by
file content, never by counts alone. Run with:  python -m unittest discover -s tests -v"""
import os
import queue
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rsg import core  # noqa: E402

RCLONE = core.find_rclone()


def drain_until_done(q, timeout=60):
    end = time.time() + timeout
    seen = []
    while time.time() < end:
        try:
            kind, payload = q.get(timeout=0.5)
        except queue.Empty:
            continue
        seen.append((kind, payload))
        if kind == "done":
            return seen
    raise AssertionError("run did not finish in %ds" % timeout)


@unittest.skipUnless(RCLONE, "rclone not installed")
class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["RSG_HOME"] = str(self.root / "home")
        (self.root / "remote").mkdir()
        os.environ["RCLONE_CONFIG_TESTR_TYPE"] = "alias"
        os.environ["RCLONE_CONFIG_TESTR_REMOTE"] = str(self.root / "remote")
        self.src = self.root / "src"
        self.src.mkdir()

    def tearDown(self):
        os.environ.pop("RSG_HOME", None)
        self.tmp.cleanup()

    def write(self, base, rel, text):
        p = Path(base) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def read(self, base, rel):
        return (Path(base) / rel).read_text(encoding="utf-8")

    def job(self, **kw):
        j = core.Job(name="t", source=str(self.src), remote="testr", target="dest", backup_root="bk")
        for k, v in kw.items():
            setattr(j, k, v)
        return j

    def run_job(self, job, real):
        q = queue.Queue()
        run = core.SyncRun(RCLONE, job, real, q)
        run.start()
        events = drain_until_done(q)
        return run, events[-1][1]["result"], events


class TestPure(unittest.TestCase):
    def test_check_path(self):
        dirs = ["A", "A/B", "C", "C"]
        self.assertEqual(core.check_path("A/B", dirs, 2).state, "exists")
        self.assertEqual(core.check_path("A/X", dirs, 2).state, "missing")
        self.assertEqual(core.check_path("A/B/C", dirs, 2).state, "unverified")
        self.assertTrue(core.check_path("C", dirs, 1).duplicate)
        self.assertEqual(core.check_path("a", ["A"], 1).near, "A")
        self.assertEqual(core.check_path("Q/x", dirs, 2).state, "missing")  # parent missing -> cannot exist

    def test_validate(self):
        j = core.Job(source=__file__, remote="r", target="t", backup_root="t/bk")
        problems = " ".join(core.validate_job(j, "rclone"))
        self.assertIn("Local folder not found", problems)
        self.assertIn("separate", problems)
        j = core.Job(source=str(Path(__file__).parent), remote="r", target="t", mode="sync")
        self.assertIn("backup folder", " ".join(core.validate_job(j, "rclone")))
        j.mode = "copy"
        self.assertEqual(core.validate_job(j, "rclone"), [])  # backup optional for copy

    def test_args_sync_vs_copy(self):
        j = core.Job(source="S", remote="r", target="t", backup_root="bk")
        a = core.build_args(j, True, "STAMP")
        self.assertEqual(a[0], "sync")
        self.assertIn("r:bk/S/STAMP", a)
        self.assertNotIn("--dry-run", a)
        self.assertNotIn("--no-update-dir-modtime", a)    # folder dates: own option, OFF by default (rclone's behaviour)
        self.assertIn("--tpslimit", a)                     # low API mode is the default
        self.assertIn("--check-first", a)                  # hdd profile is the default
        self.assertNotIn("--ignore-existing", a)
        j.mode, j.backup_root, j.skip_existing = "copy", "", True
        a = core.build_args(j, False, "STAMP")
        self.assertEqual(a[0], "copy")
        self.assertNotIn("--backup-dir", a)
        self.assertIn("--ignore-existing", a)
        self.assertIn("--dry-run", a)
        # the two options are independent of each other
        j.no_dir_modtime = True
        a = core.build_args(j, True, "S")
        self.assertIn("--no-update-dir-modtime", a)
        self.assertIn("--tpslimit", a)
        j.api_low = False
        a = core.build_args(j, True, "S")
        self.assertIn("--no-update-dir-modtime", a)
        self.assertNotIn("--tpslimit", a)
        j.no_dir_modtime = False
        a = core.build_args(j, True, "S")
        self.assertNotIn("--no-update-dir-modtime", a)
        self.assertNotIn("--tpslimit", a)

    def test_detect_disk_kind_is_safe(self):
        import tempfile as _tf
        self.assertIn(core.detect_disk_kind(_tf.gettempdir()), ("ssd", "hdd", None))
        self.assertIsNone(core.detect_disk_kind("\\\\no-such-server\\share\\folder"))   # network or nonsense: no answer, no crash
        self.assertIsNone(core.detect_disk_kind(""))

    def test_defaults(self):
        j = core.Job()
        self.assertFalse(j.no_dir_modtime)       # rclone's own behaviour unless asked otherwise
        self.assertTrue(j.api_low)
        self.assertEqual(core.APP_NAME, "rSimpLone")

    def test_bandwidth(self):
        j = core.Job(bw_mbps=30, bw_percent=85)
        self.assertEqual(core.tuning(j)["bwlimit"], "3.04M")
        j.no_bw_limit = True
        self.assertEqual(core.tuning(j)["bwlimit"], "")

    def test_classify(self):
        self.assertEqual(core.classify("Copied (new)", "info"), "upload")
        self.assertEqual(core.classify("Skipped copy as --dry-run is set (size 5)", "notice"), "upload")
        self.assertEqual(core.classify("Moved into backup dir", "info"), "backup")
        self.assertEqual(core.classify("Skipped move as --dry-run is set (size 5)", "notice"), "replace")
        self.assertEqual(core.classify("Updated modification time in destination", "info"), "modtime")
        self.assertIsNone(core.classify("Set directory modification time (using SetModTime)", "info"))
        self.assertEqual(core.classify("boom", "error"), "error")

    def test_exit_meaning(self):
        self.assertIn("success", core.exit_meaning(0))
        self.assertIn("unknown", core.exit_meaning(99))


class TestRuns(Base):
    def scenario(self):
        self.dst = self.root / "remote" / "dest"
        self.write(self.src, "new.txt", "new")
        self.write(self.src, "changed.txt", "changed-new-content")
        self.write(self.src, "sub/in.txt", "in")
        self.write(self.dst, "changed.txt", "old")
        self.write(self.dst, "gone.txt", "gone-content")
        self.write(self.dst, "sub/gone2.txt", "gone2-content")

    def test_list_dirs_and_remotes(self):
        (self.root / "remote" / "A" / "B").mkdir(parents=True)
        (self.root / "remote" / "C").mkdir()
        self.assertEqual(sorted(core.list_dirs(RCLONE, "testr", 1)), ["A", "C"])
        self.assertEqual(sorted(core.list_dirs(RCLONE, "testr", 2)), ["A", "A/B", "C"])
        self.assertIn("testr", [n for n, _ in core.list_remotes(RCLONE)])
        with self.assertRaises(core.RcloneError):
            core.list_dirs(RCLONE, "no_such_remote", 1)

    def test_sync_dry_run_changes_nothing(self):
        self.scenario()
        before = {p.name: p.read_text() for p in (self.root / "remote").rglob("*") if p.is_file()}
        _, res, _ = self.run_job(self.job(), real=False)
        after = {p.name: p.read_text() for p in (self.root / "remote").rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(res.code, 0)
        self.assertFalse((self.root / "remote" / "bk").exists())

    def test_sync_real(self):
        self.scenario()
        run, res, _ = self.run_job(self.job(), real=True)
        self.assertEqual(res.code, 0, res.errors)
        # destination mirrors the source exactly
        self.assertEqual(self.read(self.dst, "new.txt"), "new")
        self.assertEqual(self.read(self.dst, "changed.txt"), "changed-new-content")
        self.assertEqual(self.read(self.dst, "sub/in.txt"), "in")
        self.assertFalse((self.dst / "gone.txt").exists())
        self.assertFalse((self.dst / "sub" / "gone2.txt").exists())
        # replaced and deleted files are kept, with their OLD content, under backup/<label>/<stamp>/
        bk = [p for p in (self.root / "remote" / "bk").rglob("*") if p.is_file()]
        self.assertEqual(sorted(p.read_text() for p in bk), ["gone-content", "gone2-content", "old"])
        for p in bk:
            self.assertEqual(p.relative_to(self.root / "remote" / "bk").parts[0], "src")   # label folder
        names = sorted(p.name for p in bk)
        self.assertEqual(names, ["changed.txt", "gone.txt", "gone2.txt"])
        self.assertEqual(res.counts.get("backup"), 3)
        self.assertEqual(res.counts.get("upload"), 3)
        self.assertTrue(Path(res.log_path).exists())
        self.assertIn("exit code 0", Path(res.log_path).read_text())

    def test_copy_never_deletes_and_backs_up_overwrites(self):
        self.scenario()
        self.write(self.dst, "keep.txt", "keep-me")
        _, res, _ = self.run_job(self.job(mode="copy"), real=True)
        self.assertEqual(res.code, 0, res.errors)
        self.assertEqual(self.read(self.dst, "keep.txt"), "keep-me")
        self.assertEqual(self.read(self.dst, "gone.txt"), "gone-content")        # not deleted
        self.assertEqual(self.read(self.dst, "changed.txt"), "changed-new-content")
        bk = [p for p in (self.root / "remote" / "bk").rglob("*") if p.is_file()]
        self.assertEqual([(p.name, p.read_text()) for p in bk], [("changed.txt", "old")])

    def test_copy_without_backup_dir(self):
        self.scenario()
        _, res, _ = self.run_job(self.job(mode="copy", backup_root=""), real=True)
        self.assertEqual(res.code, 0, res.errors)
        self.assertEqual(self.read(self.dst, "changed.txt"), "changed-new-content")
        self.assertFalse((self.root / "remote" / "bk").exists())

    def test_copy_skip_existing(self):
        self.scenario()
        _, res, _ = self.run_job(self.job(mode="copy", skip_existing=True), real=True)
        self.assertEqual(res.code, 0, res.errors)
        self.assertEqual(self.read(self.dst, "changed.txt"), "old")   # existing file left alone
        self.assertEqual(self.read(self.dst, "new.txt"), "new")       # new file still uploaded

    def test_lock_blocks_second_run(self):
        self.scenario()
        self.write(self.src, "big.bin", "x" * 3_000_000)
        j = self.job(bw_mbps=0.2)   # ~21 KiB/s: stays running long enough
        q1 = queue.Queue()
        r1 = core.SyncRun(RCLONE, j, True, q1)
        r1.start()
        try:
            with self.assertRaises(core.RunBusy):
                core.SyncRun(RCLONE, j, True, queue.Queue()).start()
        finally:
            r1.stop()
            drain_until_done(q1, 30)
        # lock is released afterwards
        q3 = queue.Queue()
        r3 = core.SyncRun(RCLONE, self.job(), False, q3)
        r3.start()
        r3.kill()
        drain_until_done(q3, 30)      # wait until rclone has really exited, or Windows still holds its log file

    def test_stop_ends_rclone(self):
        self.scenario()
        self.write(self.src, "big.bin", "x" * 3_000_000)
        q = queue.Queue()
        run = core.SyncRun(RCLONE, self.job(bw_mbps=0.2), True, q)
        run.start()
        time.sleep(3)
        self.assertTrue(run.running)
        t0 = time.time()
        run.stop()
        events = drain_until_done(q, 30)
        self.assertLess(time.time() - t0, 15)
        res = events[-1][1]["result"]
        self.assertTrue(res.stopped)
        self.assertFalse(run.running)
        self.assertFalse(list((Path(os.environ["RSG_HOME"]) / "locks").glob("*.lock")))

    def test_store_roundtrip_and_broken_file(self):
        s = core.Store(jobs=[self.job(name="a"), self.job(name="b", mode="copy")], settings={"rclone": ""})
        core.save_store(s)
        back = core.load_store()
        self.assertEqual([(j.name, j.mode) for j in back.jobs], [("a", "sync"), ("b", "copy")])
        (Path(os.environ["RSG_HOME"]) / "jobs.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(core.load_store().jobs, [])
        self.assertTrue((Path(os.environ["RSG_HOME"]) / "jobs.broken.json").exists())  # kept, not destroyed

    def test_cli_headless(self):
        self.scenario()
        j = self.job(name="cli job")
        core.save_store(core.Store(jobs=[j]))
        rc = core.cli_main(["--run", "cli job", "--execute"])           # no --yes -> dry run only
        self.assertEqual(rc, 0)
        self.assertEqual(self.read(self.dst, "changed.txt"), "old")
        rc = core.cli_main(["--run", "cli job", "--execute", "--yes"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.read(self.dst, "changed.txt"), "changed-new-content")
        self.assertEqual(core.load_store().jobs[0].last_mode, "run")

    def test_export_script_runs(self):
        self.scenario()
        j = self.job(name="exp")
        name, text = core.export_script(j, RCLONE)
        self.assertIn("--dry-run" if core.IS_WIN else "--dry-run", text)
        script = self.root / name
        script.write_bytes(text.encode("utf-8"))
        if core.IS_WIN:
            cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        else:
            cmd = ["sh", str(script)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(self.dst, "changed.txt"), "old")     # dry run by default
        cmd.append("-Execute" if core.IS_WIN else "--execute")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(self.dst, "changed.txt"), "changed-new-content")
        self.assertTrue(any(p.is_file() for p in (self.root / "remote" / "bk").rglob("*")))


class TestLocalDestination(Base):
    """The destination can be another folder on this computer instead of a cloud remote."""

    def ljob(self, **kw):
        j = core.Job(name="l", dest_kind="local", source=str(self.src), target=str(self.root / "ldest"),
                     backup_root=str(self.root / "lbk"))
        for k, v in kw.items():
            setattr(j, k, v)
        return j

    def scenario(self):
        self.dst = self.root / "ldest"
        self.write(self.src, "new.txt", "new")
        self.write(self.src, "changed.txt", "changed-new-content")
        self.write(self.src, "sub/in.txt", "in")
        self.write(self.dst, "changed.txt", "old")
        self.write(self.dst, "gone.txt", "gone-content")

    def test_args_carry_no_cloud_only_flags(self):
        j = self.ljob(no_dir_modtime=True)       # even when ticked, a local destination keeps its folder dates
        a = core.build_args(j, True, "STAMP")
        self.assertEqual(a[2], os.path.normpath(j.target))
        for flag in ("--drive-chunk-size", "--fast-list", "--tpslimit", "--bwlimit", "--no-update-dir-modtime"):
            self.assertNotIn(flag, a)
        self.assertEqual(a[a.index("--backup-dir") + 1], os.path.join(os.path.normpath(j.backup_root), "src", "STAMP"))

    def test_validation(self):
        self.write(self.src, "x.txt", "x")      # sync refuses an empty source
        base = self.ljob()
        self.assertEqual(core.validate_job(base, "rclone"), [])
        j = self.ljob(target="relative/folder")
        self.assertIn("full folder path", " ".join(core.validate_job(j, "rclone")))
        j = self.ljob(target=os.path.splitdrive(str(self.root))[0] + os.sep if core.IS_WIN else "/")
        self.assertIn("not the whole drive", " ".join(core.validate_job(j, "rclone")))
        j = self.ljob(target=str(self.src / "inside"))                       # destination inside the source: would copy into itself
        self.assertIn("separate folders", " ".join(core.validate_job(j, "rclone")))
        j = self.ljob(target=str(self.root))                                  # destination contains the source
        self.assertIn("separate folders", " ".join(core.validate_job(j, "rclone")))
        j = self.ljob(backup_root=str(self.src / "bk"))
        self.assertIn("backup folder must not be inside", " ".join(core.validate_job(j, "rclone")))
        j = self.ljob(backup_root=str(self.root / "ldest" / "bk"))
        self.assertIn("non-nested", " ".join(core.validate_job(j, "rclone")))
        j = self.ljob(backup_root="")
        self.assertIn("backup folder", " ".join(core.validate_job(j, "rclone")))
        j.mode = "copy"
        self.assertEqual(core.validate_job(j, "rclone"), [])
        self.assertEqual(core.check_local_path(str(self.src)).state, "exists")
        self.assertEqual(core.check_local_path(str(self.root / "nope")).state, "missing")

    def test_dry_run_changes_nothing(self):
        self.scenario()
        before = sorted((str(p.relative_to(self.dst)), p.read_text()) for p in self.dst.rglob("*") if p.is_file())
        _, res, _ = self.run_job(self.ljob(), real=False)
        after = sorted((str(p.relative_to(self.dst)), p.read_text()) for p in self.dst.rglob("*") if p.is_file())
        self.assertEqual(res.code, 0)
        self.assertEqual(before, after)
        self.assertFalse((self.root / "lbk").exists())

    def test_sync_local_to_local(self):
        self.scenario()
        _, res, _ = self.run_job(self.ljob(), real=True)
        self.assertEqual(res.code, 0, res.errors)
        self.assertEqual(self.read(self.dst, "new.txt"), "new")
        self.assertEqual(self.read(self.dst, "changed.txt"), "changed-new-content")
        self.assertEqual(self.read(self.dst, "sub/in.txt"), "in")
        self.assertFalse((self.dst / "gone.txt").exists())
        kept = [p for p in (self.root / "lbk").rglob("*") if p.is_file()]
        self.assertEqual(sorted((p.name, p.read_text()) for p in kept), [("changed.txt", "old"), ("gone.txt", "gone-content")])
        for p in kept:
            self.assertEqual(p.relative_to(self.root / "lbk").parts[0], "src")      # label folder, then a timestamp folder

    def test_copy_local_to_local_never_deletes(self):
        self.scenario()
        _, res, _ = self.run_job(self.ljob(mode="copy"), real=True)
        self.assertEqual(res.code, 0, res.errors)
        self.assertEqual(self.read(self.dst, "gone.txt"), "gone-content")
        self.assertEqual(self.read(self.dst, "changed.txt"), "changed-new-content")
        kept = [p for p in (self.root / "lbk").rglob("*") if p.is_file()]
        self.assertEqual([(p.name, p.read_text()) for p in kept], [("changed.txt", "old")])

    def test_exported_script_for_local(self):
        self.scenario()
        name, text = core.export_script(self.ljob(name="exp-local"), RCLONE)
        script = self.root / name
        script.write_bytes(text.encode("utf-8"))
        cmd = (["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)] if core.IS_WIN else ["sh", str(script)])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(self.dst, "changed.txt"), "old")               # dry run by default
        r = subprocess.run(cmd + ["-Execute" if core.IS_WIN else "--execute"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read(self.dst, "changed.txt"), "changed-new-content")


if __name__ == "__main__":
    unittest.main()
