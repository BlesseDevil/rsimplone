# Copyright (C) 2026 Mehedi Maruf
# SPDX-License-Identifier: AGPL-3.0-or-later
# Contact: rsimplone@mehedimaruf.com (developer), license@mehedimaruf.com (licence). See rsg/core.py for the full notice.
# Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
# The domain probably expired because HE's TOO BROKE TO RENEW IT.
# Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
# and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"""Remote management against real rclone, in a THROWAWAY rclone.conf. The real one is never touched (its mtime is checked)."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["RSG_TESTING"] = "1"
_SAFE_HOME = os.path.join(tempfile.gettempdir(), "rsg-tests-never-real")
os.environ["RSG_HOME"] = _SAFE_HOME
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rsg import api as apimod, core, remotes  # noqa: E402

RCLONE = core.find_rclone()


def _real_conf_mtime():
    try:
        out = subprocess.run([RCLONE, "config", "file"], capture_output=True, text=True, timeout=20).stdout.strip().splitlines()[-1]
        return out, os.path.getmtime(out)
    except (OSError, IndexError):
        return "", None


@unittest.skipUnless(RCLONE, "rclone not installed")
class TestRemotes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("RCLONE_CONFIG", None)
        core.set_config_path("")
        cls.real = _real_conf_mtime()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("RCLONE_CONFIG", None)
        core.set_config_path("")
        path, mtime = _real_conf_mtime()
        if cls.real[1] is not None:
            assert mtime == cls.real[1], "the REAL rclone.conf was modified by a test"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["RSG_HOME"] = str(self.root / "home")
        self.conf = str(self.root / "t.conf")
        core.set_config_path(self.conf)
        remotes._backed_up[0] = False

    def tearDown(self):
        core.set_config_path("")
        os.environ["RSG_HOME"] = _SAFE_HOME
        self.tmp.cleanup()

    def names(self):
        return dict(core.list_remotes(RCLONE))

    def test_providers_come_with_schema_and_hide_internal_ones(self):
        ps = {p["name"]: p for p in remotes.providers(RCLONE)}
        self.assertIn("drive", ps)
        self.assertIn("s3", ps)
        order = [p["name"] for p in remotes.providers(RCLONE)]
        self.assertEqual(order[:2], ["drive", "google photos"], "Drive and Photos first")
        rest = [p["description"].lower() for p in remotes.providers(RCLONE)[2:]]
        self.assertEqual(rest, sorted(rest), "the rest in rclone's alphabetical order")
        sftp = {o["name"]: o for o in ps["sftp"]["options"]}
        self.assertTrue(sftp["pass"]["password"])
        self.assertTrue(any(o["advanced"] for o in ps["sftp"]["options"]))

    def test_create_update_describe_delete_without_leaking_secrets(self):
        step = remotes.start(RCLONE, "mys3", "s3", {"provider": "Other", "access_key_id": "AKTESTKEYID", "secret_access_key": "SECRET-TEST-VALUE", "endpoint": "http://x.invalid"})
        self.assertTrue(step["done"])
        self.assertEqual(self.names().get("mys3"), "s3")
        d = remotes.describe(RCLONE, "mys3")
        self.assertEqual(d["values"].get("endpoint"), "http://x.invalid")
        self.assertNotIn("SECRET-TEST-VALUE", str(d))
        self.assertNotIn("AKTESTKEYID", str(d), "key-like fields are never sent to the page")
        remotes.update(RCLONE, "mys3", {"endpoint": "http://y.invalid"})
        self.assertEqual(remotes.describe(RCLONE, "mys3")["values"]["endpoint"], "http://y.invalid")
        step = remotes.start(RCLONE, "mysftp", "sftp", {"host": "h.invalid", "user": "u", "pass": "-pa ss'word"})
        text = Path(self.conf).read_text(encoding="utf-8")
        self.assertNotIn("pa ss'word", text, "an sftp password is stored obscured, never as typed")
        remotes.delete(RCLONE, "mys3")
        self.assertNotIn("mys3", self.names())
        self.assertIn("mysftp", self.names())

    def test_drive_asks_a_follow_up_question_as_data(self):
        step = remotes.start(RCLONE, "mydrive", "drive", {"scope": "drive"})
        self.assertFalse(step["done"])
        self.assertTrue(step["state"])
        self.assertTrue(step["question"]["help"])

    def test_bad_names_and_values_are_refused(self):
        for bad in ("", "-x", "a:b", "x" * 80):
            with self.assertRaises(remotes.RemoteError):
                remotes.start(RCLONE, bad, "s3", {})
        with self.assertRaises(remotes.RemoteError):
            remotes.start(RCLONE, "ok", "nope", {})
        with self.assertRaises(remotes.RemoteError):
            remotes.start(RCLONE, "ok2", "s3", {"endpoint": "a\nb"})
        with self.assertRaises(remotes.RemoteError):
            remotes.start(RCLONE, "ok3", "s3", {"Bad Name": "x"})

    def test_copy_keeps_the_login_changes_only_the_root_folder_and_leaves_the_source_alone(self):
        remotes.start(RCLONE, "mydrive", "drive", {"scope": "drive"})
        conf = Path(self.conf)
        text = conf.read_text(encoding="utf-8")
        conf.write_text(text.rstrip("\n") + '\ntoken = {"access_token":"TESTTOKEN123","expiry":"2030-01-01T00:00:00Z"}\nroot_folder_id = OLDFOLDER\n', encoding="utf-8")
        before = conf.read_text(encoding="utf-8")
        remotes.copy_remote(RCLONE, "mydrive", "second", {"root_folder_id": "NewFolder_123-x"})
        after = conf.read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before.rstrip("\n")), "the source section is byte-for-byte unchanged")
        new = after[len(before.rstrip("\n")):]
        self.assertIn('token = {"access_token":"TESTTOKEN123"', new, "same login")
        self.assertIn("root_folder_id = NewFolder_123-x", new)
        self.assertNotIn("OLDFOLDER", new)
        self.assertEqual(self.names().get("second"), "drive")
        remotes.copy_remote(RCLONE, "mydrive", "notoken", {"root_folder_id": "AbCdEfGh1"}, copy_token=False)
        self.assertNotIn("TESTTOKEN123", conf.read_text(encoding="utf-8").split("[notoken]")[1], "no login copied when unticked")
        remotes.copy_remote(RCLONE, "mydrive", "third", {"root_folder_id": ""})      # empty = top of the drive
        self.assertNotIn("root_folder_id", conf.read_text(encoding="utf-8").split("[third]")[1])
        for bad in ({"root_folder_id": "a/b"}, {"root_folder_id": "x y"}, {"token": "x"}, {"scope": "x"}):
            with self.assertRaises(remotes.RemoteError):
                remotes.copy_remote(RCLONE, "mydrive", "fourth", bad)
        with self.assertRaises(remotes.RemoteError):
            remotes.copy_remote(RCLONE, "mydrive", "second", {})                       # name taken
        remotes.start(RCLONE, "mys3", "s3", {"provider": "Other"})
        with self.assertRaises(remotes.RemoteError):
            remotes.copy_remote(RCLONE, "mys3", "s3copy", {})                           # no root folder setting

    def test_copy_login_replaces_only_the_token_of_the_chosen_remotes(self):
        for n, scope in (("a", "drive"), ("b", "drive.readonly"), ("c", "drive")):
            remotes.start(RCLONE, n, "drive", {"scope": scope})
        remotes.start(RCLONE, "s", "s3", {"provider": "Other"})
        conf = Path(self.conf)
        t = conf.read_text(encoding="utf-8")
        t = t.replace("[a]\n", '[a]\ntoken = {"access_token":"GOODTOKEN"}\n').replace("[b]\n", '[b]\ntoken = {"access_token":"EXPIRED_B"}\n')
        conf.write_text(t, encoding="utf-8")
        self.assertEqual(sorted(remotes.login_targets(RCLONE, "a")), ["b", "c"])
        remotes.copy_login(RCLONE, "a", ["b", "c"])
        after = conf.read_text(encoding="utf-8")
        sec = lambda n: after.split("[%s]" % n)[1].split("[")[0]
        self.assertIn("GOODTOKEN", sec("b"))
        self.assertNotIn("EXPIRED_B", after)
        self.assertIn("GOODTOKEN", sec("c"))
        self.assertIn("scope = drive.readonly", sec("b"), "the target's other settings are untouched")
        self.assertIn("GOODTOKEN", sec("a"), "the source keeps its login")
        for src, dsts in (("s", ["a"]), ("a", ["s"]), ("a", []), ("a", ["a"]), ("zzz", ["a"])):
            with self.assertRaises(remotes.RemoteError):
                remotes.copy_login(RCLONE, src, dsts)
        conf.write_text(after.replace('token = {"access_token":"GOODTOKEN"}', ""), encoding="utf-8")
        with self.assertRaises(remotes.RemoteError):
            remotes.copy_login(RCLONE, "a", ["b"])                  # the source has no login to give

    def test_remotes_with_spaces_in_the_name_or_the_type_are_listed(self):
        remotes.start(RCLONE, "my photos", "google photos", {})
        self.assertEqual(self.names().get("my photos"), "google photos")

    def test_rename_edits_the_section_and_remotes_that_point_at_it(self):
        remotes.start(RCLONE, "old", "s3", {"provider": "Other", "endpoint": "http://x.invalid"})
        remotes.start(RCLONE, "other", "s3", {"provider": "Other"})
        remotes.start(RCLONE, "al", "alias", {"remote": "old:folder"})
        remotes.start(RCLONE, "al2", "alias", {"remote": "other:folder"})
        n = remotes.rename_remote(RCLONE, "old", "fresh name")
        self.assertEqual(n, 1, "only the alias that pointed at it followed")
        text = Path(self.conf).read_text(encoding="utf-8")
        self.assertIn("[fresh name]", text)
        self.assertNotIn("[old]", text)
        self.assertIn("remote = fresh name:folder", text)
        self.assertIn("remote = other:folder", text, "unrelated remotes are untouched")
        self.assertIn("endpoint = http://x.invalid", text.split("[fresh name]")[1].split("[")[0])
        self.assertEqual(self.names().get("fresh name"), "s3")
        for bad in ("", "-x", "a:b", "other", "OTHER"):
            with self.assertRaises(remotes.RemoteError):
                remotes.rename_remote(RCLONE, "fresh name", bad)
        with self.assertRaises(remotes.RemoteError):
            remotes.rename_remote(RCLONE, "nope", "x")
        self.assertEqual(remotes.rename_remote(RCLONE, "fresh name", "fresh name"), 0)

    def test_a_password_protected_config_is_never_copied(self):
        remotes.start(RCLONE, "mydrive", "drive", {"scope": "drive"})
        Path(self.conf).write_text("RCLONE_ENCRYPT_V0:\nabc\n", encoding="utf-8")
        with self.assertRaises(Exception):
            remotes.copy_remote(RCLONE, "mydrive", "second", {})

    def test_google_credentials_file_is_read_without_exposing_the_secret(self):
        fake = {"installed": {"client_id": "111-abc.apps.googleusercontent.com", "project_id": "demo", "client_secret": "FAKE-SECRET-VALUE",
                              "auth_uri": "https://a.invalid", "token_uri": "https://t.invalid", "redirect_uris": ["http://localhost"]}}
        r = remotes.parse_google_credentials(__import__("json").dumps(fake))
        self.assertEqual(r["client_id"], "111-abc.apps.googleusercontent.com")
        self.assertIn("client_secret", r["fields"])
        self.assertNotIn("FAKE-SECRET-VALUE", str(r), "the page never receives the secret")
        self.assertEqual(remotes._imported_secret(), "FAKE-SECRET-VALUE")
        web = remotes.parse_google_credentials(__import__("json").dumps({"web": fake["installed"]}))
        self.assertTrue(web["warning"], "a Web client is flagged")
        for bad in ("not json", "[]", "{}", '{"installed": {"client_id": "x"}}', '{"installed": {"client_id": "a.apps.googleusercontent.com", "client_secret": ""}}',
                    '{"installed": {"client_id": "evil;rm", "client_secret": "s"}}', "x" * 30000):
            with self.assertRaises(remotes.RemoteError):
                remotes.parse_google_credentials(bad)
        remotes.clear_imported()
        with self.assertRaises(remotes.RemoteError):
            remotes._imported_secret()

    def test_imported_secret_is_substituted_only_inside_the_backend(self):
        remotes._imported["client_secret"] = "FAKE-SECRET-VALUE"
        pairs, secrets = remotes._pairs(RCLONE, "drive", {"client_id": "111-abc.apps.googleusercontent.com", "client_secret": remotes.IMPORTED_MARK})
        self.assertIn("client_secret=FAKE-SECRET-VALUE", pairs)
        self.assertIn("FAKE-SECRET-VALUE", secrets, "it is scrubbed from any error text")
        self.assertEqual(remotes._scrub("boom FAKE-SECRET-VALUE end", secrets), "boom *** end")
        remotes.clear_imported()
        with self.assertRaises(remotes.RemoteError):
            remotes._pairs(RCLONE, "drive", {"client_secret": remotes.IMPORTED_MARK})

    def test_the_sign_in_link_is_found_in_rclone_output(self):
        line = "2026/11/04 NOTICE: If your browser doesn't open automatically go to the following link: http://127.0.0.1:53682/auth?state=Ab-1_xyz9\n"
        self.assertEqual(remotes._AUTH_URL.search(line).group(0), "http://127.0.0.1:53682/auth?state=Ab-1_xyz9")
        self.assertIsNone(remotes._AUTH_URL.search("see https://evil.example/auth?state=abc"))

    def test_the_first_change_backs_the_config_up(self):
        Path(self.conf).write_text("[old]\ntype = s3\n", encoding="utf-8")
        remotes.start(RCLONE, "mys3", "s3", {"provider": "Other", "endpoint": "http://x.invalid"})
        self.assertEqual(len(list(self.root.glob("t.conf.bak-*"))), 1)

    def test_writes_refuse_to_run_without_a_throwaway_config(self):
        core.set_config_path("")
        os.environ.pop("RCLONE_CONFIG", None)
        with self.assertRaises(RuntimeError):
            remotes.start(RCLONE, "mys3", "s3", {"provider": "Other"})
        with self.assertRaises(RuntimeError):
            remotes.delete(RCLONE, "anything") if "anything" in self.names() else core.guard_config_write()

    def test_every_rclone_call_uses_the_chosen_config_file(self):
        self.assertEqual(remotes.active_config_file(RCLONE), self.conf)
        code, out, _ = core.run_capture(RCLONE, ["config", "file"])
        self.assertIn("t.conf", out)
        self.assertEqual(core.rclone_env()["RCLONE_CONFIG"], self.conf)
        job = core.Job(name="x", dest_kind="remote", mode="copy", source="S", remote="r", target="t")
        core.set_config_path("C:\\a b\\x'y.conf" if core.IS_WIN else "/a b/x'y.conf")
        _name, text = core.export_script(job, "rclone")
        self.assertIn("RCLONE_CONFIG", text)


