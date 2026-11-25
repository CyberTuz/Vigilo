"""
Playback window: calendar, timeline, motion list, snapshots and export.
"""

import os
import math
import time
import calendar
import threading
import subprocess
import datetime
import tkinter as tk
from tkinter import messagebox

from PIL import Image
from PIL import ImageTk
import customtkinter as ctk

from i18n import tr
from ..common import APP_ICO, APP_NAME, EXPORT_DIR, FFMPEG, MONTHS, NOWIN, safe_name, SNAP_DIR, WEEKDAYS
from .theme import (
    ACCENT, BG, BORDER, CARD, CARD_HOVER, fit_image, icon, MUTED, ORANGE, PANEL, pil_font, RED, TILE_BG, TXT,
)
from ..archive import export_clip, list_segments, read_events
from ..player import Player
from .. import hwaccel
from ..system import log_exception
from .widgets import button, dark_menu, entry, F, label, segmented


class MiniCalendar(ctk.CTkFrame):
    def __init__(self, master, on_select):
        super().__init__(master, fg_color=CARD, corner_radius=10)
        self.on_select = on_select
        self.marked = set()
        self.selected = datetime.date.today()
        self.month = (self.selected.year, self.selected.month)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkButton(head, text="", image=icon("left", 14, TXT), width=30, height=28, fg_color="transparent",
                      hover_color=CARD_HOVER, command=lambda: self._shift(-1)).pack(side="left")
        ctk.CTkButton(head, text="", image=icon("right", 14, TXT), width=30, height=28, fg_color="transparent",
                      hover_color=CARD_HOVER, command=lambda: self._shift(1)).pack(side="right")
        self.title = ctk.CTkLabel(head, text="", font=F(13, "bold"), text_color=TXT)
        self.title.pack(expand=True)
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(padx=8, pady=(0, 10))
        for i, d in enumerate(tr("MTWTFSS")):
            ctk.CTkLabel(grid, text=d, font=F(10, "bold"), text_color=MUTED, width=32, height=18).grid(row=0, column=i)
        self.btns = []
        for i in range(42):
            b = ctk.CTkButton(grid, text="", width=32, height=28, corner_radius=7, font=F(11),
                              fg_color="transparent", hover_color=CARD_HOVER, text_color=MUTED,
                              command=lambda i=i: self._click(i))
            b.grid(row=1 + i // 7, column=i % 7, padx=1, pady=1)
            self.btns.append(b)
        self.render()

    def _shift(self, delta):
        y, m = self.month
        m += delta
        if m < 1:
            y, m = y - 1, 12
        elif m > 12:
            y, m = y + 1, 1
        self.month = (y, m)
        self.render()

    def set_marked(self, dates):
        self.marked = set(dates)
        self.render()

    def select(self, d):
        self.selected = d
        self.month = (d.year, d.month)
        self.render()

    def _click(self, i):
        y, m = self.month
        first, ndays = calendar.monthrange(y, m)
        day = i - first + 1
        if 1 <= day <= ndays:
            self.select(datetime.date(y, m, day))
            self.on_select(self.selected)

    def render(self):
        y, m = self.month
        self.title.configure(text=f"{tr(MONTHS[m - 1])} {y}")
        first, ndays = calendar.monthrange(y, m)
        today = datetime.date.today()
        for i, b in enumerate(self.btns):
            day = i - first + 1
            if 1 <= day <= ndays:
                d = datetime.date(y, m, day)
                if d == self.selected:
                    b.configure(text=str(day), state="normal", fg_color=ACCENT, text_color="#ffffff",
                                border_width=0)
                elif d in self.marked:
                    b.configure(text=str(day), state="normal", fg_color=CARD_HOVER, text_color=TXT,
                                border_width=1 if d == today else 0, border_color=ACCENT)
                else:
                    b.configure(text=str(day), state="normal", fg_color="transparent", text_color="#555c6b",
                                border_width=1 if d == today else 0, border_color=BORDER)
            else:
                b.configure(text="", state="disabled", fg_color="transparent", border_width=0)


class PlaybackWindow(ctk.CTkToplevel):
    SPEEDS = ["1x", "2x", "4x", "8x", "16x"]
    ZOOMS = {"24 h": 86400, "4 h": 14400, "1 h": 3600, "10 min": 600}

    def __init__(self, app, cam_id=None):
        super().__init__(app.root)
        self.app = app
        self.title(tr("Playback"))
        self.configure(fg_color=BG)
        self.geometry("1360x860")
        self.minsize(1050, 680)
        if os.path.exists(APP_ICO):
            try:
                self.iconbitmap(APP_ICO)
            except Exception:
                pass
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<space>", lambda e: self.toggle_play())
        self.bind("<Left>", lambda e: self.jump(-10))
        self.bind("<Right>", lambda e: self.jump(10))
        self.player = Player()
        self.player.hw_args = lambda: hwaccel.decode_args(app.settings)
        self.segments = []
        self.all_segments = []
        self.events = []
        self.day = datetime.date.today()
        self.cam_id = None
        self.v0, self.v1 = 0.0, 86400.0
        self.hover_x = None
        self.photo = None
        self.last_fid = -1
        self.dragging = False
        self.f_tl = pil_font("segoeui.ttf", 11 * app.px)
        self.sticky_until = 0.0      # keep a message (snapshot/export) on screen for a while
        self.player.audio_out = app.audio

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # left column
        left = ctk.CTkFrame(self, width=300, corner_radius=0, fg_color=PANEL)
        left.grid(row=0, column=0, sticky="ns")
        left.pack_propagate(False)
        ctk.CTkLabel(left, text=tr("CAMERA"), font=F(11, "bold"), text_color=MUTED).pack(anchor="w", padx=16, pady=(18, 4))
        self.cam_names = {c["name"]: c["id"] for c in app.cameras}
        self.cam_var = tk.StringVar()
        ctk.CTkOptionMenu(left, values=list(self.cam_names) or ["-"], variable=self.cam_var,
                          command=lambda v: self.set_camera(self.cam_names.get(v)), height=36,
                          fg_color=CARD, button_color=CARD_HOVER, button_hover_color=BORDER,
                          dropdown_fg_color=CARD, dropdown_hover_color=CARD_HOVER, font=F(13),
                          dropdown_font=F(12), text_color=TXT).pack(fill="x", padx=16)
        ctk.CTkLabel(left, text=tr("DAY"), font=F(11, "bold"), text_color=MUTED).pack(anchor="w", padx=16, pady=(16, 4))
        self.cal = MiniCalendar(left, self.set_day)
        self.cal.pack(padx=16, fill="x")
        ev_head = ctk.CTkFrame(left, fg_color="transparent")
        ev_head.pack(fill="x", padx=16, pady=(16, 4))
        ctk.CTkLabel(ev_head, text=tr("MOTION EVENTS"), font=F(11, "bold"), text_color=MUTED).pack(side="left")
        self.ev_count = ctk.CTkLabel(ev_head, text="", font=F(11), text_color=MUTED)
        self.ev_count.pack(side="right")
        self.ev_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.ev_list.pack(fill="both", expand=True, padx=8)
        button(left, tr("Open folder"), "folder", "secondary", self._open_folder).pack(fill="x", padx=16, pady=14)

        # right area
        right = ctk.CTkFrame(self, corner_radius=0, fg_color=BG)
        right.grid(row=0, column=1, sticky="nsew")
        top = ctk.CTkFrame(right, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(14, 8))
        self.time_lbl = ctk.CTkLabel(top, text="--:--:--", font=F(26, "bold"), text_color=TXT)
        self.time_lbl.pack(side="left")
        self.date_lbl = ctk.CTkLabel(top, text="", font=F(13), text_color=MUTED)
        self.date_lbl.pack(side="left", padx=14, pady=(8, 0))
        self.state_lbl = ctk.CTkLabel(top, text="", font=F(12), text_color=MUTED)
        self.state_lbl.pack(side="right")

        self.video = tk.Canvas(right, bg=TILE_BG, highlightthickness=0, bd=0)
        self.video.pack(fill="both", expand=True, padx=18)
        self.video_img = self.video.create_image(0, 0)
        self.video_txt = self.video.create_text(0, 0, text="", fill=MUTED, font=("Segoe UI", 13))
        self.video.bind("<Double-1>", lambda e: self.toggle_play())

        tlrow = ctk.CTkFrame(right, fg_color="transparent")
        tlrow.pack(fill="x", padx=18, pady=(10, 0))
        self.zoom_var = tk.StringVar(value="24 h")
        segmented(tlrow, list(self.ZOOMS), self._zoom_btn, self.zoom_var, height=28).pack(side="left")
        ctk.CTkLabel(tlrow, text="  " + tr("Click the bar to jump to that time · mouse wheel to zoom"),
                     font=F(11), text_color=MUTED).pack(side="left", padx=8)
        leg = ctk.CTkFrame(tlrow, fg_color="transparent")
        leg.pack(side="right")
        for col, txt in ((ACCENT, tr("Recorded")), (ORANGE, tr("Motion"))):
            ctk.CTkFrame(leg, width=12, height=12, corner_radius=3, fg_color=col).pack(side="left", padx=(10, 4))
            ctk.CTkLabel(leg, text=txt, font=F(11), text_color=MUTED).pack(side="left")
        self.tl = tk.Canvas(right, height=int(70 * app.px), bg=PANEL, highlightthickness=0, bd=0, cursor="hand2")
        self.tl.pack(fill="x", padx=18, pady=(6, 0))
        self.tl.bind("<Configure>", lambda e: self.draw_timeline())
        self.tl.bind("<Button-1>", self._tl_click)
        self.tl.bind("<B1-Motion>", self._tl_drag)
        self.tl.bind("<ButtonRelease-1>", self._tl_release)
        self.tl.bind("<Motion>", self._tl_motion)
        self.tl.bind("<Leave>", lambda e: (setattr(self, "hover_x", None), self.draw_timeline()))
        self.tl.bind("<MouseWheel>", self._tl_wheel)

        ctrl = ctk.CTkFrame(right, fg_color="transparent")
        ctrl.pack(fill="x", padx=18, pady=12)
        button(ctrl, "1 min", "prev", "secondary", lambda: self.jump(-60)).pack(side="left")
        button(ctrl, "10 s", "left", "secondary", lambda: self.jump(-10)).pack(side="left", padx=6)
        self.play_btn = button(ctrl, tr("Play"), "play", "primary", self.toggle_play, width=100)
        self.play_btn.pack(side="left")
        button(ctrl, "10 s", "right", "secondary", lambda: self.jump(10)).pack(side="left", padx=6)
        button(ctrl, "1 min", "next", "secondary", lambda: self.jump(60)).pack(side="left")
        self.speed_var = tk.StringVar(value="1x")
        segmented(ctrl, self.SPEEDS, self._speed, self.speed_var, height=34).pack(side="left", padx=14)
        ctk.CTkLabel(ctrl, text=tr("Go to"), font=F(12), text_color=MUTED).pack(side="left")
        self.goto_var = tk.StringVar()
        ge = entry(ctrl, self.goto_var, width=80)
        ge.pack(side="left", padx=6)
        ge.bind("<Return>", lambda e: self._goto())
        button(ctrl, "", "clock", "secondary", self._goto).pack(side="left")
        self.exp_btn = button(ctrl, tr("Export"), "export", "secondary", self._export_menu)
        self.exp_btn.pack(side="right")
        button(ctrl, tr("Snapshot"), "camera", "secondary", self._snapshot).pack(side="right", padx=6)
        self.audio_btn = button(ctrl, "", "mute", "secondary", self._toggle_audio)
        self.audio_btn.pack(side="right")

        cam_id = cam_id or app.selected or (app.cameras[0]["id"] if app.cameras else None)
        self.after(100, lambda: self.set_camera(cam_id))
        self.after(250, self._bring_front)
        self.after(60, self._poll)
        self.after(30000, self._refresh_today)

    def _toggle_audio(self):
        p = self.player
        if not self.app.audio.available:
            messagebox.showinfo(APP_NAME, tr("No audio output device is available."), parent=self)
            return
        p.audio_on = not p.audio_on
        if p.audio_on:
            self.app.set_listen(None)
            self.app.audio.set_owner("playback")
            if p.speed != 1:
                self.state_lbl.configure(text=tr("Audio plays at 1x speed only"))
                self.sticky_until = time.time() + 4
            if p.cur_t and p.playing:
                p.seek(p.cur_t)
        else:
            p._kill_audio()
            self.app.audio.set_owner(None)
        self.audio_btn.configure(image=icon("volume" if p.audio_on else "mute", 16, TXT))

    def _bring_front(self):
        try:
            if self.state() == "withdrawn":
                self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(300, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except Exception:
            pass

    # ------------------------------------------------------------ data
    def _folder(self):
        cam = self.app.cam(self.cam_id)
        return os.path.join(self.app.settings["rec_dir"], safe_name(cam["name"])) if cam else None

    def set_camera(self, cid):
        cam = self.app.cam(cid)
        if not cam:
            self.video.itemconfigure(self.video_txt, text=tr("No camera"))
            return
        self.cam_id = cid
        self.cam_var.set(cam["name"])
        self.all_segments = list_segments(self._folder(), self.app.settings["segment_min"])
        days = set()
        for s, e, _, _ in self.all_segments:
            d = s.date()
            while d <= e.date():
                days.add(d)
                d += datetime.timedelta(days=1)
        self.cal.set_marked(days)
        day = self.day if self.day in days else (max(days) if days else datetime.date.today())
        self.cal.select(day)
        self.set_day(day)

    def _events_for(self, day):
        folder = self._folder()
        ev = read_events(folder, day) if folder else []
        v = self.app.viewers.get(self.cam_id)
        if v is not None and v.ev_start and day == datetime.date.today():   # motion still going on
            ev.append((datetime.datetime.fromtimestamp(v.ev_start), datetime.datetime.now()))
        return ev

    def set_day(self, day):
        self.day = day
        d0 = datetime.datetime.combine(day, datetime.time())
        d1 = d0 + datetime.timedelta(days=1)
        self.segments = [s for s in self.all_segments if s[1] > d0 and s[0] < d1]
        self.player.set_segments(self.all_segments)
        self.events = self._events_for(day)
        self.date_lbl.configure(text=f"{tr(WEEKDAYS[day.weekday()])} {day.day} {tr(MONTHS[day.month - 1])} {day.year}")
        self._fill_events()
        self.v0, self.v1 = 0.0, 86400.0
        self.zoom_var.set("24 h")
        if not self.segments:
            self.player.playing = False
            self.player.seek(None)
            self.player.cur_t = None
            self.photo = None
            self.video.itemconfigure(self.video_img, image="")
            self.video.itemconfigure(self.video_txt, text=tr("No recordings on this day"))
            self.draw_timeline()
            return
        self.video.itemconfigure(self.video_txt, text="")
        if day == datetime.date.today():
            start = max(self.segments[0][0], self.segments[-1][1] - datetime.timedelta(minutes=5))
        else:
            start = max(self.segments[0][0], d0)
        self.player.playing = True
        self.player.seek(start)
        self.draw_timeline()

    def _refresh_today(self):
        if not self.winfo_exists():
            return
        if self.cam_id and self.day == datetime.date.today():
            self.all_segments = list_segments(self._folder(), self.app.settings["segment_min"])
            d0 = datetime.datetime.combine(self.day, datetime.time())
            self.segments = [s for s in self.all_segments if s[1] > d0]
            self.player.set_segments(self.all_segments)
            self.events = self._events_for(self.day)
            self._fill_events()
            self.draw_timeline()
        self.after(30000, self._refresh_today)

    def _fill_events(self):
        for w in self.ev_list.winfo_children():
            w.destroy()
        self.ev_count.configure(text=str(len(self.events)) if self.events else "")
        if not self.events:
            label(self.ev_list, tr("No motion detected"), size=12).pack(pady=12)
            return
        for s, e in reversed(self.events[-300:]):
            dur = int((e - s).total_seconds())
            txt = f"{s:%H:%M:%S}     {dur // 60} min {dur % 60:02d} s" if dur >= 60 else f"{s:%H:%M:%S}     {dur} s"
            ctk.CTkButton(self.ev_list, text=txt, anchor="w", height=30, font=F(12), fg_color="transparent",
                          hover_color=CARD_HOVER, text_color=TXT, image=icon("motion", 14, ORANGE),
                          command=lambda s=s: self.seek(s - datetime.timedelta(seconds=3))).pack(fill="x", pady=1)

    # ------------------------------------------------------------ commands
    def seek(self, t):
        if t is None or not self.all_segments:
            return
        if t.date() != self.day and self.segments:
            # leaving the day: switch the day in the calendar too
            if any(s[1] > t and s[0] <= t + datetime.timedelta(hours=1) for s in self.all_segments):
                self.day = t.date()
                self.cal.select(self.day)
                d0 = datetime.datetime.combine(self.day, datetime.time())
                self.segments = [s for s in self.all_segments if s[1] > d0 and s[0] < d0 + datetime.timedelta(days=1)]
                self.events = self._events_for(self.day)
                self._fill_events()
                self.date_lbl.configure(text=f"{tr(WEEKDAYS[self.day.weekday()])} {self.day.day} "
                                             f"{tr(MONTHS[self.day.month - 1])} {self.day.year}")
        self.player.seek(t)
        self.draw_timeline()

    def jump(self, sec):
        if self.player.cur_t:
            self.seek(self.player.cur_t + datetime.timedelta(seconds=sec))

    def toggle_play(self):
        p = self.player
        if p.playing:
            p.playing = False
            p._kill_audio()
        else:
            p.playing = True
            if p.cur_t and (p.state == "end" or p.audio_on):
                p.seek(p.cur_t)          # restart (also keeps the audio in sync)

    def _speed(self, v):
        self.player.set_speed(int(v.rstrip("x")))

    def _goto(self):
        txt = self.goto_var.get().strip().replace(".", ":")
        for fmt in ("%H:%M:%S", "%H:%M", "%H"):
            try:
                tm = datetime.datetime.strptime(txt, fmt).time()
                break
            except ValueError:
                tm = None
        if tm is None:
            messagebox.showinfo(APP_NAME, tr("Type a time, for example 14:30"), parent=self)
            return
        t = datetime.datetime.combine(self.day, tm)
        self.player.playing = True
        self.seek(t)
        self._center_view(t)

    def _snapshot(self):
        t = self.player.cur_t
        cam = self.app.cam(self.cam_id)
        seg = next((s for s in self.all_segments if s[0] <= t < s[1]), None) if t and cam else None
        if not seg:
            return
        folder = os.path.join(self._folder(), SNAP_DIR)
        os.makedirs(folder, exist_ok=True)
        out = os.path.join(folder, t.strftime("Snapshot_%Y-%m-%d_%H-%M-%S.jpg"))
        off = (t - seg[0]).total_seconds()

        def work():
            subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{off:.2f}", "-i", seg[2],
                            "-frames:v", "1", "-q:v", "2", out], creationflags=NOWIN, timeout=60)
            def done():
                self.sticky_until = time.time() + 4
                self.state_lbl.configure(text=tr("Snapshot saved: {name}").format(name=os.path.basename(out)))
            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _export_menu(self):
        m = dark_menu(self)
        for label_, sec in (("30 seconds from here", 30), ("1 minute from here", 60), ("5 minutes from here", 300),
                            ("10 minutes from here", 600), ("30 minutes from here", 1800)):
            m.add_command(label="  " + tr("Export") + " " + tr(label_), command=lambda s=sec: self._export(s))
        x, y = self.exp_btn.winfo_rootx(), self.exp_btn.winfo_rooty()
        try:
            m.tk_popup(x, y - 5 * 26)
        finally:
            m.grab_release()

    def _export(self, sec):
        t = self.player.cur_t
        cam = self.app.cam(self.cam_id)
        if not t or not cam:
            return
        folder = os.path.join(self.app.settings["rec_dir"], EXPORT_DIR)
        os.makedirs(folder, exist_ok=True)
        out = os.path.join(folder, f"{safe_name(cam['name'])}_{t:%Y-%m-%d_%H-%M-%S}_{sec}s.mp4")
        self.sticky_until = time.time() + 3600
        self.state_lbl.configure(text=tr("Exporting..."))
        self.exp_btn.configure(state="disabled")

        def work():
            ok, msg = export_clip(self.all_segments, t, sec, out)

            def done():
                if not self.winfo_exists():
                    return
                self.exp_btn.configure(state="normal")
                self.sticky_until = time.time() + 4
                if ok:
                    self.state_lbl.configure(text=tr("Clip exported"))
                    if messagebox.askyesno(APP_NAME, tr("Clip saved:\n{path}\n\nOpen the folder?").format(path=out),
                                           parent=self):
                        os.startfile(folder)
                else:
                    self.state_lbl.configure(text="")
                    messagebox.showerror(APP_NAME, tr("Export failed.\n{err}").format(err=msg), parent=self)
            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()

    def _open_folder(self):
        f = self._folder() or self.app.settings["rec_dir"]
        if os.path.isdir(f):
            os.startfile(f)

    # ------------------------------------------------------------ timeline
    def _sec(self, t):
        return (t - datetime.datetime.combine(self.day, datetime.time())).total_seconds()

    def _x2sec(self, x):
        w = max(1, self.tl.winfo_width())
        return self.v0 + (x / w) * (self.v1 - self.v0)

    def _sec2x(self, s):
        w = max(1, self.tl.winfo_width())
        return (s - self.v0) / (self.v1 - self.v0) * w

    def _set_view(self, center, span):
        span = max(300.0, min(86400.0, span))
        v0 = center - span / 2
        v0 = max(0.0, min(86400.0 - span, v0))
        self.v0, self.v1 = v0, v0 + span
        self.draw_timeline()

    def _center_view(self, t):
        self._set_view(self._sec(t), self.v1 - self.v0)

    def _zoom_btn(self, v):
        c = self._sec(self.player.cur_t) if self.player.cur_t else 43200
        self._set_view(c, self.ZOOMS[v])

    def _tl_wheel(self, e):
        s = self._x2sec(e.x)
        span = (self.v1 - self.v0) * (0.7 if e.delta > 0 else 1.4)
        span = max(300.0, min(86400.0, span))
        frac = e.x / max(1, self.tl.winfo_width())
        v0 = max(0.0, min(86400.0 - span, s - frac * span))
        self.v0, self.v1 = v0, v0 + span
        self.zoom_var.set("")
        self.draw_timeline()

    def _tl_time(self, x):
        return datetime.datetime.combine(self.day, datetime.time()) + datetime.timedelta(
            seconds=max(0.0, min(86399.0, self._x2sec(x))))

    def _tl_click(self, e):
        self.dragging = True
        self.hover_x = e.x
        self.draw_timeline()

    def _tl_drag(self, e):
        self.hover_x = max(0, min(self.tl.winfo_width(), e.x))
        self.draw_timeline()

    def _tl_release(self, e):
        if self.dragging:
            self.dragging = False
            self.seek(self._tl_time(max(0, min(self.tl.winfo_width(), e.x))))

    def _tl_motion(self, e):
        self.hover_x = e.x
        self.draw_timeline()

    def draw_timeline(self):
        c = self.tl
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10:
            return
        px = self.app.px
        c.delete("all")
        top, bot = int(22 * px), h - int(8 * px)
        c.create_rectangle(0, top, w, bot, fill=CARD, outline="")
        d0 = datetime.datetime.combine(self.day, datetime.time())
        for s, e, _, _ in self.segments:
            x0, x1 = self._sec2x(self._sec(max(s, d0))), self._sec2x(self._sec(e))
            if x1 < 0 or x0 > w:
                continue
            c.create_rectangle(max(0, x0), top + int(10 * px), min(w, max(x0 + 1, x1)), bot, fill=ACCENT, outline="")
        for s, e in self.events:
            x0, x1 = self._sec2x(self._sec(s)), self._sec2x(self._sec(e))
            if x1 < 0 or x0 > w:
                continue
            c.create_rectangle(max(0, x0), top, min(w, max(x0 + 2, x1)), top + int(8 * px), fill=ORANGE, outline="")
        span = self.v1 - self.v0
        step = next(st for lim, st in ((900, 60), (2400, 300), (7200, 600), (21600, 1800), (50000, 3600), (1e9, 7200))
                    if span <= lim)
        first = math.ceil(self.v0 / step) * step
        s = first
        while s <= self.v1:
            x = self._sec2x(s)
            hh, mm = int(s // 3600) % 24, int(s % 3600 // 60)
            c.create_line(x, top - int(4 * px), x, top, fill=MUTED)
            c.create_text(x + 3, top - int(12 * px), text=f"{hh:02d}:{mm:02d}" if s < 86400 else "24:00",
                          fill=MUTED, font=("Segoe UI", 9), anchor="w")
            s += step
        if self.player.cur_t and not self.dragging:
            x = self._sec2x(self._sec(self.player.cur_t))
            if 0 <= x <= w:
                c.create_line(x, top - int(4 * px), x, h, fill=RED, width=max(2, int(2 * px)))
                c.create_polygon(x - 6 * px, top - 8 * px, x + 6 * px, top - 8 * px, x, top, fill=RED, outline="")
        if self.hover_x is not None:
            x = self.hover_x
            c.create_line(x, top, x, bot, fill="#ffffff", dash=(3, 3))
            t = self._tl_time(x)
            txt = t.strftime("%H:%M:%S")
            tx = min(max(x, 34 * px), w - 34 * px)
            c.create_rectangle(tx - 32 * px, bot - 20 * px, tx + 32 * px, bot - 2 * px, fill="#000000", outline="")
            c.create_text(tx, bot - 11 * px, text=txt, fill="#ffffff", font=("Segoe UI", 9, "bold"))

    # ------------------------------------------------------------ drawing loop
    def _poll(self):
        if not self.winfo_exists():
            return
        p = self.player
        try:
            with p.lock:
                fid, frame, t = p.frame_id, p.frame, p.cur_t
            if fid != self.last_fid and frame is not None:
                self.last_fid = fid
                w, h = self.video.winfo_width(), self.video.winfo_height()
                if w > 20 and h > 20:
                    self.photo = ImageTk.PhotoImage(Image.fromarray(fit_image(frame, w, h)))
                    self.video.itemconfigure(self.video_img, image=self.photo)
                    self.video.coords(self.video_img, w // 2, h // 2)
            w, h = self.video.winfo_width(), self.video.winfo_height()
            self.video.coords(self.video_txt, w // 2, h // 2)
            if t:
                self.time_lbl.configure(text=t.strftime("%H:%M:%S"))
                if t.date() != self.day:
                    pass
                # follow the cursor when the view is zoomed in
                if self.v1 - self.v0 < 86400 and not self.dragging:
                    s = self._sec(t)
                    if s > self.v1 - (self.v1 - self.v0) * 0.05 or s < self.v0:
                        self._center_view(t)
            states = {"loading": tr("Loading..."), "end": tr("End of recordings"), "pause": tr("Paused"),
                      "play": tr("Playing") + f" · {self.speed_var.get()}"}
            if time.time() > self.sticky_until or p.state == "loading":
                self.state_lbl.configure(text=states.get(p.state, ""))
            playing = p.playing
            self.play_btn.configure(text=tr("Pause") if playing else tr("Play"),
                                    image=icon("pause" if playing else "play", 16, "#ffffff"))
            if fid % 3 == 0:
                self.draw_timeline()
        except Exception:
            log_exception("playback window")
        self.after(60, self._poll)

    def close(self):
        self.player.close()
        if self.app.audio.owner == "playback":
            self.app.audio.set_owner(None)
        self.app.playback_win = None
        self.destroy()
