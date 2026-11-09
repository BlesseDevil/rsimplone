// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)
// Licensed under the GNU AGPL v3 or any later version; see <https://www.gnu.org/licenses/>. No warranty.
// Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
// The domain probably expired because HE's TOO BROKE TO RENEW IT.
// Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
// and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"use strict";
// Remotes: list, test, add (guided), edit, delete, plus the Simple/Advanced switch and the rclone config file choice.

const isAdvanced = () => !!(S.settings && S.settings.advanced);
async function setAdvanced(on, after) {
  S.settings.advanced = on; await call("save_settings", { advanced: on }); if (after) after(); else renderAll();
}
function modeSwitch(after) {
  return h("div", { class: "seg", role: "group", "aria-label": "Simple or Advanced" },
    h("button", { "aria-pressed": String(!isAdvanced()), title: "Only the essentials", onclick: () => setAdvanced(false, after) }, "Simple"),
    h("button", { "aria-pressed": String(isAdvanced()), title: "Every rclone setting. Changes what is shown, never what a job does.", onclick: () => setAdvanced(true, after) }, "Advanced"));
}
const guideBtn = (name) => h("button", { class: "ghost sm", title: "Open rclone's guide for this backend in your browser", onclick: () => must("open_url", "https://rclone.org/" + encodeURIComponent(name) + "/") }, icon("open"), "See guide");
const shortHelp = (t) => { const l = firstLine(t); return l.length > 120 ? l.slice(0, 117).trimEnd() + "…" : l; };

// The few settings a beginner needs, per common backend. Everything else is rclone's own guided questions or Advanced mode.
const SIMPLE = {
  drive: [], onedrive: [], dropbox: [],
  s3: ["provider", "access_key_id", "secret_access_key", "region", "endpoint"],
  sftp: ["host", "user", "port", "pass"], webdav: ["url", "vendor", "user", "pass"], b2: ["account", "key"],
  ftp: ["host", "user", "port", "pass"], smb: ["host", "user", "pass"],
};
const TOP = ["drive", "google photos"], GOOGLE = TOP;
const SAME_ACCOUNT = "The Google account behind both remotes must be the same. A login from a different account gives access to that other account's files.";
const NICE = { "google photos": "Google Photos", drive: "Google Drive", onedrive: "Microsoft OneDrive", dropbox: "Dropbox", s3: "Amazon S3 and compatible", sftp: "SFTP (SSH server)", webdav: "WebDAV", b2: "Backblaze B2", ftp: "FTP", smb: "Windows / SMB share" };
const IMPORTED = "@imported-from-file@";
async function copyText(t) {
  try { await navigator.clipboard.writeText(t); toast("Copied.", "ok"); } catch { toast("Could not copy. Select the text and press Ctrl+C.", "bad"); }
}
// Google's downloaded OAuth client file: the secret stays inside the app; only the client id and what the file covers come back
function importRow(onImported, onManual) {
  const box = h("div", { class: "stack", style: "gap:.4rem" });
  const idIn = h("input", { placeholder: "Client id (ends with .apps.googleusercontent.com)", spellcheck: "false", autocomplete: "off" });
  const secIn = h("input", { type: "password", placeholder: "Client secret", autocomplete: "new-password" });
  const manual = h("details", {}, h("summary", { class: "note" }, "Type the client id and secret by hand instead"),
    h("div", { class: "stack", style: "margin-top:.5rem" }, idIn, secIn, h("button", { class: "sm", onclick: () => {
      if (!idIn.value.trim() || !secIn.value) return toast("Enter both the client id and the client secret.", "bad");
      onManual({ client_id: idIn.value.trim(), client_secret: secIn.value }); secIn.value = "";
      box.replaceChildren(h("div", { class: "note" }, icon("check"), " Using the client id and secret you typed."));
    } }, "Use these")));
  const btn = h("button", { onclick: async () => {
    const x = await call("remote_import_credentials");
    if (!x.ok) {      // a file that cannot be used: say why, and let the person type the two values instead
      box.replaceChildren(h("div", { class: "note", style: "color:var(--bad)" }, x.error + " Please enter the client id and client secret by hand below."));
      manual.open = true; return;
    }
    const r = x.data; if (r.cancelled) return;
    onImported(r);
    box.replaceChildren(h("div", { class: "note" }, icon("check"), ` Read the file (${r.kind === "installed" ? "Desktop app" : "Web application"} client${r.project_id ? ", project " + r.project_id : ""}).`),
      h("div", { class: "note" }, "Found: ", r.fields.map((f) => f.replace(/_/g, " ") + (f === "client_secret" ? " (kept hidden)" : "")).join(", "), "."),
      h("div", { class: "note" }, "This fills in: client id and client secret."), r.warning ? h("div", { class: "note", style: "color:var(--warn)" }, r.warning) : null);
  } }, icon("open"), "Import Google credentials file…");
  return h("div", { class: "stack", style: "gap:.4rem" }, h("div", { class: "row" }, btn,
    h("button", { class: "ghost sm", onclick: () => must("open_url", "https://rclone.org/drive/#making-your-own-client-id") }, icon("open"), "rclone guide: make your own key")), box, manual);
}
const firstLine = (t) => String(t || "").split("\n")[0];

