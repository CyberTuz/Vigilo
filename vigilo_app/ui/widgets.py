"""
Common widgets and the base dialog window.
"""

import os
import tkinter as tk

import customtkinter as ctk

from ..common import APP_ICO
from .theme import ACCENT, ACCENT_H, BORDER, CARD, CARD_HOVER, icon, INPUT, MUTED, PANEL, RED_D, RED_DH, TXT


# ----------------------------------------------------------------------------- common widgets

def F(size=13, weight="normal"):
    return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)


def button(parent, text="", icon_name=None, kind="secondary", command=None, width=None, height=36):
    styles = {
        "primary": (ACCENT, ACCENT_H, "#ffffff", 0),
        "danger": (RED_D, RED_DH, "#ffffff", 0),
        "secondary": (CARD, CARD_HOVER, TXT, 1),
        "ghost": ("transparent", CARD_HOVER, TXT, 0),
    }
    fg, hv, tc, bw = styles[kind]
    img = icon(icon_name, 16, tc if kind != "ghost" else MUTED) if icon_name else None
    if width is None:
        width = height if not text else 0
    b = ctk.CTkButton(parent, text=text, image=img, compound="left", fg_color=fg, hover_color=hv,
                      text_color=tc, border_width=bw, border_color=BORDER, corner_radius=9,
                      height=height, width=width, font=F(13, "bold" if kind in ("primary", "danger") else "normal"),
                      command=command)
    return b


def segmented(parent, values, command, variable=None, height=32):
    return ctk.CTkSegmentedButton(parent, values=values, command=command, variable=variable, height=height,
                                  font=F(12), fg_color=INPUT, selected_color=ACCENT, selected_hover_color=ACCENT_H,
                                  unselected_color=INPUT, unselected_hover_color=CARD_HOVER, text_color=TXT)


def dark_menu(root):
    return tk.Menu(root, tearoff=0, bg=CARD, fg=TXT, activebackground=ACCENT, activeforeground="#ffffff",
                   bd=0, relief="flat", font=("Segoe UI", 10))


class Dialog(ctk.CTkToplevel):
    def __init__(self, parent, title, modal=True, resizable=False):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=PANEL)
        self.resizable(resizable, resizable)  # only once: calling it twice hides the window
        self.transient(parent.winfo_toplevel())
        self.modal = modal
        if os.path.exists(APP_ICO):
            try:
                self.iconbitmap(APP_ICO)
            except Exception:
                pass
        self.after(120, self._finish)

    def _finish(self):
        try:
            self.update_idletasks()
            p = self.master.winfo_toplevel()
            x = p.winfo_rootx() + (p.winfo_width() - self.winfo_width()) // 2
            y = p.winfo_rooty() + (p.winfo_height() - self.winfo_height()) // 3
            self.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
            if self.state() == "withdrawn":
                self.deiconify()
            self.lift()
            self.focus_force()
            if self.modal:
                self.grab_set()
        except Exception:
            pass

    def heading(self, parent, title, subtitle=None, icon_name=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=(0, 14))
        if icon_name:
            box = ctk.CTkLabel(row, text="", image=icon(icon_name, 20, ACCENT), width=40, height=40,
                               fg_color=CARD, corner_radius=10)
            box.pack(side="left", padx=(0, 12))
        col = ctk.CTkFrame(row, fg_color="transparent")
        col.pack(side="left", fill="x")
        ctk.CTkLabel(col, text=title, font=F(18, "bold"), text_color=TXT, anchor="w").pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(col, text=subtitle, font=F(12), text_color=MUTED, anchor="w").pack(anchor="w")


def entry(parent, var, width=200, show=""):
    return ctk.CTkEntry(parent, textvariable=var, width=width, height=36, show=show, fg_color=INPUT,
                        border_color=BORDER, border_width=1, corner_radius=8, text_color=TXT, font=F(13))


def label(parent, text, muted=True, size=12, weight="normal"):
    return ctk.CTkLabel(parent, text=text, text_color=MUTED if muted else TXT, font=F(size, weight), anchor="w",
                        justify="left")


def switch(parent, text, var):
    return ctk.CTkSwitch(parent, text=text, variable=var, onvalue=True, offvalue=False, font=F(13),
                         text_color=TXT, progress_color=ACCENT)