@unittest.skipUnless(RCLONE, "rclone not installed")
class TestRemoteApi(unittest.TestCase):
    def setUp(self):
        os.environ.pop("RCLONE_CONFIG", None)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ["RSG_HOME"] = str(self.root / "home")
        core.set_config_path("")
        self.api = apimod.Api(lambda: None)
        for step, _ in apimod.BOOT:
            self.api.boot_step(step)
        self.api.scheduler.stop()

    def tearDown(self):
        self.api.shutdown()
        core.set_config_path("")
        os.environ["RSG_HOME"] = _SAFE_HOME
        self.tmp.cleanup()

    def test_own_config_file_is_separate_and_can_start_from_a_copy(self):
        info = self.api.config_info()["data"]
        self.assertEqual(info["mode"], "default")
        r = self.api.set_config("own")
        self.assertTrue(r["ok"], r)
        self.assertEqual(core.config_path(), core.own_config_file())
        step = self.api.remote_start("mine", "s3", {"provider": "Other", "endpoint": "http://x.invalid"})
        self.assertTrue(step["ok"], step)
        self.assertIn("mine", [x["name"] for x in step["data"]["remotes"]])
        self.assertTrue(Path(core.own_config_file()).exists())
        self.assertEqual(self.api.store.settings["config_mode"], "own")
        self.assertFalse(self.api.set_config("custom", "relative.conf")["ok"])
        self.assertFalse(self.api.set_config("weird")["ok"])
        self.api.set_config("default")
        self.assertNotIn("mine", [x["name"] for x in self.api.remotes])

    def test_open_config_file_opens_only_the_active_file_after_a_backup(self):
        opened = []
        real = core.open_in_editor
        core.open_in_editor = lambda p: opened.append(p)
        try:
            self.api.set_config("own")
            self.assertFalse(self.api.open_config_file()["ok"], "no file yet: a clear message, nothing opened")
            self.api.remote_start("mine", "s3", {"provider": "Other", "endpoint": "http://x.invalid"})
            remotes._backed_up[0] = False
            r = self.api.open_config_file()
        finally:
            core.open_in_editor = real
        self.assertTrue(r["ok"], r)
        self.assertEqual(opened, [core.own_config_file()])
        self.assertEqual(len(list(Path(core.own_config_file()).parent.glob("rclone.conf.bak-*"))), 1)

    def test_renaming_a_remote_moves_its_jobs_and_mounts_with_it(self):
        self.api.set_config("own")
        self.api.remote_start("mine", "s3", {"provider": "Other", "endpoint": "http://x.invalid"})
        job = self.api.new_job("copy")["data"]
        job.update(dest_kind="remote", remote="mine", source=str(self.root), target="t")
        self.api.save_job(job)
        spec = self.api.new_mount()["data"]
        spec.update(remote="mine", name="m1")
        self.api.save_mount(spec)
        r = self.api.remote_rename("mine", "renamed")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.api._job(job["id"]).remote, "renamed")
        self.assertEqual([m["remote"] for m in self.api._mount_specs()], ["renamed"])
        self.assertIn("renamed", [x["name"] for x in r["data"]["remotes"]])
        self.assertEqual(core.load_store().jobs[0].remote, "renamed", "saved to disk too")
        self.assertFalse(self.api.remote_rename("renamed", "bad:name")["ok"])

    def test_a_remote_in_use_cannot_be_deleted(self):
        self.api.set_config("own")
        self.api.remote_start("mine", "s3", {"provider": "Other", "endpoint": "http://x.invalid"})
        job = self.api.new_job("copy")["data"]
        job.update(dest_kind="remote", remote="mine", source=str(self.root), target="t")
        self.api.save_job(job)
        r = self.api.remote_delete("mine")
        self.assertFalse(r["ok"])
        self.assertIn(job["name"], r["error"])
        self.assertEqual(self.api.remote_uses("mine")["data"]["jobs"], [job["name"]])
        self.api.delete_job(job["id"])
        self.assertTrue(self.api.remote_delete("mine")["ok"])


if __name__ == "__main__":
    unittest.main()
