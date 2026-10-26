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
# Contact: license@mehedimaruf.com
# Can't reach license@mehedimaruf.com?
# The domain probably expired because HE's TOO BROKE TO RENEW IT.
# Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
# and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"""Look and feel: palettes taken from the mehedimaruf.com design tokens, fonts, and soft rounded ttk elements.

tkinter has no rounded corners, so buttons, fields and cards are small anti-aliased images drawn here with plain
Python (a signed-distance rounded rectangle plus a PNG writer) and stretched by ttk as nine-slice image elements.
Each palette's images are built once per run, so switching themes after the first time is instant."""
from __future__ import annotations

import base64
import math
import struct
import zlib
import tkinter as tk
from tkinter import font as tkfont, ttk
from typing import Dict, List, Sequence, Set, Tuple

PALETTES: Dict[str, Dict[str, str]] = {
    # values follow src/styles/tokens.css of the website: warm cream by day, wine-black by night
    "light": {
        "bg": "#fbf5ec", "surface": "#fffdf8", "field": "#fbf5ec", "surface2": "#f5ecdd", "border": "#e8dccb",
        "border_strong": "#d8c6ad", "text": "#2a1117", "muted": "#6e5a52", "gold": "#d8b478", "gold_hover": "#c9a05e",
        "on_gold": "#2a1117", "crimson": "#7a0f24", "crimson_hover": "#5c0a1b", "on_crimson": "#fbf3e8",
        "select": "#f1e2c8", "success": "#1f7a45", "warn": "#8a5f12", "error": "#b3261e", "link": "#8a5a12",
        "b_idle": "#f5ecdd|#4a3a34", "b_run": "#f6ead2|#5c4515", "b_ok": "#e3f1e6|#14532d",
        "b_warn": "#fbefd0|#6b4a0a", "b_bad": "#f8e0e0|#7f1d1d",
    },
    "dark": {
        "bg": "#1a0b10", "surface": "#26121a", "field": "#1a0b10", "surface2": "#321820", "border": "#3a1e27",
        "border_strong": "#4e2a34", "text": "#f2e6d8", "muted": "#a8958c", "gold": "#d8b478", "gold_hover": "#e8c893",
        "on_gold": "#1a0b10", "crimson": "#a81830", "crimson_hover": "#c21f3a", "on_crimson": "#fbf3e8",
        "select": "#3a2630", "success": "#6ccb8c", "warn": "#e3b04b", "error": "#ff8080", "link": "#e0bb7a",
        "b_idle": "#26121a|#e0d3c4", "b_run": "#3a2f1f|#f0d9a8", "b_ok": "#1d3526|#9be0b5",
        "b_warn": "#3f3419|#f1d08a", "b_bad": "#43202a|#ffb4b4",
    },
}

DISPLAY_FONTS = ("Petrona", "Petrona Variable", "Georgia", "Cambria", "Palatino Linotype", "Times New Roman")
BODY_FONTS = ("Source Sans 3", "Source Sans 3 Variable", "Source Sans Pro", "Segoe UI Variable Text", "Segoe UI",
              "SF Pro Text", "Helvetica Neue", "Noto Sans", "Ubuntu", "DejaVu Sans", "Helvetica")
MONO_FONTS = ("Geist Mono", "Geist Mono Variable", "Cascadia Mono", "Cascadia Code", "Consolas", "SF Mono", "Menlo",
              "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono", "Courier New")

RGB = Tuple[float, float, float]


def rgb(hexcolor: str) -> RGB:
    h = hexcolor.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


def mix(a: str, b: str, t: float) -> str:
    ca, cb = rgb(a), rgb(b)
    return "#%02x%02x%02x" % tuple(round(255 * (ca[i] * (1 - t) + cb[i] * t)) for i in range(3))


CENTER = 64          # width of the flat middle of every box image, see rbox_png


