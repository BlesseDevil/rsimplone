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
"""Tests for move, flags, scheduling, crypt, mounts and simultaneous runs. Real rclone against throwaway folders;
results are checked by file CONTENT, never by counts alone. Run with:  python -m unittest discover -s tests -v"""
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rsg import core, flags, mounts, runs, schedule  # noqa: E402

RCLONE = core.find_rclone()


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
        self.src = self.root / "src"
        self.dst = self.root / "dst"
        self.bk = self.root / "bk"
        for p in (self.src, self.dst, self.bk):
            p.mkdir()
        self.mgr = runs.RunManager(lambda: RCLONE)

    def tearDown(self):
        os.environ.pop("RSG_HOME", None)
        self.tmp.cleanup()

    def write(self, base, rel, text):
        p = Path(base) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def tree(self, base):
        return {str(p.relative_to(base)).replace("\\", "/"): p.read_text(encoding="utf-8")
                for p in Path(base).rglob("*") if p.is_file()}

    def allow(self, j, ts=None):
        """Record a successful dry run on disk, the way the app does (the unlock is read from jobs.json)."""
        j.dry_sig, j.dry_ts = core.job_signature(j), (ts if ts is not None else time.time())
        store = core.load_store()
        store.jobs = [x for x in store.jobs if x.id != j.id] + [j]
        core.save_store(store)

    def job(self, **kw):
        j = core.Job(name="t", dest_kind="local", mode="move", source=str(self.src), target=str(self.dst), backup_root=str(self.bk))
        for k, v in kw.items():
            setattr(j, k, v)
        return j


class TestFlags(unittest.TestCase):
    SAMPLE = (
        "Flags for anything which can copy a file (flag group Copy):\n"
        "      --check-first                                 Do all the checks before starting transfers\n"
        "  -c, --checksum                                    Check for changes with size & checksum\n"
        "      --max-transfer SizeSuffix                     Maximum size of data to transfer (default off)\n"
        "      --multi-thread-streams int                    Number of streams to use (default 4)\n"
    )

    def test_parse(self):
        got = {f["name"]: f for f in flags.parse_help_flags(self.SAMPLE)}
        self.assertEqual(got["--check-first"]["type"], "bool")
        self.assertEqual(got["--checksum"]["short"], "-c")
        self.assertEqual(got["--multi-thread-streams"]["default"], "4")
        self.assertEqual(got["--multi-thread-streams"]["type"], "int")
        self.assertEqual(got["--max-transfer"]["help"], "Maximum size of data to transfer")
        self.assertEqual(got["--check-first"]["group"], "Copy")

    @unittest.skipUnless(RCLONE, "rclone not installed")
    def test_parse_real_rclone(self):
        _code, out, _err = core.run_capture(RCLONE, ["help", "flags"], timeout=60)
        cat = flags.parse_help_flags(out)
        names = {f["name"] for f in cat}
        self.assertGreater(len(cat), 200)
        for needed in ("--bwlimit", "--transfers", "--checkers", "--exclude", "--tpslimit"):
            self.assertIn(needed, names)
        self.assertTrue(next(f for f in cat if f["name"] == "--dry-run")["denied"])

    def test_denied(self):
        for bad in ("--dry-run", "--backup-dir", "--use-json-log", "--log-file", "--stats", "--stats-one-line", "--suffix", "--rc-addr", "--config"):
            self.assertTrue(flags.is_denied(bad), bad)
        self.assertFalse(flags.is_denied("--bwlimit"))
        self.assertEqual(flags.denied_in_tokens(["-P", "--bwlimit", "1M", "-vv", "--stats=1s", "-I"]), ["-P", "-v", "-v", "--stats"])
        with self.assertRaises(ValueError):
            flags.merge({}, {"--dry-run": True})
        with self.assertRaises(ValueError):
            flags.merge({}, {}, "--exclude x --backup-dir=y")

    def test_merge(self):
        m = {"--checkers": "2", "--check-first": None, "--fast-list": None}
        args = flags.merge(m, {"--checkers": "6", "--check-first": False, "--exclude": ["*.tmp", "a b"]}, "--bwlimit 1M")
        self.assertEqual(args, ["--checkers", "6", "--fast-list", "--exclude", "*.tmp", "--exclude", "a b", "--bwlimit", "1M"])

    def test_clean_overrides_keeps_only_differences(self):
        cat = flags.parse_help_flags(self.SAMPLE)
        got = flags.clean_overrides({"--multi-thread-streams": "4", "--max-transfer": "10G", "--dry-run": True,
                                     "--check-first": True, "--checksum": False, "--junk": ""}, cat)
        self.assertEqual(got, {"--max-transfer": "10G", "--check-first": True, "--checksum": False})

    def test_job_flags_reach_command_line_and_cannot_touch_managed_ones(self):
        j = core.Job(mode="copy", source="S", remote="r", target="t", flags={"--checkers": "9", "--fast-list": False},
                     extra="--exclude '*.tmp'")
        a = core.build_args(j, True, "STAMP")
        self.assertEqual(a[a.index("--checkers") + 1], "9")
        self.assertNotIn("--fast-list", a)
        self.assertIn("--exclude", a)
        self.assertEqual(a.count("--checkers"), 1)
        j.extra = "--dry-run"
        self.assertTrue(any("managed" in e for e in core.validate_job(j, "rclone")))