async function loadProviders() {
  if (!S.providers) { const p = await must("remote_providers"); if (!p) return null; S.providers = p; }
  return S.providers;
}

// ═══ page ═══════════════════════════════════════════════════════════════════════════════
async function pageRemotes() {
  const page = $("#page");
  if (S.rcloneVersion) await loadProviders();
  const info = (await call("config_info")).data || {};
  const stack = h("div", { class: "stack" });
  stack.append(h("div", { class: "note" }, icon("cloud"), " Using rclone config file: ", h("code", { class: "mono-sel" }, info.active || "(rclone's default)"), " ",
    h("button", { class: "ghost sm", onclick: () => { S.view = "settings"; renderAll(); } }, "Change…"), configButtons()));
  if (!S.rcloneVersion) {
    stack.append(h("div", { class: "warnbox" }, icon("alert"), " rclone was not found. rSimpLone needs it for everything. ",
      h("button", { class: "primary sm", onclick: installRcloneDialog }, "Install rclone…")));
  } else if (!S.remotes.length) {
    stack.append(h("div", { class: "empty card" }, h("h2", {}, "Connect your first cloud or server"),
      h("p", {}, "A remote is a saved connection, like Google Drive or an SFTP server. Add one, then pick it as the destination of a job."),
      h("button", { class: "primary", onclick: () => addRemoteDialog() }, icon("plus"), "Add a remote")));
  }
  for (const r of S.remotes) stack.append(remoteCard(r));
  page.style.gridTemplateRows = "auto minmax(0, 1fr)";
  page.replaceChildren(h("div", { class: "jobhead" }, h("h2", { style: "font-size:1.35rem" }, "Remotes"), h("span", { class: "grow" }),
    h("button", { class: "primary", disabled: !S.rcloneVersion, onclick: () => addRemoteDialog() }, icon("plus"), "Add remote")), h("div", { class: "view" }, stack));
}
function remoteCard(r) {
  const result = h("span", { class: "note" });
  const test = h("button", { class: "sm", onclick: async () => {
    test.disabled = true; result.className = "note"; result.textContent = "Testing…";
    const x = await call("remote_test", r.name); test.disabled = false;
    result.className = "chip " + (x.ok ? "ok" : "bad"); result.textContent = x.ok ? x.data : x.error;
  } }, "Test");
  return h("div", { class: "card" }, h("header", {}, r.crypt ? icon("lock", "lock") : icon("cloud"), h("h2", { style: "flex:0 0 15rem;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap", title: r.name }, r.name), h("span", { class: "chip", style: "flex:0 0 8rem;justify-content:center" }, r.type),
    h("span", { class: "grow" }), result, test,
    r.crypt ? null : h("button", { class: "sm", onclick: () => editRemoteDialog(r) }, "Edit"),
    GOOGLE.includes(r.type) && S.remotes.filter((x) => x.type === r.type).length > 1 ? h("button", { class: "sm", title: "Give other remotes of the same Google account this remote's login", onclick: () => copyLoginDialog(r) }, "Copy login…") : null,
    S.providers && (S.providers.find((p) => p.name === r.type) || { options: [] }).options.some((o) => o.name === "root_folder_id") ? h("button", { class: "sm", title: "Advanced: a second remote with the same login but a different root folder", onclick: () => copyRemoteDialog(r) }, icon("dup"), "Copy…") : null,
    h("button", { class: "ghost icon", title: "Delete this remote", "aria-label": "Delete " + r.name, onclick: () => deleteRemote(r) }, icon("trash"))));
}
async function deleteRemote(r) {
  const users = (await call("remote_uses", r.name)).data || { jobs: [], mounts: [] };
  const inUse = [...users.jobs, ...users.mounts];
  if (inUse.length) return toast(`“${r.name}” is used by ${inUse.join(", ")}. Change or delete those first.`, "bad");
  const ok = await confirmBox("Delete this remote?", h("p", {}, `“${r.name}” will be removed from the rclone config file. Your files in the cloud are not touched. A backup copy of the config file is made first.`), "Delete remote", true);
  if (!ok) return;
  const list = await must("remote_delete", r.name); if (!list) return;
  S.remotes = list; toast("Remote deleted.", "ok"); pageRemotes();
}

