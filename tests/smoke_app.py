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
"""Opens the REAL app (splash, then the main window) against throwaway folders, drives it through its own page
script, and writes what it saw to a JSON file. Usage:  python tests/smoke_app.py RESULT.json
Needs pywebview and rclone; opens windows on screen for about 15 seconds."""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(result_path: str) -> int:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    os.environ["RSG_HOME"] = str(root / "home")
    src, dst = root / "src", root / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "a.txt").write_text("alpha", encoding="utf-8")
    (src / "sub").mkdir()
    (src / "sub" / "b.txt").write_text("bravo", encoding="utf-8")
    out = {"checks": {}}

    def driver(window, splash, api):
        try:
            t0 = time.time()
            while time.time() - t0 < 40 and not api._ui_ready.is_set():
                time.sleep(0.2)
            out["checks"]["ui_ready"] = api._ui_ready.is_set()
            time.sleep(1.0)
            import webview
            out["checks"]["windows_open_after_boot"] = len(webview.windows)      # the splash closes itself: expect 1
            job = api.new_job("copy")["data"]
            job.update(dest_kind="local", source=str(src), target=str(dst))
            api.save_job(job)
            window.evaluate_js("(async()=>{const j=await call('jobs'); S.jobs=j.data; S.sel=S.jobs[0].id; S.view='job'; S.tab='setup'; renderAll();})()")
            time.sleep(1.0)
            out["checks"]["slots"] = window.evaluate_js("document.querySelectorAll('.slot').length")
            out["checks"]["title_input"] = window.evaluate_js("document.querySelector('.jobhead .name').value")
            out["checks"]["theme_logo"] = window.evaluate_js("document.querySelector('#logo-main').getAttribute('src')")
            out["checks"]["has_dry_btn"] = window.evaluate_js("[...document.querySelectorAll('#hdr-actions button')].some(b=>b.textContent.includes('Dry run'))")
            window.evaluate_js("[...document.querySelectorAll('#hdr-actions button')].find(b=>b.textContent.includes('Dry run')).click()")
            deadline = time.time() + 30
            while time.time() < deadline:
                state = window.evaluate_js("(S.runs[0]||{}).state")
                if state in ("done", "failed"):
                    break
                time.sleep(0.4)
            out["checks"]["run_state"] = state
            out["checks"]["tab_after_start"] = window.evaluate_js("S.tab")
            out["checks"]["dst_untouched_by_dry_run"] = sorted(p.name for p in dst.iterdir()) == []
            out["checks"]["console_lines"] = len(api.mgr.console(next(iter(api.mgr.records)), 0)["lines"])
            window.evaluate_js("document.querySelector('#logo-btn').click()")
            time.sleep(0.6)
            out["checks"]["theme_after_click"] = window.evaluate_js("document.documentElement.dataset.mode")
            out["checks"]["js_errors"] = window.evaluate_js("(window.__errs||[]).length")
        except Exception as exc:  # noqa: BLE001
            out["error"] = repr(exc)
        finally:
            Path(result_path).write_text(json.dumps(out, indent=2), encoding="utf-8")
            api.shutdown()
            window.destroy()

    from rsg import app
    app.main(driver)
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
