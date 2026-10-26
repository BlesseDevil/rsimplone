// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)
// Licensed under the GNU AGPL v3 or any later version; see <https://www.gnu.org/licenses/>. No warranty.
// Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
// The domain probably expired because HE's TOO BROKE TO RENEW IT.
// Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
// and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"use strict";
// The splash window: runs the real start-up steps (each one a call into Python), narrates them, then asks
// Python to reveal the main window and close this one. Clicking the mark changes the theme.

const VERBOSE = {
  settings: ["Reading your jobs…", "Checking the data folder…"],
  rclone: ["Looking for rclone…", "Asking rclone for its version…"],
  remotes: ["Reading your remotes (names only)…", "Spotting encrypted remotes…"],
  flags: ["Loading rclone's flag list…", "Indexing flag help for the Config tab…"],
  scheduler: ["Starting the scheduler…", "Checking for mounts to restore…"],
  ready: ["Warming up the window…", "Ready"],
};
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const $s = (s) => document.querySelector(s);

$s("#tile").addEventListener("click", async () => {
  const next = THEMES[(THEMES.indexOf(S.theme) + 1) % THEMES.length];
  applyTheme(next); call("set_theme", next);
});

async function boot() {
  const step = $s("#step"), pct = $s("#pct"), fill = $s("#fill"), trail = $s("#trail");
  $s(".err")?.remove();
  trail.replaceChildren(); fill.style.width = "0"; pct.textContent = "0%"; delete step.dataset.cur;
  const say = (text) => {
    if (step.dataset.cur) { const d = document.createElement("div"); d.textContent = step.dataset.cur; trail.append(d); }
    while (trail.children.length > 3) trail.firstChild.remove();
    step.textContent = text; step.dataset.cur = text;
  };
  try {
    const t0 = Date.now();
    while (!bridgeReady()) { if (Date.now() - t0 > 10000) throw new Error("the app bridge did not start"); await wait(50); }
    call("theme").then((r) => r.ok && applyTheme(r.data));
    const steps = (await call("boot_steps")).data;
    const total = steps.reduce((n, s) => n + (VERBOSE[s.name] || [s.label]).length, 0);
    let done = 0;
    for (const s of steps) {
      const lines = VERBOSE[s.name] || [s.label];
      for (let k = 0; k < lines.length; k++) {
        say(lines[k]);
        if (k === 0) { const r = await call("boot_step", s.name); if (!r.ok) throw new Error(r.error); if (r.data.detail) say(`${s.label.replace(/…$/, "")} · ${r.data.detail}`); }
        done++;
        const p = Math.min(100, Math.round((done / total) * 100));
        fill.style.width = p + "%"; pct.textContent = p + "%";
        await wait(150);
      }
    }
    fill.style.width = "100%"; pct.textContent = "100%";
    await wait(350);
    const r = await call("boot_complete"); if (!r.ok) throw new Error(r.error);
  } catch (e) {
    step.textContent = "Could not start";
    const err = document.createElement("div"); err.className = "err";
    const b = document.createElement("button"); b.textContent = "Retry"; b.onclick = boot;
    err.append(String(e.message || e), b); $s("#splash").append(err);
  }
}
boot();