class TestSchedule(unittest.TestCase):
    def test_interval(self):
        now = datetime(2026, 1, 5, 10, 0)
        s = {"enabled": True, "kind": "interval", "every_min": 60, "last_fired": (now - timedelta(minutes=61)).timestamp()}
        self.assertTrue(schedule.is_due(s, now))
        s["last_fired"] = (now - timedelta(minutes=30)).timestamp()
        self.assertFalse(schedule.is_due(s, now))
        self.assertEqual(schedule.next_run(s, now), now + timedelta(minutes=30))
        self.assertFalse(schedule.is_due({"enabled": False, "kind": "interval", "last_fired": 1}, now))

    def test_daily_and_missed_slot(self):
        s = {"enabled": True, "kind": "daily", "time": "02:00", "last_fired": 0}
        self.assertTrue(schedule.is_due(s, datetime(2026, 1, 5, 2, 30)))
        self.assertFalse(schedule.is_due(s, datetime(2026, 1, 5, 9, 0)), "a slot missed by more than the grace period is skipped")
        s["last_fired"] = datetime(2026, 1, 5, 2, 1).timestamp()
        self.assertFalse(schedule.is_due(s, datetime(2026, 1, 5, 2, 30)), "already fired for this slot")
        self.assertEqual(schedule.next_run(s, datetime(2026, 1, 5, 9, 0)), datetime(2026, 1, 6, 2, 0))

    def test_weekly(self):
        s = {"enabled": True, "kind": "weekly", "time": "23:30", "days": [2], "last_fired": 0}     # Wednesday
        mon = datetime(2026, 1, 5, 12, 0)
        self.assertEqual(mon.weekday(), 0)
        self.assertEqual(schedule.next_run(s, mon), datetime(2026, 1, 7, 23, 30))
        self.assertTrue(schedule.is_due(s, datetime(2026, 1, 7, 23, 45)))
        self.assertFalse(schedule.is_due(s, datetime(2026, 1, 8, 3, 0)), "Thursday is not a chosen day")

    def test_tick_real_needs_matching_signature(self):
        j = core.Job(name="x", mode="copy", source="S", remote="r", target="t",
                     schedule={"enabled": True, "kind": "daily", "time": "02:00", "real": True, "real_sig": "old"})
        fired = []
        sched = schedule.Scheduler(lambda: [j], lambda job, real: fired.append(real), lambda i: False, lambda: None, core.job_signature)
        sched.tick(datetime(2026, 1, 5, 2, 10))
        self.assertEqual(fired, [False], "a changed job must fall back to a dry run")
        j.schedule.update(real_sig=core.job_signature(j), last_fired=0)
        sched.tick(datetime(2026, 1, 6, 2, 10))
        self.assertEqual(fired, [False, True])
        sched.tick(datetime(2026, 1, 6, 2, 11))
        self.assertEqual(len(fired), 2, "it must not fire twice for one slot")

    def test_tick_skips_busy_job(self):
        j = core.Job(name="x", mode="copy", source="S", remote="r", target="t",
                     schedule={"enabled": True, "kind": "daily", "time": "02:00"})
        fired = []
        sched = schedule.Scheduler(lambda: [j], lambda job, real: fired.append(1), lambda i: True, lambda: None, core.job_signature)
        sched.tick(datetime(2026, 1, 5, 2, 10))
        self.assertEqual(fired, [])


