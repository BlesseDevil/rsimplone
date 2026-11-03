# Copyright (C) 2026 Mehedi Maruf
# SPDX-License-Identifier: AGPL-3.0-or-later
# Contact: rsimplone@mehedimaruf.com (developer), license@mehedimaruf.com (licence). See rsg/core.py for the full notice.
# Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
# The domain probably expired because HE's TOO BROKE TO RENEW IT.
# Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
# and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"""Opens the REAL app against a throwaway data folder and a throwaway rclone.conf, shows the Remotes page, and fails
if it throws or lacks its buttons. Usage:  python tests/smoke_remotes.py result.json   (needs pywebview and rclone)."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

tmp = tempfile.TemporaryDirectory()
root = Path(tmp.name)
os.environ["RSG_HOME"] = str(root / "home")
os.environ["RCLONE_CONFIG"] = str(root / "t.conf")
os.environ["RSG_TESTING"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
out = {"ok": False}


def driver(window, splash, api):
    try:
        t0 = time.time()
        while time.time() - t0 < 40 and not api._ui_ready.is_set():
            time.sleep(0.2)
        time.sleep(1)
        from rsg import remotes
        remotes.start(api.rclone, "d1", "drive", {"scope": "drive"})
        remotes.start(api.rclone, "d2", "drive", {"scope": "drive"})
        window.evaluate_js("window.__errs=[]; window.addEventListener('error',e=>window.__errs.push(String(e.message)));")
        window.evaluate_js("(async()=>{const r=await call('reload_remotes'); S.remotes=r.data; S.view='remotes'; try{ await pageRemotes(); }catch(e){ window.__errs.push('THROW '+(e.stack||e)); } window.__done=true; })()")
        for _ in range(40):
            if window.evaluate_js("window.__done"):
                break
            time.sleep(0.5)
        out["errs"] = json.loads(window.evaluate_js("JSON.stringify(window.__errs)"))
        page = window.evaluate_js("document.querySelector('#page').innerText")
        out["has_buttons"] = all(t in page for t in ("Open config file", "Reload", "Add remote", "d1", "d2", "Edit", "Copy login", "Copy"))
        out["ok"] = not out["errs"] and out["has_buttons"]
    except Exception as exc:  # noqa: BLE001
        out["error"] = repr(exc)
    finally:
        Path(sys.argv[1]).write_text(json.dumps(out, indent=2), encoding="utf-8")
        api.shutdown()
        window.destroy()


from rsg import app  # noqa: E402

app.main(driver)
sys.exit(0 if out.get("ok") else 1)