// ═══ add / edit ═════════════════════════════════════════════════════════════════════════
function fieldFor(o, value) {
  let ctl;
  if (o.type === "bool") {
    ctl = h("select", {}, h("option", { value: "" }, "(default)"), h("option", { value: "true", selected: value === "true" }, "Yes"), h("option", { value: "false", selected: value === "false" }, "No"));
  } else if (o.examples && o.examples.length && o.examples.length <= 60) {
    ctl = h("select", {}, h("option", { value: "" }, o.default ? `(default: ${o.default})` : "(choose)"), o.examples.map((e) => h("option", { value: e.value, selected: e.value === value }, e.help ? `${e.value}: ${firstLine(e.help)}`.slice(0, 90) : e.value)));
  } else {
    ctl = h("input", { type: o.password ? "password" : "text", value: o.password ? "" : (value || ""), placeholder: o.password ? (value === undefined ? "" : "leave blank to keep the current one") : (o.default ? "default: " + o.default : ""), autocomplete: o.password ? "new-password" : "off", spellcheck: "false" });
  }
  ctl.dataset.opt = o.name;
  return h("label", { class: "f", "data-opt": o.name }, o.name.replace(/_/g, " ") + (o.required ? " *" : ""), ctl, h("span", { class: "note", style: "font-weight:400", title: o.help }, shortHelp(o.help)));
}
function readForm(box) {
  const out = {};
  for (const el of box.querySelectorAll("[data-opt]")) if (el.tagName !== "LABEL" && el.value !== "") out[el.dataset.opt] = el.value;
  return out;
}
function visibleOptions(p, adv) {
  const simple = SIMPLE[p.name];
  return p.options.filter((o) => adv ? true : simple ? simple.includes(o.name) : (o.required && !o.advanced));
}

