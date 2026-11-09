# Copyright (C) 2026 Mehedi Maruf
# SPDX-License-Identifier: AGPL-3.0-or-later
# Contact: rsimplone@mehedimaruf.com (developer), license@mehedimaruf.com (licence)
# Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
# The domain probably expired because HE's TOO BROKE TO RENEW IT.
# Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
# and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"""Update check: strict tag parsing, newer-than logic, silent failure, and the API only asks GitHub when allowed.
The network is always mocked."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["RSG_TESTING"] = "1"
from rsg import api, core, updates  # noqa: E402


def reply(obj):
    return mock.MagicMock(__enter__=lambda s: io.BytesIO(json.dumps(obj).encode()), __exit__=lambda *a: False)


class ParseTests(unittest.TestCase):
    def test_tags(self):
        self.assertEqual(updates.parse("v2.2.1"), (2, 2, 1))
        for bad in ("2.2.1", "v2.2", "v2.2.1-rc1", "v2.2.1 ", "v2.2.1/../x", "", None, 5):
            self.assertIsNone(updates.parse(bad), bad)

    def test_newer(self):
        self.assertTrue(updates.is_newer("2.2.1", "v2.2.2"))
        self.assertTrue(updates.is_newer("2.2.9", "v2.10.0"))
        self.assertFalse(updates.is_newer("2.2.1", "v2.2.1"))
        self.assertFalse(updates.is_newer("2.2.1", "v2.1.9"))
        self.assertFalse(updates.is_newer("2.2.1", "latest"))

    def test_release_url_never_uses_unchecked_text(self):
        self.assertEqual(updates.release_url("v2.2.2"), updates.RELEASES + "/tag/v2.2.2")
        self.assertEqual(updates.release_url("v1.0.0/../../evil"), updates.RELEASES)


class FetchTests(unittest.TestCase):
    def test_good_and_bad_replies(self):
        with mock.patch.object(updates.urllib.request, "urlopen", lambda *a, **k: reply({"tag_name": "v2.3.0"})):
            self.assertEqual(updates.fetch_latest(), "v2.3.0")
        for body in ({"tag_name": "v9.9.9", "prerelease": True}, {"tag_name": "v9.9.9", "draft": True}, {"tag_name": "evil"}, [1]):
            with mock.patch.object(updates.urllib.request, "urlopen", lambda *a, _b=body, **k: reply(_b)):
                self.assertIsNone(updates.fetch_latest(), body)

    def test_offline_is_silent(self):
        with mock.patch.object(updates.urllib.request, "urlopen", mock.Mock(side_effect=OSError("offline"))):
            self.assertIsNone(updates.fetch_latest())


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["RSG_HOME"] = self.tmp
        self.api = api.Api()
        self.api.store = core.load_store()
        self.api._save = lambda: None

    def tearDown(self):
        os.environ["RSG_HOME"] = os.path.join(self.tmp, "x")   # never unset: point at another throwaway place
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_off_by_default_never_touches_the_network(self):
        with mock.patch.object(updates, "fetch_latest", mock.Mock(side_effect=AssertionError("network"))):
            self.assertEqual(self.api.update_check()["data"], {"newer": False})
            self.api.store.settings["update_check"] = False
            self.assertEqual(self.api.update_check()["data"], {"newer": False})

    def test_on_asks_once_a_day_and_reports_newer(self):
        self.api.store.settings["update_check"] = True
        calls = []

        def fake():
            calls.append(1)
            return "v99.0.0"
        with mock.patch.object(updates, "fetch_latest", fake):
            first = self.api.update_check()["data"]
            second = self.api.update_check()["data"]
        self.assertTrue(first["newer"])
        self.assertEqual(first["latest"], "99.0.0")
        self.assertEqual(second["latest"], "99.0.0")
        self.assertEqual(len(calls), 1)

    def test_check_now_reports_failure(self):
        with mock.patch.object(updates, "fetch_latest", lambda: None):
            self.assertTrue(self.api.update_check(True)["data"]["failed"])


if __name__ == "__main__":
    unittest.main()
