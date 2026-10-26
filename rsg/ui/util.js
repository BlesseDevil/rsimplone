// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)
// Licensed under the GNU AGPL v3 or any later version; see <https://www.gnu.org/licenses/>. No warranty.
// Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
// The domain probably expired because HE's TOO BROKE TO RENEW IT.
// Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
// and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"use strict";
// Small helpers shared by every view: element builder, icons, formatting, toasts, tooltip, dialogs.

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "value" || k === "checked" || k === "disabled" || k === "selected") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const ICONS = {
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  sync: '<path d="M20 11a8 8 0 0 0-14-4.5L4 9M4 13a8 8 0 0 0 14 4.5L20 15"/><path d="M4 4v5h5M20 20v-5h-5"/>',
  move: '<path d="M3 12h14M13 6l6 6-6 6"/><path d="M3 5v14" />',
  cloud: '<path d="M7 18a4 4 0 0 1-.6-7.96A6 6 0 0 1 18 9.5a4.2 4.2 0 0 1-.5 8.5z"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  play: '<path d="M7 5l12 7-12 7z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  gear: '<circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4-4"/>',
  term: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/>',
  drive: '<rect x="3" y="12" width="18" height="7" rx="2"/><path d="M5 12 7.5 5h9L19 12M7 15.5h.01M11 15.5h6"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
  dup: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7"/>',
  alert: '<path d="M12 4 2.5 20h19z"/><path d="M12 10v5M12 17.5v.01"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  chev: '<path d="m6 9 6 6 6-6"/>',
  up: '<path d="m6 15 6-6 6 6"/>',
  open: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  code: '<path d="M8 4 3 12l5 8M16 4l5 8-5 8"/>',
};
function icon(name, cls) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("class", "i" + (cls ? " " + cls : ""));
  s.innerHTML = ICONS[name] || "";
  return s;
}

function bytes(n) {
  n = Number(n) || 0;
  const u = ["B", "KiB", "MiB", "GiB", "TiB"]; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i ? n.toFixed(n >= 100 ? 0 : 1) : Math.round(n)) + " " + u[i];
}
function dur(sec) {
  if (sec == null || !isFinite(sec) || sec < 0) return "-";
  sec = Math.round(sec); const h_ = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h_ ? `${h_}h ${String(m).padStart(2, "0")}m` : m ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}
function ago(ts) {
  if (!ts) return "never";
  const d = (Date.now() / 1000 - ts);
  if (d < 60) return "just now"; if (d < 3600) return Math.round(d / 60) + " min ago";
  if (d < 86400) return Math.round(d / 3600) + " h ago"; return Math.round(d / 86400) + " d ago";
}
const leaf = (p) => (String(p || "").replace(/[\\/]+$/, "").split(/[\\/]/).pop()) || String(p || "");

function toast(text, kind) {
  const t = h("div", { class: "toast " + (kind || "") }, text);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), kind === "bad" ? 9000 : 4500);
}

// ── tooltip: one shared floating panel ───────────────────────────────
let tipTimer = 0;
function tipShow(html, x, y) {
  const tip = $("#tip"); tip.replaceChildren(html); tip.classList.add("on");
  const r = tip.getBoundingClientRect();
  tip.style.left = Math.max(8, Math.min(x, innerWidth - r.width - 8)) + "px";
  tip.style.top = Math.max(8, Math.min(y, innerHeight - r.height - 8)) + "px";
}
function tipHide() { clearTimeout(tipTimer); $("#tip").classList.remove("on"); }
function tooltip(el, build, delay = 380) {
  el.addEventListener("mouseenter", (e) => { clearTimeout(tipTimer); tipTimer = setTimeout(() => { const c = build(); if (c) { const r = el.getBoundingClientRect(); tipShow(c, r.right + 8, r.top); } }, delay); });
  el.addEventListener("mouseleave", tipHide);
  el.addEventListener("click", tipHide);
}
function tipText(el, title, text, delay) {
  tooltip(el, () => h("div", {}, title ? h("b", {}, title) : null, text), delay);
}

// ── dialogs ────────────────────────────────────────────────────────────
function dialog(build) {
  const dlg = $("#dlg");
  return new Promise((resolve) => {
    const close = (v) => { dlg.close(); dlg.replaceChildren(); resolve(v); };
    dlg.replaceChildren(build(close));
    dlg.className = "";
    dlg.onclose = () => resolve(undefined);
    dlg.oncancel = () => resolve(undefined);
    dlg.showModal();
  });
}
function confirmBox(title, body, okLabel, danger) {
  return dialog((close) => h("div", {},
    h("h2", {}, title), h("div", {}, body),
    h("div", { class: "btns" }, h("button", { onclick: () => close(false) }, "Cancel"),
      h("button", { class: danger ? "danger" : "primary", onclick: () => close(true) }, okLabel || "OK"))));
}
// typed confirmation, e.g. EXECUTE
function typedConfirm(title, body, word, okLabel) {
  return dialog((close) => {
    const inp = h("input", { placeholder: `Type ${word}`, autocomplete: "off", spellcheck: "false" });
    const ok = h("button", { class: "danger", disabled: true, onclick: () => close(inp.value.trim()) }, okLabel || "Run");
    inp.addEventListener("input", () => { ok.disabled = inp.value.trim() !== word; });
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && !ok.disabled) ok.click(); });
    setTimeout(() => inp.focus(), 30);
    return h("div", {}, h("h2", {}, title), h("div", {}, body), h("div", { style: "margin-top:.8rem" }, inp),
      h("div", { class: "btns" }, h("button", { onclick: () => close(null) }, "Cancel"), ok));
  });
}
function debounce(fn, ms) { let t = 0; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