async function addRemoteDialog(resume) {
  const provs = await loadProviders(); if (!provs) return;
  let created = "", imported = null, typed = null, offKey = () => {};
  await dialog((close) => {
    const body = h("div", { class: "stack" });
    const pickProvider = () => {
      const search = h("input", { placeholder: "Search all backends…", spellcheck: "false" });
      const grid = h("div", { class: "pick-list" });
      const paint = () => {
        const q = search.value.trim().toLowerCase();
        const list = provs.filter((p) => !q || (p.name + " " + p.description).toLowerCase().includes(q));
        const row = (p) => h("button", { onclick: () => form(p) }, icon("cloud"), NICE[p.name] || p.description.split(",")[0].slice(0, 60), h("span", { class: "muted", style: "margin-left:auto" }, p.name));
        const top = list.filter((p) => TOP.includes(p.name)), rest = list.filter((p) => !TOP.includes(p.name));
        grid.replaceChildren(...top.map(row), ...(top.length && rest.length ? [h("div", { class: "note", style: "padding:.4rem .8rem;border-bottom:1px solid var(--border)" }, "All backends")] : []), ...rest.map(row));
        if (!list.length) grid.append(h("div", { class: "empty" }, "No backend matches."));
      };
      search.addEventListener("input", paint); paint();
      body.replaceChildren(h("div", { class: "row" }, h("h2", { class: "grow" }, "Add a remote"), modeSwitch(() => pickProvider())), h("p", { class: "note" }, "Google Drive and Google Photos first, then every backend rclone supports."), search, grid,
        h("div", { class: "btns" }, h("button", { onclick: () => close(false) }, "Cancel")));
      setTimeout(() => search.focus(), 30);
    };
    const form = (p, draft = {}) => {
      const fields = h("div", { class: "stack" });
      const opts = visibleOptions(p, isAdvanced());
      const basic = opts.filter((o) => !o.advanced), adv = opts.filter((o) => o.advanced);
      const name = h("input", { value: draft.__name ?? uniqueRemoteName(p.name), spellcheck: "false" });
      fields.append(field("Name for this remote", name, "Jobs refer to it by this name."), ...basic.map((o) => fieldFor(o, draft[o.name])));
      if (adv.length) fields.append(h("details", { open: adv.some((o) => draft[o.name]) }, h("summary", { class: "note" }, `Advanced options (${adv.length})`), h("div", { class: "stack", style: "margin-top:.6rem" }, adv.map((o) => fieldFor(o, draft[o.name])))));
      if (!isAdvanced() && opts.length < p.options.length) fields.append(h("div", { class: "note" }, `${p.options.length - opts.length} more options are hidden in Simple mode.`));
      if (p.name === "drive" && isAdvanced()) fields.append(h("div", { class: "stack", style: "gap:.4rem" }, h("div", { class: "note" }, "Google is retiring rclone's shared sign-in key during 2026, so your own key is recommended. If you downloaded its JSON file, import it here."),
        importRow((r) => { const cid = fields.querySelector("input[data-opt=client_id]"), sec = fields.querySelector("input[data-opt=client_secret]"); if (cid) cid.value = r.client_id; if (sec) { sec.type = "text"; sec.value = IMPORTED; sec.readOnly = true; } imported = r; }, (v) => { typed = v; if (cid) cid.value = v.client_id; })));
      const same = p.options.some((o) => o.name === "root_folder_id") ? S.remotes.filter((r) => r.type === p.name) : [];
      let reuse = null, rootIn = null;
      if (same.length) {
        reuse = h("select", {}, h("option", { value: "" }, "Sign in with the browser (new login)"), same.map((r) => h("option", { value: r.name }, `Reuse the login from “${r.name}”`)));
        rootIn = h("input", { placeholder: "Folder ID, or leave empty for the top of the drive", spellcheck: "false" });
        const rootField = field("Root folder ID", rootIn, "Copy it from the folder's web address (the part after /folders/).");
        rootField.hidden = true;
        reuse.addEventListener("change", () => { rootField.hidden = !reuse.value; });
        fields.append(field("Login", reuse, "Reusing a login skips the browser sign-in. " + SAME_ACCOUNT), rootField);
      }
      const msg = h("div", { class: "note" });
      const go = h("button", { class: "primary" }, "Continue");
      const keep = () => ({ ...readForm(fields), __name: name.value });
      go.addEventListener("click", async () => {
        go.disabled = true; msg.className = "note"; msg.textContent = "Working…";
        const nm = name.value.trim();
        if (reuse && reuse.value) {
          const x = await call("remote_copy", reuse.value, nm, rootIn.value.trim() ? { root_folder_id: rootIn.value } : {}, true);
          if (!x.ok) { msg.style.color = "var(--bad)"; msg.textContent = x.error; go.disabled = false; return; }
          S.remotes = x.data; toast(`Created “${nm}” with the same login as “${reuse.value}”.`, "ok"); close(true); return;
        }
        const r = await call("remote_start", nm, p.name, { ...readForm(fields), ...(typed || {}) });
        if (!r.ok) { msg.style.color = "var(--bad)"; msg.textContent = r.error; go.disabled = false; return; }
        created = nm; S.remotes = r.data.remotes; walk(nm, r.data.step);
      });
      body.replaceChildren(h("div", { class: "row" }, h("h2", { class: "grow" }, `Add ${NICE[p.name] || p.description.split(",")[0]}`), modeSwitch(() => form(p, keep())), guideBtn(p.name)), fields, msg,
        h("div", { class: "btns" }, h("button", { onclick: () => pickProvider() }, "Back"), h("button", { onclick: () => close(false) }, "Cancel"), go));
    };
    // rclone asks follow-up questions (for example the browser sign-in); answer them one by one, in plain words
    const friendly = (q) => {
      let title = "One more question", text = String(q.help || ""), yes = "Yes", no = "No", suggest = "";
      if (q.name === "config_shared_client_id") {
        title = "Use rclone's shared Google sign-in key?";
        text = "This shared key is being retired by Google during 2026, and it is slow and easily rate-limited. blessedevil suggests No: make your own free key (the next screen helps).";
        yes = "Yes, use the shared key"; no = "No, use my own key (suggested)"; suggest = "no";
      } else if (q.name === "config_is_local") {
        title = "Sign in with a web browser on this computer?";
        text = "Choose Yes to sign in in your browser. You can copy the link to open it in a different browser or profile. Choose No if you will sign in on another computer.";
        yes = "Yes (recommended)"; no = "No, another computer"; suggest = "yes";
      } else if (q.type === "bool") {
        text = text.split("\n").filter((l) => !/^\s*\*?\s*(say|if not sure)/i.test(l)).join("\n").trim() || text;
      }
      return { title, text, yes, no, suggest };
    };
    const working = () => {
      const linkBox = h("div", { class: "stack", style: "gap:.3rem" });
      body.replaceChildren(h("h2", {}, "Working…"), h("p", { class: "note" }, "If your browser opened, finish signing in there. This window continues by itself."), linkBox,
        h("div", { class: "btns" }, h("button", { onclick: () => call("remote_cancel") }, "Cancel")));
      const t = setInterval(async () => {
        const r = await call("remote_auth_link");
        if (r.ok && r.data && linkBox.dataset.u !== r.data) {
          linkBox.dataset.u = r.data;
          linkBox.replaceChildren(h("div", { class: "note" }, "Use a different browser or profile? Copy this link and open it where you are already signed in:"),
            h("div", { class: "row" }, h("code", { class: "mono-sel grow", style: "overflow-wrap:anywhere" }, r.data), h("button", { class: "sm", onclick: () => copyText(r.data) }, icon("copy"), "Copy link")));
        }
      }, 800);
      return () => clearInterval(t);
    };
    const walk = async (nm, step) => {
      offKey();
      if (step.done) { toast(`Remote “${nm}” is ready.`, "ok"); close(true); return; }
      const q = step.question;
      if (!q) return finish(nm, "rclone needs something this app cannot show yet.");
      const answer = async (value) => {
        offKey();
        const stop = working();
        const r = await call("remote_continue", nm, step.state, String(value));
        stop();
        if (!r.ok) return finish(nm, r.error);
        S.remotes = r.data.remotes; walk(nm, r.data.step);
      };
      const f = friendly(q);
      const extras = [];
      if (q.name === "client_id" || q.name === "client_secret") {
        extras.push(importRow((r) => { imported = r; walk(nm, step); }, (v) => { typed = v; answer(q.name === "client_secret" ? v.client_secret : v.client_id); }));
        if (typed && q.name === "client_secret") extras.push(h("button", { class: "primary", onclick: () => answer(typed.client_secret) }, "Use the client secret you typed"));
        if (imported && q.name === "client_id") extras.push(h("button", { class: "primary", onclick: () => answer(imported.client_id) }, "Use the client id from the file"));
        if (imported && q.name === "client_secret") extras.push(h("button", { class: "primary", onclick: () => answer(IMPORTED) }, "Use the client secret from the file"));
      }
      const cmd = /rclone authorize[^\n]*/.exec(q.help || "");
      if (cmd) extras.push(h("div", { class: "row" }, h("code", { class: "mono-sel grow", style: "overflow-wrap:anywhere" }, cmd[0]), h("button", { class: "sm", onclick: () => copyText(cmd[0]) }, icon("copy"), "Copy command")));
      let input;
      if (q.type === "bool") {
        const yesBtn = h("button", { class: f.suggest === "yes" ? "primary" : "", onclick: () => answer("true") }, f.yes);
        const noBtn = h("button", { class: f.suggest === "no" ? "primary" : "", onclick: () => answer("false") }, f.no);
        input = h("div", { class: "btns", style: "justify-content:flex-start" }, ...(f.suggest === "no" ? [noBtn, yesBtn] : [yesBtn, noBtn]));
        setTimeout(() => (f.suggest === "no" ? noBtn : yesBtn).focus(), 30);
        const onKey = (e) => { if (e.target.tagName === "INPUT" || e.ctrlKey || e.metaKey) return; const k = e.key.toLowerCase(); if (k === "y") answer("true"); else if (k === "n") answer("false"); };
        document.addEventListener("keydown", onKey); offKey = () => document.removeEventListener("keydown", onKey);
      } else if (q.examples.length) input = h("div", { class: "pick-list" }, q.examples.map((e) => h("button", { onclick: () => answer(e.value) }, e.help ? firstLine(e.help) : e.value)));
      else { const el = h("input", { value: q.default ?? "", type: q.password ? "password" : "text", spellcheck: "false" }); input = h("div", { class: "row" }, h("div", { class: "grow" }, el), h("button", { class: "primary", onclick: () => answer(el.value) }, "Continue")); }
      body.replaceChildren(h("h2", {}, f.title), h("p", { style: "white-space:pre-line" }, f.text), ...extras, input,
        h("div", { class: "btns" }, h("button", { onclick: () => finish(nm, "") }, "Cancel")));
    };
    const finish = async (nm, why) => {      // a half-made remote is removed again so nothing broken is left behind
      offKey(); await call("remote_cancel"); const l = await call("remote_delete", nm); if (l.ok) S.remotes = l.data;
      created = ""; if (why) toast(why, "bad"); close(false);
    };
    if (resume) { created = resume.name; walk(resume.name, resume.step); } else pickProvider();
    return body;
  });
  if (S.view === "remotes") pageRemotes(); else renderJobBody?.();
}
function uniqueRemoteName(base) {
  const names = new Set(S.remotes.map((r) => r.name.toLowerCase())); let n = base, i = 2;
  while (names.has(n.toLowerCase())) n = base + i++;
  return n;
}
const SIMPLE_EDIT = { drive: ["root_folder_id", "team_drive"], "google photos": [] };       // what is worth changing later, in Simple mode
async function editRemoteDialog(r) {
  const provs = await loadProviders(); if (!provs) return;
  const p = provs.find((x) => x.name === r.type); if (!p) return toast("This remote type can't be edited here.", "bad");
  const cur = await must("remote_describe", r.name); if (!cur) return;
  await dialog((close) => {
    const body = h("div", { class: "stack" });
    const render = (draft = {}) => {
      const fields = h("div", { class: "stack" });
      const adv = isAdvanced();
      const nameIn = h("input", { value: draft.__name ?? r.name, spellcheck: "false" });
      const simple = SIMPLE_EDIT[p.name] ?? SIMPLE[p.name] ?? null;
      const opts = adv ? p.options : p.options.filter((o) => (simple ? simple.includes(o.name) : o.required && !o.advanced));
      const val = (o) => (o.password ? "" : (draft[o.name] ?? cur.values[o.name]));
      fields.append(field("Name", nameIn, "Renaming also updates the jobs and mounts that use this remote."));
      for (const o of opts.filter((x) => !adv || !x.advanced)) fields.append(fieldFor(o, val(o)));
      const more = adv ? opts.filter((x) => x.advanced) : [];
      if (more.length) fields.append(h("details", {}, h("summary", { class: "note" }, `Advanced options (${more.length})`), h("div", { class: "stack", style: "margin-top:.6rem" }, more.map((o) => fieldFor(o, val(o))))));
      if (!adv && !opts.length) fields.append(h("div", { class: "note" }, "There is nothing else to change in Simple mode. Switch to Advanced for every setting."));
      const msg = h("div", { class: "note" }, "Passwords are never shown. Leave a password blank to keep it.");
      const save = h("button", { class: "primary" }, "Save");
      save.addEventListener("click", async () => {
        save.disabled = true; msg.style.color = "";
        let nm = r.name;
        const want = nameIn.value.trim();
        if (want && want !== r.name) {
          const x = await call("remote_rename", r.name, want);
          if (!x.ok) { msg.style.color = "var(--bad)"; msg.textContent = x.error; save.disabled = false; return; }
          S.remotes = x.data.remotes; S.jobs = x.data.jobs; nm = want; r.name = want;
        }
        const changed = {};
        for (const [k, v] of Object.entries(readForm(fields))) if (v !== cur.values[k] && k !== "") changed[k] = v;
        if (Object.keys(changed).length) {
          const x = await call("remote_update", nm, changed);
          if (!x.ok) { msg.style.color = "var(--bad)"; msg.textContent = x.error; save.disabled = false; return; }
          S.remotes = x.data.remotes;
        }
        toast(`Saved “${nm}”.`, "ok"); close(true);
      });
      body.replaceChildren(h("div", { class: "row" }, h("h2", { class: "grow" }, `Edit “${r.name}”`), modeSwitch(() => render({ ...readForm(fields), __name: nameIn.value })), guideBtn(p.name)), fields, msg,
        h("div", { class: "btns" }, h("button", { onclick: () => close(false) }, "Cancel"), save));
    };
    render();
    return body;
  });
  pageRemotes();
}

