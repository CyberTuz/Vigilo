"""
Main window: camera list, live video grid, toolbar and the application object.
"""

import os
import sys
import math
import time
import shutil
import threading
import datetime
import subprocess
import tkinter as tk
from tkinter import messagebox

import numpy as np
import cv2
import psutil
from PIL import Image
from PIL import ImageTk
from PIL import ImageDraw
import customtkinter as ctk

from i18n import tr
from i18n import set_language
from i18n import LANGUAGES
from ..common import (
    APP_ICO, APP_NAME, APP_VERSION, applog, cam_address, EVENTS_DIR, fmt_gb, fmt_size, KIND_CLOUD,
    KIND_CUSTOM, KIND_NATIVE, KIND_SHORT, load_config, PTZ_DIRS, safe_name, save_config, SNAP_DIR,
    STREAM_KINDS,
)
from .theme import (
    ACCENT, ACCENT_H, BG, BORDER, CARD, CARD_HOVER, CARD_SEL, draw_app_icon, ensure_app_icon, fit_image,
    GREEN, hex2rgb, icon, icon_pil, INPUT, MUTED, ORANGE, PANEL, pil_font, RED, RED_D, TILE_BG, TXT,
)
from ..cloud import CLOUD_APP
from ..devices import PtzController
from ..audio import AudioOut, RtspAudioTap
from ..viewers import make_viewer
from ..recorder import Recorder
from ..archive import cleanup_recordings, list_segments, read_events
from ..system import (
    install_crash_log, KeepAwake, log_exception, release_instance, restart_command, ShowSignal, single_instance,
    TrayIcon,
)
from ..supervisor import EXIT_RESTART
from .. import hwaccel
from .widgets import button, dark_menu, F, segmented
from .dialogs import CameraDialog, LanguageDialog, ScanDialog, SettingsDialog
from .playback import PlaybackWindow


# ----------------------------------------------------------------------------- camera card (sidebar)

class CameraCard(ctk.CTkFrame):
    def __init__(self, master, app, cam):
        super().__init__(master, fg_color=CARD, corner_radius=10, border_width=1, border_color=CARD)
        self.app = app
        self.cid = cam["id"]
        self.grid_columnconfigure(1, weight=1)
        self.dot = ctk.CTkLabel(self, text="●", width=16, text_color=MUTED, font=F(15))
        self.dot.grid(row=0, column=0, rowspan=2, padx=(12, 6))
        self.name = ctk.CTkLabel(self, text="", anchor="w", font=F(13, "bold"), text_color=TXT)
        self.name.grid(row=0, column=1, sticky="ew", pady=(9, 0))
        self.sub = ctk.CTkLabel(self, text="", anchor="w", font=F(11), text_color=MUTED)
        self.sub.grid(row=1, column=1, sticky="ew", pady=(0, 9))
        self.badge = ctk.CTkLabel(self, text="", height=20, corner_radius=6, font=F(10, "bold"),
                                  fg_color="transparent", text_color="#ffffff")
        self.badge.grid(row=0, column=2, rowspan=2, padx=4)
        self.more = ctk.CTkButton(self, text="", image=icon("more", 16, MUTED), width=28, height=28,
                                  fg_color="transparent", hover_color=CARD_HOVER, corner_radius=6,
                                  command=self._menu_btn)
        self.more.grid(row=0, column=3, rowspan=2, padx=(0, 8))
        for w in (self, self.dot, self.name, self.sub, self.badge):
            w.bind("<Button-1>", lambda e: app.select(self.cid))
            w.bind("<Double-1>", lambda e: app.toggle_single(self.cid))
            w.bind("<Button-3>", lambda e: app.show_menu(e, self.cid))
        self.refresh()

    def _menu_btn(self):
        class E:
            pass
        e = E()
        e.x_root = self.more.winfo_rootx()
        e.y_root = self.more.winfo_rooty() + self.more.winfo_height()
        self.app.show_menu(e, self.cid)

    def refresh(self):
        cam = self.app.cam(self.cid)
        if not cam:
            return
        v = self.app.viewers.get(self.cid)
        now = time.time()
        live = v is not None and now - v.last_frame_t < 6
        name = cam["name"] if len(cam["name"]) <= 19 else cam["name"][:18] + "…"
        self.name.configure(text=name)
        extra = " · PTZ" if cam.get("ptz") else ""
        if v is not None and v.decoder == "gpu":
            extra += " · GPU"
        addr = cam.get("ip", "") if cam.get("kind") not in (KIND_CUSTOM, KIND_CLOUD) else cam_address(cam)
        self.sub.configure(text=f"{addr} · {tr(KIND_SHORT.get(cam.get('kind'), ''))}{extra}")
        moving = v is not None and now - v.last_motion < 4
        self.dot.configure(text_color=(ORANGE if moving else GREEN) if live else RED)
        state = self.app.rec_state(self.cid)
        if state == 2:
            self.badge.configure(text="  REC  ", fg_color=RED_D)
        elif state == 3:
            self.badge.configure(text="  " + tr("ARMED") + "  ", fg_color="#1d4ed8")
        elif state == 1:
            self.badge.configure(text="  " + tr("WAITING") + "  ", fg_color="#b45309")
        else:
            self.badge.configure(text="", fg_color="transparent")
        sel = self.app.selected == self.cid
        self.configure(fg_color=CARD_SEL if sel else CARD, border_color=ACCENT if sel else CARD)


# ----------------------------------------------------------------------------- main window

def best_grid(n, w, h, aspect=16 / 9):
    """Columns/rows that make the video tiles as large as possible."""
    best = None
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        tw = min(w / cols, (h / rows) * aspect)
        score = (round(tw), -(rows * cols - n))
        if best is None or score > best[0]:
            best = (score, cols, rows)
    return best[1], best[2]