class TestMountSpec(unittest.TestCase):
    def test_args_and_validation(self):
        mp = os.path.join(tempfile.gettempdir(), "rsg-mnt-does-not-exist-%d" % os.getpid())
        s = mounts.MountSpec(name="m", remote="r", path="a/b", mountpoint=mp, read_only=True, extra="--dir-cache-time 5m")
        a = mounts.mount_args(s)
        self.assertEqual(a[:3], ["mount", "r:a/b", mp])
        self.assertIn("--read-only", a)
        self.assertIn("--dir-cache-time", a)
        s.extra = "--rc"
        self.assertTrue(any("managed" in e for e in mounts.validate_mount(s)))
        self.assertIn("Choose a remote", " ".join(mounts.validate_mount(mounts.MountSpec())))
        self.assertIn("ok", mounts.fuse_status())


class TestMove(Base):
    def test_move_needs_dry_run_then_moves_exactly_the_right_files(self):
        self.write(self.src, "a.txt", "alpha")
        self.write(self.src, "sub/b.txt", "bravo")
        self.write(self.dst, "a.txt", "OLD alpha")           # will be replaced -> old copy must land in backup
        j = self.job()
        with self.assertRaises(runs.RunRefused):
            self.mgr.start_job(j, True)
        rec = wait_done(self.mgr, self.mgr.start_job(j, False))
        self.assertEqual(rec.state, "done")
        self.assertEqual(self.tree(self.src), {"a.txt": "alpha", "sub/b.txt": "bravo"}, "a dry run must not touch anything")
        self.assertEqual(self.tree(self.dst), {"a.txt": "OLD alpha"})
        with self.assertRaises(runs.RunRefused):             # a dry run only counts once the app records it
            self.mgr.start_job(j, True)
        self.allow(j)
        rec = wait_done(self.mgr, self.mgr.start_job(j, True))
        self.assertEqual(rec.state, "done", rec.console)
        self.assertEqual(self.tree(self.dst), {"a.txt": "alpha", "sub/b.txt": "bravo"})
        self.assertEqual(self.tree(self.src), {}, "move removes the transferred files from the source")
        kept = {k.split("/", 2)[-1]: v for k, v in self.tree(self.bk).items()}
        self.assertEqual(list(kept.values()), ["OLD alpha"], "the replaced destination file is kept in the backup folder")

    def test_dry_run_signature_goes_stale_when_job_changes(self):
        self.write(self.src, "a.txt", "alpha")
        j = self.job()
        self.allow(j)
        j.flags = {"--max-age": "1d"}
        with self.assertRaises(runs.RunRefused):
            self.mgr.start_job(j, True)
        self.assertEqual(self.tree(self.src), {"a.txt": "alpha"})

    def test_expired_dry_run_is_refused(self):
        self.write(self.src, "a.txt", "alpha")
        j = self.job()
        self.allow(j, time.time() - 25 * 3600)
        with self.assertRaises(runs.RunRefused):
            self.mgr.start_job(j, True)