async function copyLoginDialog(r) {
  const names = (await must("remote_login_targets", r.name)) || [];
  if (!names.length) return toast("There is no other remote of this type.", "bad");
  const boxes = names.map((n) => [n, h("input", { type: "checkbox" })]);
  const msg = h("div", { class: "note" });
  const go = h("button", { class: "danger" }, "Copy login");
  const ok = await dialog((close) => {
    go.addEventListener("click", async () => {
      const chosen = boxes.filter(([, b]) => b.checked).map(([n]) => n);
      if (!chosen.length) { msg.style.color = "var(--bad)"; msg.textContent = "Tick at least one remote."; return; }
      go.disabled = true; msg.style.color = ""; msg.textContent = "Working…";
      const x = await call("remote_copy_login", r.name, chosen);
      if (!x.ok) { msg.style.color = "var(--bad)"; msg.textContent = x.error; go.disabled = false; return; }
      toast(`Copied the login of “${r.name}” to ${x.data.join(", ")}. Use Test to check them.`, "ok"); close(true);
    });
    return h("div", { class: "stack" }, h("h2", {}, `Copy the login of “${r.name}”`),
      h("div", { class: "warnbox" }, icon("alert"), " ", SAME_ACCOUNT),
      h("p", { class: "note" }, "Use this when other remotes' logins have expired but this one still works. Their old login is replaced. A backup of the config file is made first."),
      h("div", { class: "pick-list" }, boxes.map(([n, b]) => h("label", { class: "chk pickrow" }, b, h("span", {}, h("b", {}, n))))), msg,
      h("div", { class: "btns" }, h("button", { onclick: () => close(false) }, "Cancel"), go));
  });
  if (ok) pageRemotes();
}