class App:
    def __init__(self, root, recovered=False):
        self.root = root
        self.restart = False
        self.recovered = recovered      # started again by the watchdog after a crash
        self.cfg = load_config()
        self.settings = self.cfg["settings"]
        self.cameras = self.cfg["cameras"]
        for c in self.cameras:
            c.setdefault("id", self._new_id())
        root.title(APP_NAME)
        root.configure(fg_color=BG)
        if ensure_app_icon():
            try:
                root.iconbitmap(APP_ICO)
            except Exception:
                pass
        if self.settings.get("lang") in LANGUAGES:
            set_language(self.settings["lang"])
            self._init_ui()
        else:
            root.geometry("720x460")
            root.after(200, lambda: LanguageDialog(root, self._language_chosen))

    def _language_chosen(self, lang):
        self.settings["lang"] = lang
        set_language(lang)
        save_config(self.cfg)
        self._init_ui()

    def _init_ui(self):
        root = self.root
        CLOUD_APP.clear()
        CLOUD_APP.update(self.settings.get("cloud_app") or {})
        self.audio = AudioOut()
        applog(f"start {APP_NAME} {APP_VERSION} lang={self.settings.get('lang')} cameras={len(self.cameras)} "
               f"audio={'yes' if self.audio.available else 'no'} frozen={getattr(sys, 'frozen', False)}"
               + (" (started again by the watchdog after an error)" if self.recovered else ""))
        self.keep_awake = KeepAwake()
        try:
            self.show_signal = ShowSignal()      # a second start of Vigilo shows this window
        except Exception:
            self.show_signal = None
        self.tray_hint_shown = False
        self.tray = TrayIcon(draw_app_icon(128), APP_NAME,
                             on_show=lambda: self.root.after(0, self.show_window),
                             on_quit=lambda: self.root.after(0, self.quit_from_tray))
        self.tray.start()
        # check the GPU now (about 0.2 s) so the cameras' first decoders already use it
        threading.Thread(target=hwaccel.probe, name="gpu-probe", daemon=True).start()
        self.listen_cid = None      # camera whose live audio is playing
        self.audio_tap = None       # RtspAudioTap of that camera (RTSP only)
        self.viewers = {}
        self.recorders = {}
        self.ptz = {}
        self.tiles = {}
        self.cards = {}
        self.single = None      # id of the camera shown alone (enlarged)
        self.selected = self.cameras[0]["id"] if self.cameras else None
        self.fullscreen = False
        self.playback_win = None
        self.stats = {}
        self.rec_total = None
        self.ev_lock = threading.Lock()
        self._grid_key = None
        self._relayout_job = None
        self._key_stop_job = None
        self._key_dir = None

        self.px = max(1.0, root.winfo_fpixels("1i") / 96.0)
        self.f_name = pil_font("seguisb.ttf", 15 * self.px)
        self.f_pill = pil_font("seguisb.ttf", 11 * self.px)
        self.f_status = pil_font("segoeui.ttf", 13 * self.px)
        self.hover_imgs = {n: ImageTk.PhotoImage(self._round_icon(n)) for n in
                           ("full", "back", "camera", "record", "stop", "pin", "volume", "mute")}
        self.pad_d = int(112 * self.px)
        self.pad_img = ImageTk.PhotoImage(self._pad_image(self.pad_d))
        self._grad_cache = {}

        root.geometry("1440x860")
        root.minsize(1000, 620)

        self._build_ui()
        for cam in self.cameras:
            self._start_camera(cam)
        self._rebuild_cards()
        self._relayout()
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self.root.bind("<F11>", lambda e: self.toggle_fullscreen())
        self.root.bind("<Escape>", lambda e: self._escape())
        for key, d in (("Up", "DirectionUp"), ("Down", "DirectionDown"), ("Left", "DirectionLeft"),
                       ("Right", "DirectionRight")):
            self.root.bind(f"<KeyPress-{key}>", lambda e, d=d: self._key_ptz(d, True))
            self.root.bind(f"<KeyRelease-{key}>", lambda e, d=d: self._key_ptz(d, False))
        threading.Thread(target=self._stats_loop, daemon=True).start()
        self.root.after(100, self._tick)
        self.root.after(1000, self._slow_tick)
        self.root.after(5000, self._cleanup_loop)
        self.root.after(20000, self._prune_loop)
        if not self.cameras:
            self.root.after(700, self._first_run)
        if self.recovered:
            self.root.after(1500, lambda: self.toast(tr("Vigilo was restarted after an error"), 6000))

    @staticmethod
    def _new_id():
        return f"c{int(time.time() * 1000)}{os.getpid() % 1000}"

    def _round_icon(self, name):
        d = int(36 * self.px)
        img = Image.new("RGBA", (d, d), (0, 0, 0, 0))
        ImageDraw.Draw(img).ellipse((0, 0, d - 1, d - 1), fill=(14, 16, 20, 190))
        color = RED if name == "record" else "#ffffff"
        ic = icon_pil(name, int(16 * self.px), color)
        if ic:
            img.alpha_composite(ic, ((d - ic.width) // 2, (d - ic.height) // 2))
        return img

    def _pad_image(self, d):
        """Direction pad for motorized cameras."""
        s = 3
        big = Image.new("RGBA", (d * s, d * s), (0, 0, 0, 0))
        dr = ImageDraw.Draw(big)
        dr.ellipse((0, 0, d * s - 1, d * s - 1), fill=(14, 16, 20, 175), outline=(255, 255, 255, 60), width=2 * s)
        r = d * s / 2
        dr.ellipse((r - d * s * 0.16, r - d * s * 0.16, r + d * s * 0.16, r + d * s * 0.16), fill=(255, 255, 255, 40))
        img = big.resize((d, d), Image.LANCZOS)
        isz = int(d * 0.24)
        for name, (fx, fy) in (("up", (0.5, 0.17)), ("down", (0.5, 0.83)), ("left", (0.17, 0.5)), ("right", (0.83, 0.5))):
            ic = icon_pil(name, isz, "#ffffff")
            if ic:
                img.alpha_composite(ic, (int(d * fx - isz / 2), int(d * fy - isz / 2)))
        return img

    # ---------------------------------------------------------------- UI
    def _stat_block(self, parent, title, bar=True, width=130):
        f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=9)
        f.pack(side="left", padx=4)
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(7, 0))
        ctk.CTkLabel(top, text=title, font=F(10, "bold"), text_color=MUTED, height=14).pack(side="left")
        val = ctk.CTkLabel(top, text="—", font=F(11, "bold"), text_color=TXT, height=14)
        val.pack(side="right", padx=(10, 0))
        b = ctk.CTkProgressBar(f, width=width, height=5, progress_color=ACCENT, fg_color=BORDER)
        b.pack(padx=12, pady=(5, 3))
        b.set(0)
        sub = ctk.CTkLabel(f, text="", font=F(10), text_color=MUTED, height=12, anchor="w")
        sub.pack(fill="x", padx=12, pady=(0, 7))
        return val, b, sub

    def _build_ui(self):
        r = self.root
        r.grid_columnconfigure(1, weight=1)
        r.grid_rowconfigure(1, weight=1)

        # header
        head = ctk.CTkFrame(r, height=70, corner_radius=0, fg_color=PANEL)
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        head.grid_propagate(False)
        head.grid_columnconfigure(1, weight=1)
        self.head = head
        logo = draw_app_icon(96)
        ctk.CTkLabel(head, text="", image=ctk.CTkImage(logo, logo, size=(34, 34))).grid(
            row=0, column=0, rowspan=2, padx=(18, 12), pady=16)
        ctk.CTkLabel(head, text=APP_NAME, font=F(17, "bold"), text_color=TXT, anchor="w").grid(
            row=0, column=1, sticky="sw", pady=(12, 0))
        self.head_sub = ctk.CTkLabel(head, text="", font=F(12), text_color=MUTED, anchor="w")
        self.head_sub.grid(row=1, column=1, sticky="nw", pady=(0, 12))

        right = ctk.CTkFrame(head, fg_color="transparent")
        right.grid(row=0, column=2, rowspan=2, padx=14)
        self.cpu_val, self.cpu_bar, self.cpu_sub = self._stat_block(right, "CPU", width=110)
        self.ram_val, self.ram_bar, self.ram_sub = self._stat_block(right, "RAM", width=130)
        self.disk_val, self.disk_bar, self.disk_sub = self._stat_block(right, tr("DISK"), width=150)
        ctk.CTkFrame(right, width=1, height=40, fg_color=BORDER).pack(side="left", padx=10)
        button(right, tr("Playback"), "history", "primary", lambda: self.open_playback()).pack(side="left", padx=4)
        button(right, "", "folder", "secondary", self._open_rec_dir).pack(side="left", padx=4)
        button(right, "", "settings", "secondary", lambda: SettingsDialog(self)).pack(side="left", padx=4)
        self.head_line = ctk.CTkFrame(r, height=1, corner_radius=0, fg_color=BORDER)
        self.head_line.grid(row=0, column=0, columnspan=2, sticky="sew")

        # sidebar
        side = ctk.CTkFrame(r, width=330, corner_radius=0, fg_color=PANEL)
        side.grid(row=1, column=0, sticky="ns")
        side.pack_propagate(False)
        self.side = side
        top = ctk.CTkFrame(side, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(top, text=tr("CAMERAS"), font=F(11, "bold"), text_color=MUTED).pack(side="left")
        button(top, "", "add", "primary", self._add_dialog, height=32).pack(side="right")
        button(top, "", "search", "secondary", lambda: ScanDialog(self), height=32).pack(side="right", padx=6)
        self.card_list = ctk.CTkScrollableFrame(side, fg_color="transparent", scrollbar_button_color=CARD,
                                                scrollbar_button_hover_color=CARD_HOVER)
        self.card_list.pack(fill="both", expand=True, padx=8)
        self.no_cams = ctk.CTkLabel(self.card_list, text=tr("No cameras.\nPress the magnifier to find them\nor + to add one."),
                                    font=F(12), text_color=MUTED, justify="center")
        bottom = ctk.CTkFrame(side, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=16)
        button(bottom, tr("Record all"), "record", "danger", self.record_all).pack(fill="x", pady=(0, 8))
        button(bottom, tr("Stop all"), "stop", "secondary", self.stop_all).pack(fill="x")
        self.side_line = ctk.CTkFrame(r, width=1, corner_radius=0, fg_color=BORDER)
        self.side_line.grid(row=1, column=0, sticky="nse")

        # video area
        main = ctk.CTkFrame(r, corner_radius=0, fg_color=BG)
        main.grid(row=1, column=1, sticky="nsew")
        self.main = main
        tb = ctk.CTkFrame(main, fg_color="transparent", height=44)
        tb.pack(fill="x", padx=18, pady=(14, 8))
        self.tb = tb
        self.view_title = ctk.CTkLabel(tb, text="", font=F(18, "bold"), text_color=TXT)
        self.view_title.pack(side="left")
        self.view_sub = ctk.CTkLabel(tb, text="", font=F(12), text_color=MUTED)
        self.view_sub.pack(side="left", padx=12, pady=(4, 0))
        self.btn_fs = button(tb, "", "full", "secondary", self.toggle_fullscreen)
        self.btn_fs.pack(side="right")
        self.btn_rec = button(tb, tr("Record"), "record", "secondary", lambda: self.toggle_record(self.selected))
        self.btn_rec.pack(side="right", padx=8)
        self.btn_listen = button(tb, tr("Listen"), "mute", "secondary", lambda: self.toggle_listen(self.single or self.selected))
        self.btn_listen.pack(side="right")
        self.btn_photo = button(tb, tr("Snapshot"), "camera", "secondary", lambda: self.snapshot(self.selected))
        self.btn_photo.pack(side="right", padx=(0, 8))
        self.btn_preset = button(tb, tr("Positions"), "pin", "secondary", self._preset_btn)
        self.layout_var = tk.StringVar(value=tr("Focus") if self.settings.get("layout") == "focus" else tr("Grid"))
        self.layout_seg = segmented(tb, [tr("Grid"), tr("Focus")], self._layout_changed, self.layout_var, height=34)
        self.layout_seg.pack(side="right", padx=(0, 12))
        self.btn_grid = button(tb, tr("Grid"), "grid", "primary", lambda: self.toggle_single(self.single))

        self.grid_frame = tk.Frame(main, bg=BG)
        self.grid_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.grid_frame.bind("<Configure>", lambda e: self._schedule_relayout())
        self.empty_main = ctk.CTkLabel(main, text="", image=icon("video", 56, BORDER), compound="top",
                                       font=F(14), text_color=MUTED)

        # status bar
        self.status = ctk.CTkLabel(r, text="   " + tr("Ready"), font=F(11), text_color=MUTED, anchor="w",
                                   fg_color=PANEL, corner_radius=0, height=26)
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew")

    def _first_run(self):
        if messagebox.askyesno(APP_NAME, tr("No camera configured.\n\nDo you want to search for cameras on your network?")):
            ScanDialog(self)

    def log(self, msg):
        self.status.configure(text="   " + datetime.datetime.now().strftime("%H:%M  ") + msg)

    def toast(self, msg, ms=2500):
        lbl = ctk.CTkLabel(self.main, text=f"   {msg}   ", font=F(13), text_color="#ffffff",
                           fg_color="#000000", corner_radius=10, height=36)
        lbl.place(relx=0.5, rely=0.03, anchor="n")
        self.root.after(ms, lbl.destroy)

    def cam(self, cid):
        return next((c for c in self.cameras if c["id"] == cid), None)

    def select(self, cid):
        prev = self.selected
        self.selected = cid
        for card in self.cards.values():
            card.refresh()
        self._refresh_toolbar()
        if prev != cid and self.layout_var.get() == tr("Focus") and not self.single:
            self._relayout()

    # ---------------------------------------------------------------- recording state / motion mode
    def motion_mode_for(self, cam):
        """Motion-only recording applies to cameras that have motion detection turned on."""
        return self.settings.get("rec_mode") == "motion" and cam.get("motion", True)

    def rec_state(self, cid):
        """0 = off, 1 = waiting for the camera, 2 = recording, 3 = armed (motion mode, no recent motion)."""
        r = self.recorders.get(cid)
        cam = self.cam(cid)
        if not r or not cam:
            return 0
        if r.active:
            if self.motion_mode_for(cam):
                v = self.viewers.get(cid)
                post = float(self.settings.get("motion_post_min", 2)) * 60
                if not v or (v.ev_start is None and time.time() - v.last_motion > post):
                    return 3
            return 2
        return 1 if r.want else 0

    def prune_motion(self):
        """Motion mode: delete the 1-minute files that are not near any motion event."""
        s = dict(self.settings)
        if s.get("rec_mode") != "motion":
            return 0
        since = float(s.get("motion_mode_since") or 0)
        post = float(s.get("motion_post_min", 2)) * 60
        pre = float(s.get("motion_pre_sec", 10))
        now = time.time()
        removed = 0
        for cam in list(self.cameras):
            if not self.motion_mode_for(cam):
                continue
            folder = os.path.join(s["rec_dir"], safe_name(cam["name"]))
            segs = list_segments(folder, 1)
            if not segs:
                continue
            windows = []
            for day in {seg[0].date() for seg in segs} | {datetime.date.today()}:
                for a, b in read_events(folder, day):
                    windows.append((a.timestamp() - pre, b.timestamp() + post))
            v = self.viewers.get(cam["id"])
            if v is not None:
                if v.ev_start is not None:
                    windows.append((v.ev_start - pre, now + post))
                if v.last_motion:
                    windows.append((v.last_motion - pre, v.last_motion + post))
            for start, end, path, size in segs:
                st, en = start.timestamp(), end.timestamp()
                if st < since or en > now - pre - 45:     # older than motion mode, or still too recent
                    continue
                if any(a < en and b > st for a, b in windows):
                    continue
                try:
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
        return removed

    def _prune_loop(self):
        def work():
            try:
                self.prune_motion()
            except Exception:
                log_exception("motion-mode pruning")
        threading.Thread(target=work, daemon=True).start()
        self.root.after(30000, self._prune_loop)

    # ---------------------------------------------------------------- live audio
    def set_listen(self, cid):
        """Play the live audio of one camera (None = silence)."""
        if self.audio_tap is not None:
            self.audio_tap.stop()
            self.audio_tap = None
        self.listen_cid = cid
        self.audio.set_owner(cid)
        cam = self.cam(cid) if cid else None
        if cam and cam.get("kind") not in STREAM_KINDS:
            self.audio_tap = RtspAudioTap(cam, self.audio)
            self.audio_tap.start()
        self._refresh_toolbar()

    def toggle_listen(self, cid):
        cam = self.cam(cid)
        if not cam:
            return
        if self.listen_cid == cid:
            self.set_listen(None)
            return
        if not self.audio.available:
            messagebox.showinfo(APP_NAME, tr("No audio output device is available."))
            return
        if cam.get("kind") == KIND_CLOUD:
            self.toast(tr("Live audio is not available for cloud cameras"))
            return
        if self.playback_win is not None and self.playback_win.winfo_exists():
            self.playback_win.player.audio_on = False
            self.playback_win.player._kill_audio()
        self.set_listen(cid)
        v = self.viewers.get(cid)
        if cam.get("kind") == KIND_NATIVE and v is not None and v.has_audio is None:
            self.root.after(6000, lambda: self._check_audio(cid))
        self.toast(tr("Listening: {name}").format(name=cam["name"]))

    def _check_audio(self, cid):
        v = self.viewers.get(cid)
        if self.listen_cid == cid and v is not None and v.has_audio is None:
            self.toast(tr("No audio from this camera (no microphone, or audio is off in its settings)"), 4000)

    # ---------------------------------------------------------------- cameras
    def _start_camera(self, cam):
        cid = cam["id"]
        v = make_viewer(cam, self)
        v.sub = True
        v.start()
        self.viewers[cid] = v
        self.recorders[cid] = Recorder(self, cam)
        if cam.get("record", True) and self.settings.get("autorec", True):
            self.recorders[cid].start()
        if cam.get("ptz") and cam.get("kind") != KIND_CUSTOM:
            self.ptz[cid] = PtzController(cam)
        cv = tk.Canvas(self.grid_frame, bg=TILE_BG, highlightthickness=2, highlightbackground=BG, bd=0,
                       cursor="hand2", width=1, height=1)
        img_id = cv.create_image(0, 0, anchor="center")
        actions = [("full", lambda: self.toggle_single(cid)), ("camera", lambda: self.snapshot(cid)),
                   ("record", lambda: self.toggle_record(cid)), ("volume", lambda: self.toggle_listen(cid)),
                   ("pin", lambda: self.preset_menu(cid, cv.winfo_pointerx(), cv.winfo_pointery()))]
        btn_ids = {}
        for name, cb in actions:
            tag = "b_" + name
            bid = cv.create_image(0, 0, image=self.hover_imgs[name], state="hidden", tags=("hbtn", tag))
            cv.tag_bind(tag, "<Button-1>", lambda e, cb=cb: cb())
            btn_ids[name] = bid
        pad = cv.create_image(0, 0, image=self.pad_img, state="hidden", tags=("hbtn", "ptzpad"))
        cv.tag_bind("ptzpad", "<ButtonPress-1>", lambda e: self._pad_press(cid, e))
        cv.bind("<ButtonRelease-1>", lambda e: self._pad_release(cid))
        cv.bind("<Enter>", lambda e: self._show_hover(cid, True))
        cv.bind("<Leave>", lambda e: (self._show_hover(cid, False), self._pad_release(cid)))
        cv.bind("<Button-1>", lambda e: None if self._on_btn(cv) else self.select(cid))
        cv.bind("<Double-1>", lambda e: None if self._on_btn(cv) else self.toggle_single(cid))
        cv.bind("<Button-3>", lambda e: self.show_menu(e, cid))
        self.tiles[cid] = {"cv": cv, "img": img_id, "btns": btn_ids, "pad": pad, "photo": None, "sig": None,
                           "size": (0, 0), "ph": (None, None), "ov": (None, None), "hover": False,
                           "motion": False}

    def _show_hover(self, cid, show):
        t = self.tiles.get(cid)
        cam = self.cam(cid)
        if not t or not cam:
            return
        t["hover"] = show
        cv = t["cv"]
        st = "normal" if show else "hidden"
        for name, bid in t["btns"].items():
            cv.itemconfigure(bid, state=st if (name != "pin" or cid in self.ptz) else "hidden")
        h = cv.winfo_height()
        cv.itemconfigure(t["pad"], state=st if (cid in self.ptz and h >= self.pad_d + 60 * self.px) else "hidden")

    @staticmethod
    def _on_btn(cv):
        cur = cv.find_withtag("current")
        return bool(cur) and "hbtn" in cv.gettags(cur[0])

    def _stop_camera(self, cid):
        if self.listen_cid == cid:
            self.set_listen(None)
        v = self.viewers.pop(cid, None)
        if v:
            v.stop()
        r = self.recorders.pop(cid, None)
        if r:
            threading.Thread(target=r.stop, daemon=True).start()
        p = self.ptz.pop(cid, None)
        if p:
            p.close()
        t = self.tiles.pop(cid, None)
        if t:
            t["cv"].destroy()
        if self.single == cid:
            self.single = None

    def _rebuild_cards(self):
        for c in self.cards.values():
            c.destroy()
        self.cards.clear()
        for cam in self.cameras:
            card = CameraCard(self.card_list, self, cam)
            card.pack(fill="x", pady=4, padx=4)
            self.cards[cam["id"]] = card
        if self.cameras:
            self.no_cams.pack_forget()
        else:
            self.no_cams.pack(pady=40)
        self._refresh_toolbar()

    def add_camera(self, cam):
        cam["id"] = self._new_id()
        self.cameras.append(cam)
        save_config(self.cfg)
        self._start_camera(cam)
        if cam.get("record") and not self.settings.get("autorec", True):
            self.recorders[cam["id"]].start()
        self.selected = cam["id"]
        self._rebuild_cards()
        self._relayout()
        self.log(tr("Added: {name}").format(name=cam["name"]))

    def _update_camera(self, new):
        cid = new["id"]
        idx = next(i for i, c in enumerate(self.cameras) if c["id"] == cid)
        was_single = self.single == cid
        self._stop_camera(cid)
        self.cameras[idx] = new
        save_config(self.cfg)
        if was_single:
            self.single = cid
        self._start_camera(new)
        if new.get("record"):
            self.recorders[cid].start()
        self._rebuild_cards()
        self._relayout()
        self.log(tr("Changed: {name}").format(name=new["name"]))

    def _add_dialog(self):
        CameraDialog(self.root, {"name": tr("Camera {n}").format(n=len(self.cameras) + 1)}, on_save=self.add_camera)

    def edit_dialog(self, cid):
        cam = self.cam(cid)
        if cam:
            CameraDialog(self.root, cam, on_save=self._update_camera)

    def delete(self, cid):
        cam = self.cam(cid)
        if not cam:
            return
        if not messagebox.askyesno(APP_NAME, tr("Delete the camera \"{name}\"?\n\nIts recordings stay on the disk.")
                                   .format(name=cam["name"])):
            return
        self._stop_camera(cid)
        self.cameras.remove(cam)
        save_config(self.cfg)
        if self.selected == cid:
            self.selected = self.cameras[0]["id"] if self.cameras else None
        self._rebuild_cards()
        self._relayout()

    def toggle_record(self, cid):
        cam = self.cam(cid)
        if not cam:
            return
        r = self.recorders[cid]
        if r.want:
            threading.Thread(target=r.stop, daemon=True).start()
            cam["record"] = False
            self.log(tr("Recording stopped: {name}").format(name=cam["name"]))
        else:
            r.start()
            cam["record"] = True
            self.log(tr("Recording started: {name}").format(name=cam["name"]))
        save_config(self.cfg)
        self._refresh_all()

    def record_all(self):
        for cam in self.cameras:
            cam["record"] = True
            self.recorders[cam["id"]].start()
        save_config(self.cfg)
        self.log(tr("Recording started on all cameras"))
        self._refresh_all()

    def stop_all(self):
        if not self.cameras or not messagebox.askyesno(APP_NAME, tr("Stop recording on all cameras?")):
            return
        for cam in self.cameras:
            cam["record"] = False
            threading.Thread(target=self.recorders[cam["id"]].stop, daemon=True).start()
        save_config(self.cfg)
        self.log(tr("Recording stopped on all cameras"))
        self._refresh_all()

    def snapshot(self, cid):
        cam = self.cam(cid)
        if not cam:
            return
        frame, _ = self.viewers[cid].get()
        if frame is None:
            messagebox.showinfo(APP_NAME, tr("No picture available from this camera."))
            return
        folder = os.path.join(self.settings["rec_dir"], safe_name(cam["name"]), SNAP_DIR)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, datetime.datetime.now().strftime("Snapshot_%Y-%m-%d_%H-%M-%S.jpg"))
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if ok:
            with open(path, "wb") as f:
                f.write(buf.tobytes())
            self.log(tr("Snapshot saved in {path}").format(path=path))
            self.toast(tr("Snapshot saved"))

    def motion_event(self, cam, start, end):
        """Called by the video threads: stores a motion event."""
        try:
            d = datetime.datetime.fromtimestamp(start)
            folder = os.path.join(self.settings["rec_dir"], safe_name(cam["name"]), EVENTS_DIR)
            os.makedirs(folder, exist_ok=True)
            with self.ev_lock, open(os.path.join(folder, d.strftime("%Y-%m-%d") + ".txt"), "a", encoding="utf-8") as f:
                f.write(f"{start:.1f} {end:.1f}\n")
        except OSError:
            pass

    def open_playback(self, cid=None):
        if self.playback_win is not None and self.playback_win.winfo_exists():
            self.playback_win._bring_front()
            if cid:
                self.playback_win.set_camera(cid)
            return
        if not self.cameras:
            messagebox.showinfo(APP_NAME, tr("Add a camera first."))
            return
        self.playback_win = PlaybackWindow(self, cid)

    def _open_rec_dir(self, cid=None):
        d = self.settings["rec_dir"]
        cam = self.cam(cid) if cid else None
        if cam and os.path.isdir(os.path.join(d, safe_name(cam["name"]))):
            d = os.path.join(d, safe_name(cam["name"]))
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    def apply_settings(self, new):
        old = dict(self.settings)
        self.settings.update(new)
        save_config(self.cfg)
        if new.get("lang") and new["lang"] != old.get("lang"):
            if messagebox.askyesno(APP_NAME, tr("Restart the program now to change the language?")):
                self.restart = True
                self.root.after(100, lambda: self._on_close(ask=False))
                return
        if old.get("hw_decode", "auto") != new.get("hw_decode", "auto"):
            for v in self.viewers.values():      # live view: new decoders with the new setting
                v.gpu_failed = False
                v.reload_decoder = True
        # folder, file length, audio or recording mode changed: restart the active recordings
        if any(old.get(k) != new.get(k) for k in ("rec_dir", "segment_min", "audio", "rec_mode")):
            for cam in self.cameras:
                r = self.recorders[cam["id"]]
                if r.want:
                    def restart(r=r):
                        r.stop()
                        r.start()
                    threading.Thread(target=restart, daemon=True).start()
        self.log(tr("Settings saved"))
        self.root.after(500, self._run_cleanup)

    # ---------------------------------------------------------------- PTZ
    def _mute_motion(self, cid):
        v = self.viewers.get(cid)
        if v:
            v.motion_mute_until = time.time() + 4

    def _pad_press(self, cid, e):
        p = self.ptz.get(cid)
        t = self.tiles.get(cid)
        if not p or not t:
            return
        cx, cy = t["cv"].coords(t["pad"])
        dx, dy = e.x - cx, e.y - cy
        if math.hypot(dx, dy) < self.pad_d * 0.17:
            return
        sector = int(round(math.degrees(math.atan2(-dy, dx)) / 45.0)) % 8
        p.start(PTZ_DIRS[sector])
        self._mute_motion(cid)

    def _pad_release(self, cid):
        p = self.ptz.get(cid)
        if p and p.moving:
            p.stop()
            self._mute_motion(cid)

    def _key_ptz(self, direction, press):
        cid = self.single or self.selected
        p = self.ptz.get(cid)
        if not p:
            return
        if press:
            if self._key_stop_job:
                self.root.after_cancel(self._key_stop_job)
                self._key_stop_job = None
            p.start(direction)
            self._mute_motion(cid)
        else:
            def stop():
                self._key_stop_job = None
                p.stop()
                self._mute_motion(cid)
            self._key_stop_job = self.root.after(120, stop)

    def preset_menu(self, cid, x, y):
        cam = self.cam(cid)
        p = self.ptz.get(cid)
        if not cam or not p:
            return
        presets = cam.setdefault("presets", {})
        m = dark_menu(self.root)
        for n, name in sorted(presets.items(), key=lambda kv: int(kv[0])):
            m.add_command(label=f"  {name}", command=lambda n=n: (p.goto(int(n)), self._mute_motion(cid),
                                                                    self.log(tr("{cam}: going to \"{pos}\"").format(cam=cam["name"], pos=presets[n]))))
        if presets:
            m.add_separator()
        m.add_command(label="  " + tr("Save the current position..."), command=lambda: self._save_preset(cid))
        if presets:
            sub = dark_menu(m)
            for n, name in sorted(presets.items(), key=lambda kv: int(kv[0])):
                sub.add_command(label=f"  {name}", command=lambda n=n: self._del_preset(cid, n))
            m.add_cascade(label="  " + tr("Delete a position"), menu=sub)
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def _preset_btn(self):
        b = self.btn_preset
        self.preset_menu(self.single or self.selected, b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    def _save_preset(self, cid):
        cam = self.cam(cid)
        p = self.ptz.get(cid)
        if not cam or not p:
            return
        dlg = ctk.CTkInputDialog(text=tr("Name of this position (e.g. Gate, Yard):"), title=tr("Save position"),
                                 fg_color=PANEL, button_fg_color=ACCENT, button_hover_color=ACCENT_H,
                                 entry_fg_color=INPUT, entry_border_color=BORDER)
        name = (dlg.get_input() or "").strip()
        if not name:
            return
        presets = cam.setdefault("presets", {})
        used = {int(k) for k in presets}
        n = next(i for i in range(1, 250) if i not in used)
        presets[str(n)] = name[:30]
        save_config(self.cfg)
        p.save(n)
        self.log(tr("Position \"{name}\" saved").format(name=name))
        self.toast(tr("Position \"{name}\" saved").format(name=name))

    def _del_preset(self, cid, n):
        cam = self.cam(cid)
        p = self.ptz.get(cid)
        if cam and n in cam.get("presets", {}):
            name = cam["presets"].pop(n)
            save_config(self.cfg)
            if p:
                p.clear(int(n))
            self.log(tr("Position \"{name}\" deleted").format(name=name))

    # ---------------------------------------------------------------- menu
    def show_menu(self, event, cid):
        self.select(cid)
        r = self.recorders.get(cid)
        m = dark_menu(self.root)
        m.add_command(label="  " + (tr("Back to the grid") if self.single == cid else tr("Enlarge")),
                      command=lambda: self.toggle_single(cid))
        if self.fullscreen:
            m.add_command(label="  " + tr("Exit full screen"), command=self.toggle_fullscreen)
        m.add_command(label="  " + (tr("Stop recording") if r and r.want else tr("Start recording")),
                      command=lambda: self.toggle_record(cid))
        m.add_command(label="  " + (tr("Stop listening") if self.listen_cid == cid else tr("Listen (live audio)")),
                      command=lambda: self.toggle_listen(cid))
        m.add_command(label="  " + tr("Take snapshot"), command=lambda: self.snapshot(cid))
        m.add_command(label="  " + tr("Play recordings"), command=lambda: self.open_playback(cid))
        if cid in self.ptz:
            m.add_command(label="  " + tr("Saved positions..."), command=lambda: self.preset_menu(cid, event.x_root, event.y_root))
        m.add_command(label="  " + tr("Open recordings folder"), command=lambda: self._open_rec_dir(cid))
        m.add_separator()
        m.add_command(label="  " + tr("Edit..."), command=lambda: self.edit_dialog(cid))
        m.add_command(label="  " + tr("Delete"), command=lambda: self.delete(cid))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    # ---------------------------------------------------------------- views
    def toggle_single(self, cid):
        if not cid:
            return
        self.single = None if self.single == cid else cid
        if self.single:
            self.selected = cid
        self._relayout()
        self._refresh_all()

    def _layout_changed(self, v):
        self.settings["layout"] = "focus" if v == tr("Focus") else "auto"
        save_config(self.cfg)
        self._relayout()

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        chrome = (self.head, self.head_line, self.side, self.side_line, self.status)
        if self.fullscreen:
            for w in chrome:
                w.grid_remove()
            self.main.grid_configure(row=0, column=0, columnspan=2, rowspan=3)
            self.tb.pack_forget()
            self.grid_frame.pack_configure(padx=0, pady=0)
            self.root.attributes("-fullscreen", True)
            self.toast(tr("Full screen · press Esc to exit"), 3000)
        else:
            for w in chrome:
                w.grid()
            self.main.grid_configure(row=1, column=1, columnspan=1, rowspan=1)
            self.tb.pack(fill="x", padx=18, pady=(14, 8), before=self.grid_frame)
            self.grid_frame.pack_configure(padx=14, pady=(0, 14))
            self.root.attributes("-fullscreen", False)
        self.btn_fs.configure(image=icon("back" if self.fullscreen else "full", 16, TXT))
        self._grid_key = None
        self.root.after(80, self._relayout)

    def _escape(self):
        if self.single:
            self.toggle_single(self.single)
        elif self.fullscreen:
            self.toggle_fullscreen()

    def _refresh_all(self):
        for c in self.cards.values():
            c.refresh()
        self._refresh_toolbar()

    def _refresh_toolbar(self):
        n = len(self.cameras)
        if self.single and self.cam(self.single):
            self.view_title.configure(text=self.cam(self.single)["name"])
            hint = tr("arrows or the pad on the video to move it") + " · " if self.single in self.ptz else ""
            self.view_sub.configure(text=tr("High quality") + " · " + hint + tr("Esc to go back to the grid"))
            if self.btn_grid.winfo_manager() != "pack":
                self.btn_grid.pack(side="right", padx=(8, 0), before=self.btn_fs)
            self.layout_seg.pack_forget()
        else:
            self.view_title.configure(text=tr("All cameras"))
            self.view_sub.configure(text=(tr("1 camera") if n == 1 else tr("{n} cameras").format(n=n))
                                    + " · " + tr("double-click a video to enlarge it"))
            self.btn_grid.pack_forget()
        target = self.single or self.selected
        if target in self.ptz:
            if self.btn_preset.winfo_manager() != "pack":
                self.btn_preset.pack(side="right", padx=(0, 8), after=self.btn_photo)
        else:
            self.btn_preset.pack_forget()
        # order from the left: [Grid|Focus] [Positions] [Snapshot] [Listen] [Record] [Full screen]
        if not self.single:
            anchor = self.btn_preset if self.btn_preset.winfo_manager() == "pack" else self.btn_photo
            if self.layout_seg.winfo_manager() != "pack":
                self.layout_seg.pack(side="right", padx=(0, 12), after=anchor)
            else:
                order = self.tb.pack_slaves()
                if order.index(self.layout_seg) != order.index(anchor) + 1:
                    self.layout_seg.pack_configure(after=anchor)
        r = self.recorders.get(self.selected)
        state = "normal" if self.selected else "disabled"
        self.btn_photo.configure(state=state)
        listening = self.listen_cid is not None and self.listen_cid == (self.single or self.selected)
        self.btn_listen.configure(state=state, text=tr("Mute") if listening else tr("Listen"),
                                  image=icon("volume" if listening else "mute", 16, GREEN if listening else TXT))
        if r and r.want:
            self.btn_rec.configure(text=tr("Stop REC"), image=icon("stop", 16, TXT), state=state)
        else:
            self.btn_rec.configure(text=tr("Record"), image=icon("record", 16, RED), state=state)

    def _schedule_relayout(self):
        if self._relayout_job:
            self.root.after_cancel(self._relayout_job)
        self._relayout_job = self.root.after(120, self._relayout_if_needed)

    def _relayout_if_needed(self):
        self._relayout_job = None
        if self._layout_key() != self._grid_key:
            self._relayout()
        for t in self.tiles.values():
            t["sig"] = None

    def _layout_key(self):
        ids = [c["id"] for c in self.cameras]
        if self.single:
            return ("single", self.single)
        if self.layout_var.get() == tr("Focus") and len(ids) >= 3:
            return ("focus", self.selected if self.selected in ids else ids[0], tuple(ids))
        w = max(self.grid_frame.winfo_width(), 400)
        h = max(self.grid_frame.winfo_height(), 300)
        return ("auto",) + best_grid(len(ids), w, h) + (tuple(ids),) if ids else ("empty",)

    def _relayout(self):
        for t in self.tiles.values():
            t["cv"].grid_forget()
        for i in range(30):
            self.grid_frame.rowconfigure(i, weight=0, uniform="", minsize=0)
            self.grid_frame.columnconfigure(i, weight=0, uniform="", minsize=0)
        ids = [c["id"] for c in self.cameras]
        key = self._layout_key()
        self._grid_key = key
        if not ids:
            self.grid_frame.pack_forget()
            self.empty_main.configure(text="\n" + tr("Add the first camera with the + button\nor find it on the network with the magnifier"))
            self.empty_main.pack(expand=True)
            self._refresh_toolbar()
            return
        self.empty_main.pack_forget()
        if not self.grid_frame.winfo_ismapped():
            self.grid_frame.pack(fill="both", expand=True, padx=0 if self.fullscreen else 14,
                                 pady=0 if self.fullscreen else (0, 14))
        big = None
        if key[0] == "single":
            pos = {self.single: (0, 0, 1, 1)}
            rows = cols = 1
            big = self.single
        elif key[0] == "focus":
            big = key[1]
            others = [i for i in ids if i != big]
            k = 3
            while (k - 1) + k < len(others):
                k += 1
            right = k - 1
            rows = k - 1 if len(others) <= right else k
            cols = k
            pos = {big: (0, 0, k - 1, k - 1)}
            for j, cid in enumerate(others):
                pos[cid] = (j, k - 1, 1, 1) if j < right else (k - 1, j - right, 1, 1)
        else:
            cols, rows = key[1], key[2]
            pos = {cid: (i // cols, i % cols, 1, 1) for i, cid in enumerate(ids)}
        gap = 2 if self.fullscreen else 4
        for cid, (r, c, rs, cs) in pos.items():
            t = self.tiles[cid]
            t["cv"].grid(row=r, column=c, rowspan=rs, columnspan=cs, sticky="nsew", padx=gap, pady=gap)
            t["sig"] = None
            t["size"] = (0, 0)
            t["cv"].itemconfigure(t["btns"]["full"], image=self.hover_imgs["back" if self.single else "full"])
        for r in range(rows):
            self.grid_frame.rowconfigure(r, weight=1, uniform="r")
        for c in range(cols):
            self.grid_frame.columnconfigure(c, weight=1, uniform="c")
        # high-quality stream only for the big tile
        for vid, v in self.viewers.items():
            v.sub = vid != big
        self._refresh_toolbar()

    # ---------------------------------------------------------------- video drawing
    # Per frame a tile costs: resize + one masked paste of the overlay + an update of its Tk image.
    # The overlay (dark band, name, pills) is drawn only when something in it changes.

    def _band_alpha(self, rows, band):
        """Alpha of the dark band at the top of a tile: darkening the picture by g (0.3 -> 1.0)
        is the same as laying black over it with alpha 1 - g."""
        key = (rows, band)
        a = self._grad_cache.get(key)
        if a is None:
            a = np.zeros(rows, np.uint8)
            if band > 2:
                a[:band] = np.round((1.0 - np.linspace(0.3, 1.0, band)) * 255).astype(np.uint8)
            self._grad_cache[key] = a
        return a

    def _overlay(self, t, w, h, name, rec, blink, motion, listening):
        rows = max(1, min(int(56 * self.px), h))
        band = min(int(56 * self.px), h // 3)
        key = (w, rows, band, name, rec, blink if rec == 2 else 0, motion, listening, self.px)
        if t["ov"][0] == key:
            return t["ov"][1]
        arr = np.zeros((rows, w, 4), np.uint8)
        arr[..., 3] = self._band_alpha(rows, band)[:, None]
        ov = Image.fromarray(arr, "RGBA")
        self._draw_overlay(ov, name, rec, blink, motion, listening)
        t["ov"] = (key, ov)
        return ov

    def _render_frame(self, frame, w, h):
        return Image.fromarray(fit_image(frame, w, h))

    def _wrap(self, d, text, font, maxw):
        words, lines, cur = text.split(), [], ""
        for wd in words:
            t = (cur + " " + wd).strip()
            if d.textlength(t, font=font) <= maxw or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        return lines

    def _render_placeholder(self, t, w, h, status):
        key = (w, h, status)
        if t["ph"][0] == key:
            return t["ph"][1].copy()
        img = Image.new("RGB", (w, h), hex2rgb(TILE_BG))
        d = ImageDraw.Draw(img)
        ic = icon_pil("video", int(46 * self.px), "#3a4150")
        lines = self._wrap(d, status or tr("Waiting for video..."), self.f_status, w - 40 * self.px)
        lh = int(20 * self.px)
        total = (ic.height if ic else 0) + int(12 * self.px) + lh * len(lines)
        y = (h - total) // 2
        if ic:
            img.paste(ic, ((w - ic.width) // 2, y), ic)
            y += ic.height + int(12 * self.px)
        for ln in lines:
            tw = d.textlength(ln, font=self.f_status)
            d.text(((w - tw) / 2, y), ln, font=self.f_status, fill=hex2rgb(MUTED))
            y += lh
        t["ph"] = (key, img)
        return img.copy()

    def _pill(self, d, x1, y0, text, color, dot=False, blink=0):
        px = self.px
        ph, pad, dsz, gap = int(22 * px), int(9 * px), int(8 * px), int(6 * px)
        tw = d.textlength(text, font=self.f_pill)
        pw = int(pad * 2 + tw + (dsz + gap if dot else 0))
        x0 = x1 - pw
        y1 = y0 + ph
        d.rounded_rectangle((x0, y0, x1, y1), radius=ph // 2, fill=color)
        tx = x0 + pad
        if dot:
            cy = (y0 + y1) // 2
            if not blink:
                d.ellipse((tx, cy - dsz // 2, tx + dsz, cy + dsz // 2), fill=(255, 255, 255))
            tx += dsz + gap
        b = d.textbbox((0, 0), text, font=self.f_pill)
        d.text((tx, y0 + (ph - (b[3] - b[1])) // 2 - b[1]), text, font=self.f_pill, fill=(255, 255, 255))
        return x0

    def _draw_overlay(self, pil, name, rec, blink, motion, listening=False):
        d = ImageDraw.Draw(pil)
        px = self.px
        x, y = int(14 * px), int(11 * px)
        d.text((x + 1, y + 1), name, font=self.f_name, fill=(0, 0, 0))
        d.text((x, y), name, font=self.f_name, fill=(255, 255, 255))
        name_end = x + d.textlength(name, font=self.f_name) + 12 * px
        x1 = pil.width - int(12 * px)
        y0 = int(12 * px)
        if rec and x1 - 60 * px > name_end:
            if rec == 2:
                x1 = self._pill(d, x1, y0, "REC", hex2rgb(RED_D), dot=True, blink=blink) - int(6 * px)
            elif rec == 3:
                x1 = self._pill(d, x1, y0, tr("ARMED"), (29, 78, 216)) - int(6 * px)
            else:
                x1 = self._pill(d, x1, y0, tr("WAITING"), (180, 83, 9)) - int(6 * px)
        if listening and x1 - 70 * px > name_end:
            x1 = self._pill(d, x1, y0, tr("AUDIO"), (21, 128, 61)) - int(6 * px)
        if motion and x1 - 90 * px > name_end:
            self._pill(d, x1, y0, tr("MOTION"), (217, 119, 6))

    def _tick(self):
        try:
            self._draw()
        except Exception:
            log_exception("live video drawing")
        self.root.after(66, self._tick)  # ~15 fps

    def _draw(self):
        now = time.time()
        blink = int(now * 1.6) % 2
        for cid, t in self.tiles.items():
            cv = t["cv"]
            if not cv.winfo_ismapped():
                continue
            w, h = cv.winfo_width() - 4, cv.winfo_height() - 4
            if w < 40 or h < 40:
                continue
            v = self.viewers.get(cid)
            r = self.recorders.get(cid)
            cam = self.cam(cid)
            if not v or not cam:
                continue
            frame, fid = v.get()
            live = frame is not None and now - v.last_frame_t < 6
            rec = self.rec_state(cid)
            listening = self.listen_cid == cid
            motion = live and cam.get("motion", True) and now - v.last_motion < 4
            if motion != t["motion"]:
                t["motion"] = motion
                cv.configure(highlightbackground=ORANGE if motion else BG)
            sig = (fid if live else -1, live, v.status, rec, blink if rec == 2 else 0, w, h, cam["name"], motion,
                   listening)
            if sig == t["sig"]:
                continue
            t["sig"] = sig
            pil = self._render_frame(frame, w, h) if live else self._render_placeholder(t, w, h, v.status)
            ov = self._overlay(t, pil.width, pil.height, cam["name"], rec, blink, motion, listening)
            pil.paste(ov, (0, 0), ov)
            photo = t["photo"]
            if photo is not None and (photo.width(), photo.height()) == pil.size:
                photo.paste(pil)                      # reuse the tile's Tk image: no new image per frame
            else:
                t["photo"] = ImageTk.PhotoImage(pil)
                cv.itemconfigure(t["img"], image=t["photo"])
            if (w, h) != t["size"]:
                t["size"] = (w, h)
                cw, ch = w + 4, h + 4
                cv.coords(t["img"], cw // 2, ch // 2)
                step = int(44 * self.px)
                bx, by = cw - int(30 * self.px), ch - int(30 * self.px)
                order = ["record", "volume", "camera", "full"] + (["pin"] if cid in self.ptz else [])
                for i, name in enumerate(order):
                    cv.coords(t["btns"][name], bx - i * step, by)
                m = int(14 * self.px) + self.pad_d // 2
                cv.coords(t["pad"], m, ch - m)
                if t["hover"]:
                    self._show_hover(cid, True)
            rb = t["btns"]["record"]
            want_img = self.hover_imgs["stop" if (r and r.want) else "record"]
            if cv.itemcget(rb, "image") != str(want_img):
                cv.itemconfigure(rb, image=want_img)
            vb = t["btns"]["volume"]
            vol_img = self.hover_imgs["volume" if listening else "mute"]
            if cv.itemcget(vb, "image") != str(vol_img):
                cv.itemconfigure(vb, image=vol_img)

    # ---------------------------------------------------------------- statistics
    def _stats_loop(self):
        me = psutil.Process()
        cache = {}
        ncpu = psutil.cpu_count() or 1
        psutil.cpu_percent(None)
        while True:
            try:
                cpu = psutil.cpu_percent(None)
                vm = psutil.virtual_memory()
                procs = [me] + me.children(recursive=True)
                app_cpu, app_mem, alive = 0.0, 0, set()
                for p in procs:
                    pr = cache.setdefault(p.pid, p)
                    alive.add(p.pid)
                    try:
                        app_cpu += pr.cpu_percent(None)
                        app_mem += pr.memory_info().rss
                    except psutil.Error:
                        pass
                cache = {k: v for k, v in cache.items() if k in alive}
                self.stats = {"cpu": cpu, "app_cpu": app_cpu / ncpu, "ram_used": vm.total - vm.available,
                              "ram_total": vm.total, "app_mem": app_mem}
            except Exception:
                pass
            time.sleep(2)

    def _slow_tick(self):
        try:
            # keep the PC awake while recording (from this thread only: the request is per thread)
            self.keep_awake.set(self.settings.get("keep_awake", True)
                                and any(r.want for r in self.recorders.values()))
            if self.show_signal is not None and self.show_signal.poll():
                self.show_window()      # Vigilo was started a second time
        except Exception:
            log_exception("keep awake / show signal")
        try:
            for card in self.cards.values():
                card.refresh()
            n = len(self.cameras)
            recs = sum(1 for r in self.recorders.values() if r.active)
            lives = sum(1 for v in self.viewers.values() if time.time() - v.last_frame_t < 6)
            status = tr("{live}/{n} connected  ·  {rec} recording").format(live=lives, n=n, rec=recs)
            self.head_sub.configure(text=status)
            self.tray.set_title(f"{APP_NAME} · {status}")
            s = self.stats
            if s:
                self.cpu_val.configure(text=f"{s['cpu']:.0f}%")
                self.cpu_bar.set(min(1, s["cpu"] / 100))
                self.cpu_bar.configure(progress_color=RED if s["cpu"] > 85 else ORANGE if s["cpu"] > 60 else ACCENT)
                self.cpu_sub.configure(text=tr("program") + f" {s['app_cpu']:.0f}%")
                self.ram_val.configure(text=f"{s['ram_used'] / 1024**3:.1f} / {s['ram_total'] / 1024**3:.0f} GB")
                frac = s["ram_used"] / s["ram_total"]
                self.ram_bar.set(frac)
                self.ram_bar.configure(progress_color=RED if frac > 0.9 else ORANGE if frac > 0.75 else ACCENT)
                self.ram_sub.configure(text=tr("program") + f" {fmt_size(s['app_mem'])}")
            d = self.settings["rec_dir"]
            probe = d if os.path.isdir(d) else (os.path.splitdrive(d)[0] + "\\")
            u = shutil.disk_usage(probe)
            self.disk_val.configure(text=tr("{size} free").format(size=fmt_gb(u.free)))
            self.disk_bar.set(u.used / u.total if u.total else 0)
            self.disk_bar.configure(progress_color=RED if u.free < 20 * 1024**3 else ACCENT)
            sub = (tr("recordings {size}").format(size=fmt_size(self.rec_total)) if self.rec_total is not None
                   else tr("of {size}").format(size=fmt_gb(u.total)))
            cap = float(self.settings.get("max_rec_gb", 0) or 0)
            if cap > 0 and self.rec_total is not None:
                sub += f" / {cap:g} GB"
            self.disk_sub.configure(text=sub)
            self._refresh_toolbar()
        except Exception:
            log_exception("status update")
        self.root.after(2000, self._slow_tick)

    def _run_cleanup(self):
        s = dict(self.settings)

        def work():
            total = cleanup_recordings(s, lambda m: self.root.after(0, self.log, m))
            self.rec_total = total

        threading.Thread(target=work, daemon=True).start()

    def _cleanup_loop(self):
        self._run_cleanup()
        self.root.after(2 * 60 * 1000, self._cleanup_loop)

    # ---------------------------------------------------------------- closing
    def _on_window_close(self):
        """The window's X button: keep running in the notification area, or really close."""
        if self.settings.get("tray_on_close", True) and self.tray.available:
            self.hide_to_tray()
        else:
            self._on_close()

    def hide_to_tray(self):
        if self.fullscreen:
            self.toggle_fullscreen()
        self.root.withdraw()
        if not self.tray_hint_shown:
            self.tray_hint_shown = True
            self.tray.notify(tr("Vigilo is still running in the notification area. Recording continues."),
                             APP_NAME)

    def show_window(self):
        r = self.root
        try:
            r.deiconify()
            if r.state() == "iconic":
                r.state("normal")
            r.lift()
            r.attributes("-topmost", True)
            r.after(300, lambda: r.attributes("-topmost", False))
            r.focus_force()
        except tk.TclError:
            pass

    def quit_from_tray(self):
        self.show_window()      # the confirmation must be visible
        self._on_close()

    def _on_close(self, ask=True):
        if ask and any(r.want for r in self.recorders.values()):
            if not messagebox.askyesno(APP_NAME, tr("Closing the program stops the recording.\n\nClose anyway?")):
                return
        self.log(tr("Closing, saving the recordings..."))
        self.root.update()
        self.set_listen(None)
        if self.playback_win is not None:
            try:
                self.playback_win.close()
            except Exception:
                pass
        for p in self.ptz.values():
            p.close()
        for v in self.viewers.values():
            v.stop()
        threads = [threading.Thread(target=r.stop) for r in self.recorders.values()]
        for t in threads:
            t.start()
        for t in threads:
            t.join(9)
        self.keep_awake.set(False)
        self.tray.stop()
        if self.show_signal is not None:
            self.show_signal.close()
        self.root.destroy()


def run_app(argv=()):
    """Start the user interface. Returns the exit code of the process (EXIT_RESTART = start again)."""
    lock = single_instance()
    if lock is None:
        return 0
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    install_crash_log(root)
    app = App(root, recovered="--recovered" in argv)
    root.mainloop()
    release_instance(lock)
    if app.restart:
        if "--child" in argv:       # started by the watchdog: it starts us again
            return EXIT_RESTART
        subprocess.Popen(restart_command(), creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0)
    return 0