class TestSimultaneous(Base):
    def test_two_jobs_run_together_and_overlap_is_refused(self):
        d2, b2, s2 = self.root / "dst2", self.root / "bk2", self.root / "src2"
        for p in (d2, b2, s2):
            p.mkdir()
        self.write(self.src, "one.txt", "1" * 200000)
        self.write(s2, "two.txt", "2" * 200000)
        a = self.job(id="a", name="A", mode="copy")
        b = self.job(id="b", name="B", mode="copy", source=str(s2), target=str(d2), backup_root=str(b2))
        ra = self.mgr.start_job(a, False)
        rb = self.mgr.start_job(b, False)
        self.assertNotEqual(ra, rb)
        for r in (ra, rb):
            self.assertEqual(wait_done(self.mgr, r).state, "done")
        # a second job aimed at the same destination must be refused while the first one runs
        slow = self.job(id="c", name="C", mode="copy")
        rec = self.mgr.records[self.mgr.start_job(slow, False)]
        clash = self.job(id="d", name="D", mode="copy", source=str(s2), target=str(self.dst / "inner"), backup_root=str(b2))
        if rec.state == "running":
            with self.assertRaises(runs.RunRefused):
                self.mgr.start_job(clash, False)
        self.assertIsNotNone(runs.conflicts(clash, [slow]), "nested destinations conflict")
        self.assertIsNone(runs.conflicts(b, [a]), "unrelated places do not")
        wait_done(self.mgr, rec.id)
        self.assertEqual(self.tree(self.dst), {}, "dry runs wrote nothing")

    def test_console_has_rclone_layout_not_json(self):
        self.write(self.src, "x.txt", "x")
        rec = wait_done(self.mgr, self.mgr.start_job(self.job(mode="copy"), False))
        text = "\n".join(rec.console)
        self.assertNotIn('{"', text)
        self.assertRegex(text, r"\d{4}/\d\d/\d\d \d\d:\d\d:\d\d \w+\s*: ")


@unittest.skipUnless(RCLONE, "rclone not installed")
class TestCrypt(Base):
    def test_create_crypt_and_roundtrip_without_leaking_password(self):
        cfg = self.root / "rclone.conf"
        os.environ["RCLONE_CONFIG"] = str(cfg)
        try:
            os.environ["RCLONE_CONFIG_RAWR_TYPE"] = "alias"
            os.environ["RCLONE_CONFIG_RAWR_REMOTE"] = str(self.dst)
            secret = "correct-horse-battery-staple-9"
            core.create_crypt_remote(RCLONE, "vault", "rawr:", secret, "salty-salt")
            remotes = dict(core.list_remotes(RCLONE))
            self.assertEqual(remotes.get("vault"), "crypt")
            with self.assertRaises(core.RcloneError):
                core.create_crypt_remote(RCLONE, "vault", "rawr:", secret)          # name already used
            self.write(self.src, "private.txt", "top secret body")
            j = core.Job(name="c", dest_kind="remote", mode="copy", source=str(self.src), remote="vault", target="", backup_root="")
            j.target = "docs"
            rec = wait_done(self.mgr, self.mgr.start_job(j, True))
            self.assertEqual(rec.state, "done", list(rec.console))
            names = [p.name for p in self.dst.rglob("*") if p.is_file()]
            self.assertEqual(len(names), 1)
            self.assertNotIn("private", names[0], "file names are encrypted on disk")
            self.assertNotIn(b"top secret body", next(p for p in self.dst.rglob("*") if p.is_file()).read_bytes())
            code, out, _ = core.run_capture(RCLONE, ["cat", "vault:docs/private.txt"])
            self.assertEqual(out, "top secret body", "reading through the crypt remote decrypts")
            blob = json.dumps([vars(j)]) + "\n".join(rec.console) + " ".join(core.build_args(j, True, "S"))
            self.assertNotIn(secret, blob)
        finally:
            for k in ("RCLONE_CONFIG", "RCLONE_CONFIG_RAWR_TYPE", "RCLONE_CONFIG_RAWR_REMOTE"):
                os.environ.pop(k, None)

    def test_create_crypt_validates_input(self):
        for args in (("bad name!", "r:", "pw"), ("ok", "", "pw"), ("ok", "r:", "")):
            with self.assertRaises(core.RcloneError):
                core.create_crypt_remote(RCLONE, *args)


if __name__ == "__main__":
    unittest.main()