async function copyRemoteDialog(r) {
  const ok = await dialog((close) => {
    const name = h("input", { value: uniqueRemoteName(r.name + "-copy"), spellcheck: "false" });
    const folder = h("input", { placeholder: "Folder ID, or leave empty for the top of the drive", spellcheck: "false" });
    const team = h("input", { placeholder: "Optional shared drive ID", spellcheck: "false" });
    const tok = h("input", { type: "checkbox", checked: true });
    const msg = h("div", { class: "note" });
    const go = h("button", { class: "primary" }, "Make the copy");
    go.addEventListener("click", async () => {
      go.disabled = true; msg.style.color = ""; msg.textContent = "Working…";
      const x = await call("remote_copy", r.name, name.value, { root_folder_id: folder.value, ...(team.value.trim() ? { team_drive: team.value } : {}) }, tok.checked);
      if (!x.ok) { msg.style.color = "var(--bad)"; msg.textContent = x.error; go.disabled = false; return; }
      S.remotes = x.data; const nn = name.value.trim(); close(true);
      if (tok.checked) return toast(`Created “${nn}”. It uses the same login as “${r.name}”.`, "ok");
      const st = await call("remote_update", nn, {});      // no login was copied: walk through rclone's own sign-in for the copy
      if (st.ok && !st.data.step.done) addRemoteDialog({ name: nn, step: st.data.step }); else toast(`Created “${nn}” without a login. Sign in to it before use.`, "bad");
    });
    return h("div", { class: "stack" }, h("div", { class: "row" }, h("h2", { class: "grow" }, `Copy “${r.name}”`), guideBtn(r.type)),
      h("p", { class: "note" }, "Makes a second remote that signs in the same way, but starts in a different folder. In Google Drive, open the folder in your browser and copy the ID from the address (the part after /folders/). Both remotes share one login."),
      field("Name of the copy", name), field("Root folder ID", folder), field("Shared drive ID (optional)", team),
      h("label", { class: "chk" }, tok, h("span", {}, "Also copy the login (sign-in token)", h("small", {}, "No new sign-in needed. Untick to sign in again, for example with another account."))),
      h("div", { class: "warnbox" }, icon("alert"), " ", SAME_ACCOUNT, " Untick the login above to use a different account."), msg,
      h("div", { class: "btns" }, h("button", { onclick: () => close(false) }, "Cancel"), go));
  });
  if (ok) pageRemotes();
}

