// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)
// Licensed under the GNU AGPL v3 or any later version; see <https://www.gnu.org/licenses/>. No warranty.
// Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
// The domain probably expired because HE's TOO BROKE TO RENEW IT.
// Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
// and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"use strict";
// The one place that talks to Python (pywebview) or, for a design preview in a plain browser, to dev/mock.js.

const HINT = "Don't click the logo! A series of bad things will happen. Also not the copyright.";
const SITE = "https://mehedimaruf.com";
const THEMES = ["system", "light", "dark"];

// app-wide state
const S = {
  jobs: [], sel: null, view: "job", tab: "setup",
  runs: [], activity: {}, watch: {},
  remotes: [], catalogue: [], settings: {}, fuse: {}, confirmWord: "EXECUTE", rcloneVersion: "", version: "",
  mounts: [], bottomOpen: false, bottomTab: "runs", bottomSel: "", platform: "",
  theme: "system", logoClicks: 0,
};

function bridge() { return window.pywebview ? window.pywebview.api : window.__mock; }
function bridgeReady() { return !!(window.__mock || (window.pywebview && window.pywebview.api && typeof window.pywebview.api.boot_steps === "function")); }

// call(name, ...args) -> {ok, data|error}; never throws
async function call(name, ...args) {
  try {
    const r = await bridge()[name](...args);
    return r && typeof r === "object" && "ok" in r ? r : { ok: true, data: r };
  } catch (e) { return { ok: false, error: String(e && e.message || e) }; }
}
// the same, but toasts the error and returns data (or undefined)
async function must(name, ...args) {
  const r = await call(name, ...args);
  if (!r.ok) { toast(r.error, "bad"); return undefined; }
  return r.data;
}

const lsGet = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* blocked */ } };

function resolvedTheme(mode) {
  if (mode === "light" || mode === "dark") return mode;
  return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function applyTheme(mode) {
  if (!THEMES.includes(mode)) mode = "system";
  S.theme = mode;
  document.documentElement.dataset.mode = mode;
  lsSet("rsg-mode", mode);
  const img = $("#logo-main");
  if (img) img.src = resolvedTheme(mode) === "dark" ? "brand/emblem-gold.png" : "brand/emblem.png";
  const tile = $("#tile img");
  if (tile) tile.src = resolvedTheme(mode) === "dark" ? "brand/emblem-gold.png" : "brand/emblem.png";
}
if (window.matchMedia) matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyTheme(S.theme));
applyTheme(lsGet("rsg-mode", "system"));