def rbox_png(side: int, r: int, fill: str, border: str, outside: str, bw: int = 1) -> bytes:
    """A square rounded box as an opaque PNG. Coverage comes from the distance to the box edge, so the edge is
    anti-aliased. Only one corner is computed; the rest of the image is its mirror image plus flat colour.

    ttk repeats (tiles) the flat middle of an image element across the whole widget, so the middle must be large:
    a 2-pixel middle meant tens of thousands of tiny draws for one card and made every repaint crawl."""
    fc, oc = rgb(fill), rgb(outside)
    bc = rgb(border) if border else fc
    mid = side / 2.0
    n = r + 2     # the corner block carries all of the curvature

    def cover(px: float, py: float, inset: float, rad: float) -> float:
        qx = abs(px - mid) - (mid - inset - rad)
        qy = abs(py - mid) - (mid - inset - rad)
        d = math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - rad
        return min(1.0, max(0.0, 0.5 - d))
    block = []
    for y in range(n):
        row = []
        for x in range(n):
            co = cover(x + 0.5, y + 0.5, 0.0, float(r))
            ci = cover(x + 0.5, y + 0.5, float(bw), float(r - bw)) if border else co
            row.append(bytes(round(255 * (oc[i] * (1 - co) + bc[i] * (co - ci) + fc[i] * ci)) for i in range(3)))
        block.append(row)
    raw = bytearray()
    for y in range(side):
        raw.append(0)
        line = block[min(y, side - 1 - y, n - 1)]
        for x in range(side):
            raw += line[min(x, side - 1 - x, n - 1)]

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", side, side, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 1)) + chunk(b"IEND", b""))


def pick_font(root: tk.Misc, candidates: Sequence[str], fallback: str) -> str:
    have = {f.lower(): f for f in tkfont.families(root)}
    for name in candidates:
        if name.lower() in have:
            return have[name.lower()]
    return fallback