function configButtons() {
  return h("span", { class: "row", style: "display:inline-flex;gap:.4rem;margin-left:.4rem" },
    h("button", { class: "sm", title: "Opens the file in a text editor. A backup copy is made first.", onclick: async () => { const p = await must("open_config_file"); if (p) toast("Opened in your text editor. Save it, then press Reload.", "ok"); } }, icon("open"), "Open config file"),
    h("button", { class: "sm", title: "Read the file again after you edited it", onclick: async () => { const r = await must("reload_remotes"); if (r) { S.remotes = r; toast("Reloaded the remotes.", "ok"); renderAll(); } } }, "Reload"));
}

// ═══ Settings card: which rclone config file to use ═════════════════════════════════════
async function configCard() {
  const info = (await call("config_info")).data || { mode: "default", custom: "", own: "", active: "" };
  const custom = h("input", { value: info.custom || "", placeholder: "Full path, e.g. D:\\Backups\\rclone.conf", spellcheck: "false" });
  const copy = h("input", { type: "checkbox", checked: true });
  const apply = async (mode) => {
    const r = await must("set_config", mode, custom.value, copy.checked); if (!r) return;
    S.remotes = r.remotes; S.settings.config_mode = mode; toast("Now using " + (r.info.active || "rclone's default file") + ".", "ok"); pageSettings();
  };
  const choice = (mode, title, text) => h("label", { class: "chk" }, h("input", { type: "radio", name: "cfgmode", checked: info.mode === mode, onchange: () => { if (mode !== "custom") apply(mode); } }), h("span", {}, h("b", {}, title), h("small", {}, text)));
  return h("div", { class: "card" }, h("header", {}, h("h2", {}, "rclone config file")),
    h("div", { class: "stack" },
      choice("default", "rclone's default file (recommended)", "The same remotes the rclone command line uses."),
      choice("own", "A separate file just for rSimpLone", `Kept in the rSimpLone data folder. Your other rclone setup is never touched. ${info.own}`),
      h("label", { class: "chk", style: "padding-left:1.6rem" }, copy, h("span", {}, "When switching to the separate file for the first time, start from a copy of the current remotes")),
      choice("custom", "A file I choose", "Any rclone.conf, for example on another drive."),
      h("div", { class: "row" }, h("div", { class: "grow" }, custom), h("button", { onclick: () => apply("custom") }, "Use this file")),
      h("div", { class: "note" }, "In use now: ", h("code", { class: "mono-sel" }, info.active || "(unknown)"), ". Every job, mount and check uses this file. A backup copy is made before the first change in each session."), h("div", { class: "row" }, configButtons())));
}

// ═══ guided rclone install ═══════════════════════════════════════════════════════════
// The bar under the title when rclone is missing, and the dialog behind its button. The page can only say yes:
// the command is fixed in Python (rsg/installer.py) and shown here before anything runs.
function renderRcloneBanner() {
  const b = $("#rcbanner"); if (!b) return;
  b.replaceChildren();
  if (S.rcloneVersion) {
    const u = S.update;
    if (u && u.newer && !S.updateHidden) b.append(h("div", { class: "warnbox rcbar ok" }, icon("alert"),
      h("span", {}, h("b", {}, `rSimpLone ${u.latest} is available. `), `You have ${u.current}.`),
      h("button", { class: "primary sm", onclick: () => must("open_url", u.url) }, "See what's new"),
      h("button", { class: "sm", onclick: () => { S.updateHidden = true; renderRcloneBanner(); } }, "Later")));
    return;
  }
  b.append(h("div", { class: "warnbox rcbar" }, icon("alert"),
    h("span", {}, h("b", {}, "rclone is not installed. "), "rSimpLone needs it for every job. We can help you install it."),
    h("button", { class: "primary sm", onclick: installRcloneDialog }, "Install rclone…")));
}
async function redetectRclone() {
  await must("reload_remotes");
  const s = await must("app_state");
  if (s) Object.assign(S, { rcloneVersion: s.rclone_version, remotes: s.remotes });
  const c = await call("flag_catalogue"); if (c.ok) S.catalogue = c.data;
  renderAll();
  return !!S.rcloneVersion;
}
async function installRcloneDialog() {
  const p = (await call("rclone_install_plan")).data; if (!p) return;
  const guide = h("a", { href: "#", onclick: (e) => { e.preventDefault(); must("open_url", p.page); } }, "rclone's install guide");
  await dialog((close) => {
    const out = h("pre", { class: "mono-sel", style: "max-height:9rem;overflow:auto;white-space:pre-wrap;font-size:.8rem" });
    const msg = h("div", { class: "note", hidden: true });
    const go = h("button", { class: "primary" }, "Install rclone");
    const check = h("button", { hidden: p.can_run, onclick: async () => { toast((await redetectRclone()) ? "rclone found." : "rclone is still not found.", S.rcloneVersion ? "ok" : "bad"); if (S.rcloneVersion) close(true); } }, "I installed it, check again");
    go.hidden = !p.can_run;
    go.addEventListener("click", async () => {
      go.disabled = true; msg.hidden = false; msg.textContent = "Installing… this can take a minute.";
      if (!(await call("rclone_install_start")).ok) { msg.textContent = "Could not start the install."; go.disabled = false; return; }
      for (;;) {
        await wait(1000);
        const r = (await call("rclone_install_status")).data; if (!r) break;
        out.textContent = r.tail.join("\n");
        if (r.state === "done") { await redetectRclone(); toast("Installed " + r.found, "ok"); close(true); return; }
        if (r.state === "failed") { msg.replaceChildren("The install did not finish. You can try again, or follow ", guide, "."); go.disabled = false; return; }
      }
    });
    const how = p.text
      ? (p.can_run ? h("p", {}, "rSimpLone will run this with ", h("b", {}, p.label), ". Nothing else on your computer is changed:")
                   : h("p", {}, "Open a terminal, paste this, and run it (it asks for your password). Then come back and press the check button:"))
      : h("p", {}, "This computer has no installer rSimpLone can use. Please follow ", guide, ", then press the check button.");
    return h("div", {}, h("h2", {}, "Install rclone"),
      h("p", {}, "rclone is the free program that does the actual copying. rSimpLone does not include it."), how,
      p.text ? h("div", { class: "row" }, h("code", { class: "mono-sel grow" }, p.text), p.can_run ? null : h("button", { class: "sm", onclick: () => copyText(p.text) }, icon("copy"), "Copy")) : null,
      out, msg,
      h("div", { class: "btns" }, h("button", { onclick: () => close(false) }, "Close"), p.text && !p.can_run ? h("button", { class: "ghost", onclick: () => must("open_url", p.page) }, "Install guide") : null, check, go));
  });
}

// ═══ update check (opt-in; it only looks, nothing is downloaded or installed) ═══════════
async function runUpdateCheck(force) {
  const r = await call("update_check", !!force);
  if (!r.ok) return force ? toast(r.error, "bad") : undefined;
  S.update = r.data; S.updateHidden = false; renderRcloneBanner();
  if (force) toast(r.data.failed ? "Could not reach GitHub." : r.data.newer ? `rSimpLone ${r.data.latest} is available.` : "You have the latest version.", r.data.failed ? "bad" : "ok");
}
async function askUpdateCheck() {
  if (S.settings.update_check !== undefined && S.settings.update_check !== null) return;
  const yes = await dialog((close) => h("div", {}, h("h2", {}, "Check for new versions?"),
    h("p", {}, "rSimpLone can ask GitHub once a day whether a newer version has been published, and tell you if so. It never downloads or installs anything."),
    h("p", { class: "note" }, "GitHub sees your internet address, like any website you visit. Nothing else is sent. You can change this any time in Settings."),
    h("div", { class: "btns" }, h("button", { onclick: () => close(false) }, "No thanks"), h("button", { class: "primary", onclick: () => close(true) }, "Yes, check daily"))));
  S.settings.update_check = yes === true;
  await must("save_settings", { update_check: yes === true });
  if (yes === true) runUpdateCheck(false);
}