# ------------------------------------------------------------------------------------------------
class Theme:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.style = ttk.Style(root)
        self.scale = max(root.winfo_fpixels("1i") / 96.0, 1.0)
        self.name = "light"
        self.pal = PALETTES["light"]
        self.imgs: List[tk.PhotoImage] = []     # kept alive for the life of the program: ttk only holds their names
        self.created: Set[str] = set()          # image elements already built (one set per palette)

    def px(self, value: float) -> int:
        return max(1, int(round(value * self.scale)))

    def rbox(self, fill: str, border: str, outside: str, r: int, bw: int = 1) -> tk.PhotoImage:
        """A rounded box image, drawn on the spot (about a millisecond each; the images are only made once per theme)."""
        png = rbox_png(2 * r + CENTER, r, fill, border, outside, bw)
        img = tk.PhotoImage(master=self.root, data=base64.b64encode(png).decode("ascii"))
        self.imgs.append(img)
        return img

    # ----------------------------------------------------------------------------------- fonts
    def _fonts(self) -> None:
        root = self.root
        self.family_body = pick_font(root, BODY_FONTS, "TkDefaultFont")
        self.family_display = pick_font(root, DISPLAY_FONTS, self.family_body)
        self.family_mono = pick_font(root, MONO_FONTS, "TkFixedFont")
        size = 11 if self.family_body.lower().startswith("source sans") else 10
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
            tkfont.nametofont(name).configure(family=self.family_body, size=size)
        tkfont.nametofont("TkFixedFont").configure(family=self.family_mono, size=size - 1)
        self.f_ui = tkfont.Font(family=self.family_body, size=size)
        self.f_bold = tkfont.Font(family=self.family_body, size=size, weight="bold")
        self.f_head = tkfont.Font(family=self.family_body, size=size + 1, weight="bold")
        self.f_title = tkfont.Font(family=self.family_display, size=size + 9, weight="bold")
        self.f_mono = tkfont.Font(family=self.family_mono, size=size - 1)

    # ----------------------------------------------------------------------------------- apply
    def apply(self, name: str) -> None:
        self.name = name if name in PALETTES else "light"
        self.pal = PALETTES[self.name]
        self.style.theme_use("clam")
        self._fonts()
        self._base()
        self._elements()

    def _base(self) -> None:
        p, st, root = self.pal, self.style, self.root
        root.configure(bg=p["bg"])
        st.configure(".", background=p["bg"], foreground=p["text"], fieldbackground=p["field"], bordercolor=p["border"],
                     lightcolor=p["border"], darkcolor=p["border"], troughcolor=p["surface2"], focuscolor=p["bg"],
                     selectbackground=p["select"], selectforeground=p["text"], insertcolor=p["text"], font=self.f_ui)
        for ctx, bg in (("", p["bg"]), ("Card.", p["surface"])):
            st.configure(ctx + "TFrame", background=bg)
            st.configure(ctx + "TLabel", background=bg, foreground=p["text"])
            st.configure(ctx + "TCheckbutton", background=bg, foreground=p["text"], indicatorbackground=p["field"],
                         indicatorforeground=p["on_gold"], upperbordercolor=p["border_strong"], lowerbordercolor=p["border_strong"])
            st.map(ctx + "TCheckbutton", background=[("active", bg)], indicatorbackground=[("selected", p["gold"]), ("pressed", p["gold_hover"])],
                   foreground=[("disabled", p["muted"])])
            st.configure(ctx + "TRadiobutton", background=bg, foreground=p["text"], indicatorbackground=p["field"],
                         upperbordercolor=p["border_strong"], lowerbordercolor=p["border_strong"])
            st.map(ctx + "TRadiobutton", background=[("active", bg)], indicatorbackground=[("selected", p["gold"])],
                   foreground=[("disabled", p["muted"])])
            st.configure(ctx + "Muted.TLabel", background=bg, foreground=p["muted"])
            st.configure(ctx + "Head.TLabel", background=bg, foreground=p["text"], font=self.f_head)
            st.configure(ctx + "Bold.TLabel", background=bg, foreground=p["text"], font=self.f_bold)
            st.configure(ctx + "TSeparator", background=p["border"])
        st.configure("Title.TLabel", font=self.f_title)
        row = self.px(30)
        for ctx in ("", "Card."):
            bg = p["surface"]
            st.configure(ctx + "Treeview", background=bg, fieldbackground=bg, foreground=p["text"], rowheight=row,
                         borderwidth=0, relief="flat", lightcolor=bg, darkcolor=bg, bordercolor=bg)
            st.map(ctx + "Treeview", background=[("selected", p["select"])], foreground=[("selected", p["text"])])
            st.configure(ctx + "Treeview.Heading", background=bg, foreground=p["muted"], relief="flat", font=self.f_bold,
                         padding=(self.px(8), self.px(6)), bordercolor=bg, lightcolor=bg, darkcolor=bg)
            st.map(ctx + "Treeview.Heading", background=[("active", p["surface2"])])
        st.configure("Horizontal.TProgressbar", background=p["gold"], troughcolor=p["surface2"], bordercolor=p["surface2"],
                     lightcolor=p["gold"], darkcolor=p["gold"], thickness=self.px(8))
        for ctx, bg in (("", p["bg"]), ("Card.", p["surface"])):
            st.configure(ctx + "Vertical.TScrollbar", background=p["border"], troughcolor=bg, bordercolor=bg, arrowcolor=p["muted"],
                         lightcolor=p["border"], darkcolor=p["border"], gripcount=0, arrowsize=self.px(11))
            st.map(ctx + "Vertical.TScrollbar", background=[("active", p["border_strong"])])
        root.option_add("*TCombobox*Listbox.background", p["surface"])
        root.option_add("*TCombobox*Listbox.foreground", p["text"])
        root.option_add("*TCombobox*Listbox.selectBackground", p["gold"])
        root.option_add("*TCombobox*Listbox.selectForeground", p["on_gold"])
        root.option_add("*TCombobox*Listbox.font", self.f_ui)

    def _elements(self) -> None:
        p, st = self.pal, self.style
        tag = self.name
        r = self.px(12)
        pad_big = (self.px(18), self.px(8))
        pad_small = (self.px(11), self.px(6))

        def button(style: str, fill: str, hover: str, press: str, fg: str, outside: str, border: str = "",
                   dis_fill: str = "", padding: Tuple[int, int] = pad_big, bold: bool = False) -> None:
            el = "%s.bg.%s" % (style, tag)
            if el not in self.created:
                dis = dis_fill or mix(fill, outside, 0.55)
                imgs = [self.rbox(c, border, outside, r) for c in (fill, hover, press, dis)]
                st.element_create(el, "image", imgs[0], ("disabled", imgs[3]), ("pressed", imgs[2]), ("active", imgs[1]),
                                  border=(r, r, r, r), padding=(0, 0, 0, 0), sticky="nswe", width=2 * r, height=2 * r)
                self.created.add(el)
            st.layout(style, [(el, {"sticky": "nswe", "children": [("Button.padding", {"sticky": "nswe", "children": [
                ("Button.label", {"sticky": "nswe"})]})]})])
            st.configure(style, foreground=fg, padding=padding, font=self.f_bold if bold else self.f_ui, anchor="center", width=-1)
            st.map(style, foreground=[("disabled", p["muted"])])

        button("TButton", p["surface2"], p["border"], p["border_strong"], p["text"], p["bg"], padding=pad_small)
        button("Small.TButton", p["surface2"], p["border"], p["border_strong"], p["text"], p["bg"], padding=pad_small)
        button("Accent.TButton", p["gold"], p["gold_hover"], p["gold_hover"], p["on_gold"], p["bg"], bold=True,
               dis_fill=mix(p["gold"], p["bg"], 0.65))
        button("Danger.TButton", p["crimson"], p["crimson_hover"], p["crimson_hover"], p["on_crimson"], p["bg"], bold=True,
               dis_fill=mix(p["crimson"], p["bg"], 0.65))
        button("Ghost.TButton", p["bg"], p["surface2"], p["border"], p["text"], p["bg"], border=p["border_strong"], padding=pad_small,
               dis_fill=p["bg"])
        button("CardBtn.TButton", p["surface2"], p["border"], p["border_strong"], p["text"], p["surface"], padding=pad_small)

        def segment(style: str, outside: str, idle: str) -> None:
            el = "%s.bg.%s" % (style, tag)
            if el not in self.created:
                imgs = [self.rbox(c, "", outside, r) for c in (idle, p["border"], p["gold"])]
                st.element_create(el, "image", imgs[0], ("selected", imgs[2]), ("active", imgs[1]),
                                  border=(r, r, r, r), padding=(0, 0, 0, 0), sticky="nswe", width=2 * r, height=2 * r)
                self.created.add(el)
            st.layout(style, [(el, {"sticky": "nswe", "children": [("Toolbutton.padding", {"sticky": "nswe", "children": [
                ("Toolbutton.label", {"sticky": "nswe"})]})]})])
            st.configure(style, foreground=p["muted"], padding=(self.px(18), self.px(7)), anchor="center", font=self.f_bold)
            st.map(style, foreground=[("selected", p["on_gold"]), ("active", p["text"])])
        segment("Seg.Toolbutton", p["bg"], p["surface2"])
        segment("CardSeg.Toolbutton", p["surface"], p["surface2"])

        rf = self.px(10)

        def field(prefix: str, outside: str) -> None:
            el = "%sField.bg.%s" % (prefix, tag)
            if el not in self.created:
                normal = self.rbox(p["field"], p["border_strong"], outside, rf)
                focus = self.rbox(p["field"], p["gold"], outside, rf)
                disabled = self.rbox(p["surface2"], p["border"], outside, rf)
                st.element_create(el, "image", normal, ("disabled", disabled), ("focus", focus),
                                  border=(rf, rf, rf, rf), padding=(self.px(6), self.px(2), self.px(6), self.px(2)), sticky="nswe",
                                  width=2 * rf, height=2 * rf)
                self.created.add(el)
            common = dict(foreground=p["text"], insertcolor=p["text"], arrowcolor=p["muted"], background=p["field"],
                          fieldbackground=p["field"], bordercolor=p["field"], lightcolor=p["field"], darkcolor=p["field"],
                          padding=(self.px(4), self.px(4)), selectbackground=p["select"], selectforeground=p["text"])
            ent, cmb, spn = prefix + "TEntry", prefix + "TCombobox", prefix + "TSpinbox"
            st.layout(ent, [(el, {"sticky": "nswe", "children": [("Entry.padding", {"sticky": "nswe", "children": [
                ("Entry.textarea", {"sticky": "nswe"})]})]})])
            st.layout(cmb, [(el, {"sticky": "nswe", "children": [
                ("Combobox.downarrow", {"side": "right", "sticky": "ns"}),
                ("Combobox.padding", {"expand": "1", "sticky": "nswe", "children": [("Combobox.textarea", {"sticky": "nswe"})]})]})])
            st.layout(spn, [(el, {"sticky": "nswe", "children": [
                ("null", {"side": "right", "sticky": "", "children": [
                    ("Spinbox.uparrow", {"side": "top", "sticky": "e"}), ("Spinbox.downarrow", {"side": "bottom", "sticky": "e"})]}),
                ("Spinbox.padding", {"sticky": "nswe", "children": [("Spinbox.textarea", {"sticky": "nswe"})]})]})])
            for name in (ent, cmb, spn):
                st.configure(name, **common)
                st.map(name, foreground=[("disabled", p["muted"])], fieldbackground=[("readonly", p["field"])],
                       background=[("readonly", p["field"])])
        field("", p["bg"])
        field("Card.", p["surface"])

        rc = self.px(16)
        el = "Card.bg.%s" % tag
        if el not in self.created:
            card = self.rbox(p["surface"], p["border"], p["bg"], rc)
            st.element_create(el, "image", card, border=(rc, rc, rc, rc), padding=(0, 0, 0, 0), sticky="nswe", width=2 * rc, height=2 * rc)
            self.created.add(el)
        st.layout("Card.TFrame", [(el, {"sticky": "nswe"})])
        st.configure("Card.TFrame", background=p["surface"])
        st.configure("CardPlain.TFrame", background=p["surface"])
