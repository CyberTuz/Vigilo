"""
Camera, settings, language and LAN discovery dialogs.
"""

import os
import re
import time
import threading
import ipaddress
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog

import customtkinter as ctk

from i18n import tr
from i18n import LANGUAGES
from ..common import (
    APP_NAME, APP_VERSION, DEFAULT_REC_DIR, fmt_gb, fmt_size, KIND_CLOUD, KIND_CUSTOM, KIND_HINT, KIND_LABEL,
    KIND_NATIVE, KIND_RTSP, local_ip, port_open, STARTUP_BAT,
)
from .theme import ACCENT, CARD, CARD_HOVER, draw_app_icon, GREEN, icon, INPUT, MUTED, ORANGE, RED, TXT
from ..cloud import find_cloud_sdk, SDK_HELP
from ..devices import test_camera
from ..archive import estimate_rate
from ..system import set_startup
from .. import hwaccel
from .widgets import button, Dialog, entry, F, label, segmented, switch


# ----------------------------------------------------------------------------- camera dialog

def kind_label(kind):
    return tr(KIND_LABEL[kind])


class CameraDialog(Dialog):
    def __init__(self, parent, cam=None, on_save=None, open_ports=None):
        cam = dict(cam or {})
        super().__init__(parent, tr("Camera"))
        self.on_save = on_save
        self.cam_id = cam.get("id")
        self.presets = cam.get("presets", {})
        self.v = {
            "name": tk.StringVar(value=cam.get("name", "")),
            "ip": tk.StringVar(value=cam.get("ip", "")),
            "port": tk.StringVar(value=str(cam.get("port", 554))),
            "dvrip_port": tk.StringVar(value=str(cam.get("dvrip_port", 34567))),
            "user": tk.StringVar(value=cam.get("user", "admin")),
            "password": tk.StringVar(value=cam.get("password", "")),
            "channel": tk.StringVar(value=str(cam.get("channel", 1))),
            "url_main": tk.StringVar(value=cam.get("url_main", "")),
            "url_sub": tk.StringVar(value=cam.get("url_sub", "")),
            "cloud_id": tk.StringVar(value=cam.get("cloud_id", "")),
        }
        self.kind = cam.get("kind", KIND_RTSP)
        self.record_touched = bool(self.cam_id)
        self.kind_var = tk.StringVar(value=kind_label(self.kind))
        self.record = tk.BooleanVar(value=cam.get("record", True))
        self.ptz = tk.BooleanVar(value=cam.get("ptz", False))
        self.motion = tk.BooleanVar(value=cam.get("motion", True))
        self.show_pw = False

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=20)
        self.heading(body, tr("Edit camera") if self.cam_id else tr("New camera"),
                     tr("Connect a camera on your network (LAN) or in another house (cloud)"), "video")

        if open_ports:
            names = {554: "RTSP", 34567: tr("ICSee native"), 8899: "ONVIF"}
            chips = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
            chips.pack(fill="x", pady=(0, 12))
            ctk.CTkLabel(chips, text="", image=icon("network", 14, MUTED)).pack(side="left", padx=(10, 6), pady=6)
            ctk.CTkLabel(chips, text=tr("Open ports found:") + "  " +
                         "   ".join(f"{p} ({names.get(p, '')})" for p in sorted(open_ports)),
                         font=F(12), text_color=TXT).pack(side="left", pady=6)

        label(body, tr("Name")).pack(anchor="w")
        entry(body, self.v["name"], width=440).pack(anchor="w", pady=(2, 12))

        label(body, tr("Connection type")).pack(anchor="w")
        self.seg = segmented(body, [kind_label(k) for k in KIND_LABEL], self._kind_changed, self.kind_var, height=34)
        self.seg.pack(anchor="w", fill="x", pady=(2, 4))
        self.hint = label(body, "", size=11)
        self.hint.configure(wraplength=440, justify="left")
        self.hint.pack(anchor="w", pady=(0, 10))

        # ICSee fields
        self.xm = ctk.CTkFrame(body, fg_color="transparent")
        self.addr_lbl = label(self.xm, tr("IP address"))
        self.addr_lbl.configure(wraplength=440, justify="left")
        self.addr_lbl.grid(row=0, column=0, columnspan=2, sticky="w")
        self.port_lbl = label(self.xm, tr("Port"))
        self.port_lbl.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.ip_entry = entry(self.xm, self.v["ip"], width=320)
        self.ip_entry.grid(row=1, column=0, sticky="w", pady=(2, 10))
        self.cloud_entry = entry(self.xm, self.v["cloud_id"], width=440)
        self.cloud_entry.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 10))
        self.port_rtsp = entry(self.xm, self.v["port"], width=110)
        self.port_dvrip = entry(self.xm, self.v["dvrip_port"], width=110)
        self.port_rtsp.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(2, 10))
        self.port_dvrip.grid(row=1, column=1, sticky="w", padx=(10, 0), pady=(2, 10))
        label(self.xm, tr("User")).grid(row=2, column=0, sticky="w")
        label(self.xm, tr("Channel")).grid(row=2, column=1, sticky="w", padx=(10, 0))
        entry(self.xm, self.v["user"], width=320).grid(row=3, column=0, sticky="w", pady=(2, 10))
        entry(self.xm, self.v["channel"], width=110).grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(2, 10))
        label(self.xm, tr("Password (the one set in the ICSee app, empty if never set)")).grid(row=4, column=0, columnspan=2, sticky="w")
        pw = ctk.CTkFrame(self.xm, fg_color="transparent")
        pw.grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 4))
        self.pw_entry = entry(pw, self.v["password"], width=394, show="•")
        self.pw_entry.pack(side="left")
        button(pw, "", "eye", "secondary", self._toggle_pw, width=36).pack(side="left", padx=(10, 0))
        self.sdk_box = ctk.CTkFrame(self.xm, fg_color=CARD, corner_radius=8)
        self.sdk_box.grid(row=6, column=0, columnspan=2, sticky="we", pady=(10, 0))
        self.sdk_icon = ctk.CTkLabel(self.sdk_box, text="", width=20)
        self.sdk_icon.pack(side="left", padx=(10, 6), pady=8, anchor="n")
        self.sdk_txt = ctk.CTkLabel(self.sdk_box, text="", font=F(11), text_color=TXT, justify="left",
                                    anchor="w", wraplength=390)
        self.sdk_txt.pack(side="left", fill="x", expand=True, pady=8, padx=(0, 10))

        # custom URL fields
        self.cu = ctk.CTkFrame(body, fg_color="transparent")
        label(self.cu, tr("Main URL (recording)")).pack(anchor="w")
        entry(self.cu, self.v["url_main"], width=440).pack(anchor="w", pady=(2, 10))
        label(self.cu, tr("Secondary URL (preview, optional)")).pack(anchor="w")
        entry(self.cu, self.v["url_sub"], width=440).pack(anchor="w", pady=(2, 4))

        self.fields_anchor = ctk.CTkFrame(body, fg_color="transparent", height=1)
        self.fields_anchor.pack(fill="x")

        sw = ctk.CTkFrame(body, fg_color="transparent")
        sw.pack(fill="x", pady=(12, 4))
        rec_sw = switch(sw, tr("Record this camera"), self.record)
        rec_sw.grid(row=0, column=0, sticky="w", pady=3)
        rec_sw.configure(command=lambda: setattr(self, "record_touched", True))
        switch(sw, tr("Detect motion"), self.motion).grid(row=0, column=1, sticky="w", padx=(24, 0), pady=3)
        self.ptz_sw = switch(sw, tr("Motorized (pan/tilt)"), self.ptz)
        self.ptz_sw.grid(row=1, column=0, columnspan=2, sticky="w", pady=3)

        self.result = ctk.CTkFrame(body, fg_color=CARD, corner_radius=8)
        self.result_icon = ctk.CTkLabel(self.result, text="", width=20)
        self.result_icon.pack(side="left", padx=(12, 8), pady=10)
        self.result_txt = ctk.CTkLabel(self.result, text="", font=F(12), text_color=TXT, justify="left",
                                       anchor="w", wraplength=380)
        self.result_txt.pack(side="left", fill="x", expand=True, pady=10, padx=(0, 12))

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill="x", side="bottom", pady=(14, 0))
        self.test_btn = button(btns, tr("Test connection"), "plug", "secondary", self._test)
        self.test_btn.pack(side="left")
        button(btns, tr("Save"), "check", "primary", self._save, width=110).pack(side="right")
        button(btns, tr("Cancel"), None, "ghost", self.destroy, width=90).pack(side="right", padx=8)

        self._kind_changed()

    def _kind_changed(self, *_):
        lbl = self.kind_var.get()
        self.kind = next((k for k in KIND_LABEL if kind_label(k) == lbl), KIND_RTSP)
        self.hint.configure(text=tr(KIND_HINT[self.kind]))
        self.xm.pack_forget()
        self.cu.pack_forget()
        if self.kind == KIND_CUSTOM:
            self.cu.pack(fill="x", before=self.fields_anchor)
            self.ptz_sw.configure(state="disabled")
            self.ptz.set(False)
        else:
            self.ptz_sw.configure(state="normal")
            self.xm.pack(fill="x", before=self.fields_anchor)
            cloud = self.kind == KIND_CLOUD
            self.addr_lbl.configure(text=tr("Serial number (Cloud ID): in the ICSee app, camera settings "
                                            "> Device info") if cloud else tr("IP address"))
            for w in (self.ip_entry, self.port_lbl, self.port_rtsp, self.port_dvrip):
                w.grid_remove()
            if cloud:
                self.cloud_entry.grid()
                self._sdk_status()
                self.sdk_box.grid()
                if not self.record_touched:
                    self.record.set(False)   # cloud: recording 24/7 uses the other house's internet line
            else:
                self.cloud_entry.grid_remove()
                self.sdk_box.grid_remove()
                self.ip_entry.grid()
                self.port_lbl.grid()
                (self.port_dvrip if self.kind == KIND_NATIVE else self.port_rtsp).grid()
                if not self.record_touched:
                    self.record.set(True)

    def _sdk_status(self):
        sdk = find_cloud_sdk(refresh=True)
        if sdk:
            self.sdk_icon.configure(image=icon("check", 14, GREEN))
            self.sdk_txt.configure(text=tr("SDK library found:") + f"\n{sdk}\n"
                                   + tr("Video goes through the ICSee cloud servers: it can take a few seconds."))
        else:
            self.sdk_icon.configure(image=icon("warning", 14, ORANGE))
            self.sdk_txt.configure(text=tr(SDK_HELP))

    def _toggle_pw(self):
        self.show_pw = not self.show_pw
        self.pw_entry.configure(show="" if self.show_pw else "•")

    def _collect(self):
        d = {k: v.get().strip() for k, v in self.v.items()}
        d["password"] = self.v["password"].get()  # the password may contain spaces
        d["kind"] = self.kind
        try:
            d["port"] = int(d["port"] or 554)
            d["dvrip_port"] = int(d["dvrip_port"] or 34567)
            d["channel"] = int(d["channel"] or 1)
        except ValueError:
            raise ValueError(tr("Port and channel must be numbers."))
        d["cloud_id"] = re.sub(r"\s+", "", d["cloud_id"])
        if not d["name"]:
            d["name"] = (d["cloud_id"] if d["kind"] == KIND_CLOUD else d["ip"]) or tr("Camera")
        if d["kind"] == KIND_CLOUD and not d["cloud_id"]:
            raise ValueError(tr("Enter the camera serial number (Cloud ID)."))
        if d["kind"] not in (KIND_CUSTOM, KIND_CLOUD) and not d["ip"]:
            raise ValueError(tr("Enter the IP address."))
        if d["kind"] == KIND_CUSTOM and not d["url_main"]:
            raise ValueError(tr("Enter the RTSP URL."))
        d["record"] = self.record.get()
        d["ptz"] = self.ptz.get()
        d["motion"] = self.motion.get()
        d["presets"] = self.presets
        if self.cam_id:
            d["id"] = self.cam_id
        return d

    def _show_result(self, state, text):
        colors = {"ok": GREEN, "err": RED, "wait": MUTED}
        names = {"ok": "check", "err": "warning", "wait": "refresh"}
        self.result_icon.configure(image=icon(names[state], 16, colors[state]))
        self.result_txt.configure(text=text)
        if not self.result.winfo_ismapped():
            self.result.pack(fill="x", pady=(6, 0), before=self.test_btn.master)

    def _test(self):
        try:
            cam = self._collect()
        except ValueError as e:
            messagebox.showerror(APP_NAME, str(e), parent=self)
            return
        self._show_result("wait", tr("Connecting through the ICSee cloud (it can take up to a minute)...")
                          if cam["kind"] == KIND_CLOUD else tr("Trying to connect..."))
        self.test_btn.configure(state="disabled")

        def work():
            ok, msg, auth, extra = test_camera(cam)
            switched = None
            if not ok and not auth and cam["kind"] in (KIND_RTSP, KIND_NATIVE):
                other = KIND_NATIVE if cam["kind"] == KIND_RTSP else KIND_RTSP
                ok2, msg2, auth2, extra2 = test_camera(dict(cam, kind=other))
                if ok2:
                    switched, msg, extra = other, msg2, extra2
                    ok = True
                elif auth2:
                    msg, auth = msg2, True
            self.after(0, lambda: self._test_done(ok, msg, auth, switched, extra))

        threading.Thread(target=work, daemon=True).start()

    def _test_done(self, ok, msg, auth, switched, extra):
        if not self.winfo_exists():
            return
        self.test_btn.configure(state="normal")
        if ok and extra.get("ptz") is not None:
            self.ptz.set(bool(extra["ptz"]))
            msg += (" · " + tr("motorized")) if extra["ptz"] else ""
        if ok and extra.get("audio"):
            msg += " · " + tr("audio")
        if ok and switched:
            self.kind_var.set(kind_label(switched))
            self._kind_changed()
            self._show_result("ok", tr("It works with \"{kind}\" (selected for you).").format(kind=kind_label(switched))
                              + f"\n{msg}")
        elif ok:
            self._show_result("ok", tr("It works!") + f"  {msg}")
        elif auth:
            self._show_result("err", f"{msg}.\n" + tr("Check the password (the one set in the ICSee app)."))
        elif self.kind == KIND_CLOUD:
            self._show_result("err", f"{msg}.\n" + tr("Check the serial number and that the camera is online "
                                                     "in the ICSee app."))
        else:
            self._show_result("err", f"{msg}.\n" + tr("Check the IP address and that the camera is on."))

    def _save(self):
        try:
            cam = self._collect()
        except ValueError as e:
            messagebox.showerror(APP_NAME, str(e), parent=self)
            return
        if self.on_save:
            self.on_save(cam)
        self.destroy()


# ----------------------------------------------------------------------------- settings

class SettingsDialog(Dialog):
    SEGMENTS = ["5 min", "10 min", "15 min", "30 min"]
    SENS = ("low", "medium", "high")
    SENS_LABEL = {"low": "Low", "medium": "Medium", "high": "High"}
    MODES = ("continuous", "motion")
    MODE_LABEL = {"continuous": "Continuous", "motion": "Only on motion"}

    def __init__(self, app):
        super().__init__(app.root, tr("Settings"))
        self.app = app
        s = app.settings
        self.rec_dir = tk.StringVar(value=s["rec_dir"])
        seg = f"{int(s['segment_min'])} min"
        self.segment = tk.StringVar(value=seg if seg in self.SEGMENTS else "10 min")
        self.keep = tk.StringVar(value=f"{s['keep_days']:g}")
        self.free = tk.StringVar(value=f"{s['min_free_gb']:g}")
        self.maxrec = tk.StringVar(value=f"{s.get('max_rec_gb', 0):g}")
        self.post = tk.StringVar(value=f"{s.get('motion_post_min', 2):g}")
        self.autorec = tk.BooleanVar(value=s["autorec"])
        self.audio = tk.BooleanVar(value=s.get("audio", True))
        self.startup = tk.BooleanVar(value=os.path.exists(STARTUP_BAT))
        self.tray_close = tk.BooleanVar(value=s.get("tray_on_close", True))
        self.keep_awake = tk.BooleanVar(value=s.get("keep_awake", True))
        self.hw = tk.StringVar(value=tr("Off") if s.get("hw_decode", "auto") == "off" else tr("Automatic"))
        self.sens = tk.StringVar(value=tr(self.SENS_LABEL.get(s.get("motion_sens", "medium"), "Medium")))
        self.mode = tk.StringVar(value=tr(self.MODE_LABEL.get(s.get("rec_mode", "continuous"), "Continuous")))
        self.lang = tk.StringVar(value=LANGUAGES.get(s.get("lang", "en"), "English"))
        self.rate = None

        body = ctk.CTkScrollableFrame(self, fg_color="transparent", width=560, height=640)
        body.pack(fill="both", expand=True, padx=14, pady=14)
        self.heading(body, tr("Settings"), tr("Language, recording, overwrite, motion and startup"), "settings")

        def section(title, icon_name):
            card = ctk.CTkFrame(body, fg_color=CARD, corner_radius=10)
            card.pack(fill="x", pady=(0, 10))
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(12, 6))
            ctk.CTkLabel(row, text="", image=icon(icon_name, 16, ACCENT)).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(row, text=title, font=F(14, "bold"), text_color=TXT).pack(side="left")
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=14, pady=(0, 12))
            return inner

        def num_row(parent, text, var, unit):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", pady=3)
            label(r, text, muted=False, size=13).pack(side="left")
            label(r, unit, size=12).pack(side="right", padx=(6, 0))
            entry(r, var, width=70).pack(side="right")
            return r

        gen = section(tr("Language"), "globe")
        r = ctk.CTkFrame(gen, fg_color="transparent")
        r.pack(fill="x", pady=3)
        label(r, tr("Program language"), muted=False, size=13).pack(side="left")
        segmented(r, list(LANGUAGES.values()), None, self.lang).pack(side="right")

        rec = section(tr("Recording"), "record")
        label(rec, tr("Recordings folder")).pack(anchor="w")
        d = ctk.CTkFrame(rec, fg_color="transparent")
        d.pack(fill="x", pady=(2, 8))
        entry(d, self.rec_dir, width=380).pack(side="left")
        button(d, tr("Browse"), "folder", "secondary", self._browse).pack(side="left", padx=(8, 0))
        r = ctk.CTkFrame(rec, fg_color="transparent")
        r.pack(fill="x", pady=3)
        label(r, tr("Recording mode"), muted=False, size=13).pack(side="left")
        segmented(r, [tr(self.MODE_LABEL[m]) for m in self.MODES], lambda v: self._mode_changed(),
                  self.mode).pack(side="right")
        self.post_row = num_row(rec, tr("Keep recording after the last motion for"), self.post, tr("minutes"))
        self.mode_hint = label(rec, "", size=11)
        self.mode_hint.configure(wraplength=500, justify="left")
        self.mode_hint.pack(anchor="w", pady=(2, 6))
        self.seg_row = ctk.CTkFrame(rec, fg_color="transparent")
        self.seg_row.pack(fill="x", pady=3)
        label(self.seg_row, tr("Length of each file"), muted=False, size=13).pack(side="left")
        segmented(self.seg_row, self.SEGMENTS, lambda v: self._update_estimate(), self.segment).pack(side="right")
        self.est = label(rec, "", size=11)
        self.est.pack(anchor="w", pady=(2, 4))
        switch(rec, tr("Record audio too (when the camera has a microphone)"), self.audio).pack(anchor="w", pady=4)

        cl = section(tr("Automatic overwrite"), "refresh")
        label(cl, tr("When a limit is reached, the oldest recordings are deleted to make room\n"
                     "for new ones. Set 0 to disable a limit."), size=11).pack(anchor="w", pady=(0, 6))
        num_row(cl, tr("Maximum space for recordings"), self.maxrec, "GB")
        num_row(cl, tr("Keep recordings for"), self.keep, tr("days"))
        num_row(cl, tr("Always leave free on the disk at least"), self.free, "GB")
        self.days_est = label(cl, "", size=11)
        self.days_est.pack(anchor="w", pady=(4, 0))

        mv = section(tr("Motion detection"), "motion")
        r = ctk.CTkFrame(mv, fg_color="transparent")
        r.pack(fill="x", pady=3)
        label(r, tr("Sensitivity"), muted=False, size=13).pack(side="left")
        segmented(r, [tr(self.SENS_LABEL[k]) for k in self.SENS], None, self.sens).pack(side="right")
        label(mv, tr("Motion is marked in orange on the playback timeline."), size=11).pack(anchor="w", pady=(4, 0))

        pf = section(tr("Performance"), "video")
        r = ctk.CTkFrame(pf, fg_color="transparent")
        r.pack(fill="x", pady=3)
        label(r, tr("Video decoding on the graphics card (GPU)"), muted=False, size=13).pack(side="left")
        segmented(r, [tr("Automatic"), tr("Off")], None, self.hw).pack(side="right")
        self.gpu_lbl = label(pf, tr("Checking the graphics card..."), size=11)
        self.gpu_lbl.configure(wraplength=500, justify="left")
        self.gpu_lbl.pack(anchor="w", pady=(4, 0))
        threading.Thread(target=self._check_gpu, daemon=True).start()

        st = section(tr("Startup and background"), "window")
        switch(st, tr("Start the program when the PC starts"), self.startup).pack(anchor="w", pady=4)
        switch(st, tr("Resume recording automatically at startup"), self.autorec).pack(anchor="w", pady=4)
        switch(st, tr("Keep running in the notification area when the window is closed"),
               self.tray_close).pack(anchor="w", pady=4)
        switch(st, tr("Keep the PC awake while recording (the screen can still turn off)"),
               self.keep_awake).pack(anchor="w", pady=4)

        b = ctk.CTkFrame(self, fg_color="transparent")
        b.pack(fill="x", padx=24, pady=(0, 16))
        label(b, f"{APP_NAME} {APP_VERSION}", size=11).pack(side="left")
        button(b, tr("Save"), "check", "primary", self._save, width=110).pack(side="right")
        button(b, tr("Cancel"), None, "ghost", self.destroy, width=90).pack(side="right", padx=8)

        for var in (self.maxrec,):
            var.trace_add("write", lambda *a: self._update_estimate())
        threading.Thread(target=self._calc_rate, daemon=True).start()
        self._mode_changed()

    def _mode_key(self):
        return next((m for m in self.MODES if tr(self.MODE_LABEL[m]) == self.mode.get()), "continuous")

    def _mode_changed(self):
        motion = self._mode_key() == "motion"
        if motion:
            self.post_row.pack(fill="x", pady=3, before=self.mode_hint)
            self.mode_hint.configure(text=tr(
                "Recording starts a few seconds before the motion and continues for the minutes set "
                "above. In this mode files are 1 minute long. Cameras with motion detection turned "
                "off keep recording continuously."))
            self.seg_row.pack_forget()
        else:
            self.post_row.pack_forget()
            self.mode_hint.configure(text=tr("Records all the time."))
            self.seg_row.pack(fill="x", pady=3, before=self.est)
        self._update_estimate()

    def _check_gpu(self):
        p = hwaccel.probe()
        name = hwaccel.gpu_name() or tr("Graphics card")
        viewers = list(getattr(self.app, "viewers", {}).values())
        running = [v for v in viewers if v.decoder]
        if any(p.values()):
            txt = (f"{name} · H.264 {'✓' if p['h264'] else '✗'} · H.265 {'✓' if p['hevc'] else '✗'}\n"
                   + tr("Much less CPU for high-resolution video (enlarged view, playback, cameras "
                        "without a secondary stream). When a stream does not decode on the GPU, the CPU "
                        "takes over by itself."))
            if running:
                txt += "\n" + tr("Now: {gpu} of {n} cameras decoded on the GPU.").format(
                    gpu=sum(1 for v in running if v.decoder == "gpu"), n=len(running))
        else:
            txt = tr("This PC cannot decode video on the graphics card: the CPU does it.")

        def show():
            if self.winfo_exists():
                self.gpu_lbl.configure(text=txt)
        try:
            self.after(0, show)
        except Exception:
            pass

    def _calc_rate(self):
        self.rate = estimate_rate(self.app.settings["rec_dir"], self.app.settings["segment_min"])
        try:
            self.after(0, self._update_estimate)
        except Exception:
            pass

    def _update_estimate(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        mins = 1 if self._mode_key() == "motion" else int(self.segment.get().split()[0])
        n = max(1, len(self.app.cameras))
        if self.rate:
            self.est.configure(text=tr("Each file will be about {size} per camera (measured on your recordings).")
                               .format(size=fmt_size(self.rate * mins * 60)))
            try:
                cap = float(self.maxrec.get().replace(",", ".")) * 1024**3
            except ValueError:
                cap = 0
            if cap > 0:
                days = cap / (self.rate * n * 86400)
                self.days_est.configure(text=tr("With {n} camera(s) the maximum space is enough for about "
                                                "{days} days of continuous recording.")
                                        .format(n=n, days=f"{days:.1f}"))
            else:
                self.days_est.configure(text=tr("{n} camera(s) use about {size} per day of continuous recording.")
                                        .format(n=n, size=fmt_gb(self.rate * n * 86400)))
        else:
            self.est.configure(text="" if self._mode_key() == "motion"
                               else tr("Shorter files = smaller files, easier to copy."))
            self.days_est.configure(text="")

    def _browse(self):
        d = filedialog.askdirectory(parent=self, initialdir=self.rec_dir.get())
        if d:
            self.rec_dir.set(os.path.normpath(d))

    def _save(self):
        try:
            seg = int(self.segment.get().split()[0])
            keep = max(0.0, float(self.keep.get().replace(",", ".")))
            free = max(0.0, float(self.free.get().replace(",", ".")))
            maxrec = max(0.0, float(self.maxrec.get().replace(",", ".")))
            post = min(60.0, max(0.5, float(self.post.get().replace(",", "."))))
        except ValueError:
            messagebox.showerror(APP_NAME, tr("Check the numbers you entered."), parent=self)
            return
        sens = next((k for k in self.SENS if tr(self.SENS_LABEL[k]) == self.sens.get()), "medium")
        lang = next((k for k, v in LANGUAGES.items() if v == self.lang.get()), "en")
        mode = self._mode_key()
        new = {"rec_dir": self.rec_dir.get().strip() or DEFAULT_REC_DIR, "segment_min": seg,
               "keep_days": keep, "min_free_gb": free, "max_rec_gb": maxrec, "autorec": self.autorec.get(),
               "audio": self.audio.get(), "motion_sens": sens, "rec_mode": mode, "motion_post_min": post,
               "lang": lang, "tray_on_close": self.tray_close.get(), "keep_awake": self.keep_awake.get(),
               "hw_decode": "off" if self.hw.get() == tr("Off") else "auto"}
        if mode == "motion" and self.app.settings.get("rec_mode") != "motion":
            new["motion_mode_since"] = time.time()
        set_startup(self.startup.get())
        self.destroy()
        self.app.apply_settings(new)


class LanguageDialog(Dialog):
    """First start: choose the program language."""

    def __init__(self, root, on_done):
        super().__init__(root, "Vigilo")
        self.on_done = on_done
        self.protocol("WM_DELETE_WINDOW", lambda: self._pick("en"))
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=34, pady=28)
        logo = draw_app_icon(96)
        ctk.CTkLabel(body, text="", image=ctk.CTkImage(logo, logo, size=(56, 56))).pack(pady=(0, 10))
        ctk.CTkLabel(body, text="Welcome to Vigilo · Benvenuto in Vigilo", font=F(17, "bold"),
                     text_color=TXT).pack()
        ctk.CTkLabel(body, text="Choose the language · Scegli la lingua", font=F(12),
                     text_color=MUTED).pack(pady=(4, 18))
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack()
        button(row, "English", "globe", "primary", lambda: self._pick("en"), width=150, height=42).pack(side="left", padx=6)
        button(row, "Italiano", "globe", "primary", lambda: self._pick("it"), width=150, height=42).pack(side="left", padx=6)
        ctk.CTkLabel(body, text="You can change it later in Settings · Si può cambiare poi nelle Impostazioni",
                     font=F(11), text_color=MUTED).pack(pady=(18, 0))

    def _pick(self, lang):
        self.destroy()
        self.on_done(lang)


# ----------------------------------------------------------------------------- LAN discovery

class ScanDialog(Dialog):
    PORTS = (554, 34567, 8899)

    def __init__(self, app):
        super().__init__(app.root, tr("Find cameras"), modal=False, resizable=True)
        self.app = app
        self.geometry("640x560")
        net = ipaddress.ip_network(local_ip() + "/24", strict=False)
        self.net = tk.StringVar(value=str(net))
        self.rows = {}

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=22, pady=18)
        self.heading(body, tr("Find cameras"), tr("Find the cameras connected to your network"), "search")

        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x")
        label(top, tr("Network"), size=13).pack(side="left", padx=(0, 8))
        entry(top, self.net, width=180).pack(side="left")
        self.btn = button(top, tr("Search"), "search", "primary", self._scan, width=110)
        self.btn.pack(side="left", padx=10)
        self.count = label(top, "", size=12)
        self.count.pack(side="right")

        self.prog = ctk.CTkProgressBar(body, height=6, progress_color=ACCENT, fg_color=CARD)
        self.prog.pack(fill="x", pady=(12, 10))
        self.prog.set(0)

        self.list = ctk.CTkScrollableFrame(body, fg_color="transparent")
        self.list.pack(fill="both", expand=True)
        self.empty = label(self.list, "", size=13)
        self.empty.pack(pady=30)
        self.after(300, self._scan)

    def _scan(self):
        try:
            net = ipaddress.ip_network(self.net.get().strip(), strict=False)
        except ValueError:
            messagebox.showerror(APP_NAME, tr("Invalid network (e.g. 192.168.1.0/24)"), parent=self)
            return
        hosts = list(net.hosts())[:1024]
        for r in self.rows.values():
            r.destroy()
        self.rows.clear()
        self.empty.configure(text=tr("Searching..."))
        self.empty.pack(pady=30)
        self.btn.configure(state="disabled")
        self.prog.set(0)
        total = len(hosts)
        done = [0]

        def probe(h):
            h = str(h)
            return h, [p for p in self.PORTS if port_open(h, p, 0.6)]

        def progress():
            done[0] += 1
            if self.winfo_exists():
                self.prog.set(done[0] / total)
                self.count.configure(text=tr("{done}/{total} addresses").format(done=done[0], total=total))

        def work():
            with ThreadPoolExecutor(max_workers=96) as ex:
                for h, ports in ex.map(probe, hosts):
                    self.after(0, progress)
                    if 554 in ports or 34567 in ports:
                        self.after(0, lambda h=h, p=ports: self._add_row(h, p))
            self.after(0, self._done)

        threading.Thread(target=work, daemon=True).start()

    def _done(self):
        if not self.winfo_exists():
            return
        self.btn.configure(state="normal")
        n = len(self.rows)
        self.count.configure(text=tr("None found") if n == 0 else tr("1 camera found") if n == 1
                             else tr("{n} cameras found").format(n=n))
        if not n:
            self.empty.configure(text=tr("No camera found.\nCheck that the PC is on the same network."))

    def _add_row(self, ip, ports):
        if not self.winfo_exists():
            return
        self.empty.pack_forget()
        known = next((c for c in self.app.cameras if c.get("ip") == ip), None)
        row = ctk.CTkFrame(self.list, fg_color=CARD, corner_radius=10)
        row.pack(fill="x", pady=4, padx=2)
        ctk.CTkLabel(row, text="", image=icon("video", 20, ACCENT), width=40, height=40,
                     fg_color=INPUT, corner_radius=10).pack(side="left", padx=12, pady=10)
        col = ctk.CTkFrame(row, fg_color="transparent")
        col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(col, text=ip, font=F(14, "bold"), text_color=TXT, anchor="w").pack(anchor="w")
        if 554 in ports:
            desc = tr("ICSee/XMeye with RTSP") if 34567 in ports else tr("RTSP camera")
        else:
            desc = tr("ICSee/XMeye (native protocol only)")
        chips = ctk.CTkFrame(col, fg_color="transparent")
        chips.pack(anchor="w", pady=(2, 0))
        ctk.CTkLabel(chips, text=desc, font=F(11), text_color=MUTED).pack(side="left", padx=(0, 8))
        for p in ports:
            ctk.CTkLabel(chips, text=str(p), font=F(10, "bold"), text_color=TXT, fg_color=CARD_HOVER,
                         corner_radius=6, height=18, width=44).pack(side="left", padx=2)
        if known:
            b = button(row, tr("Already added"), "check", "secondary", None)
            b.configure(state="disabled")
        else:
            b = button(row, tr("Add"), "add", "primary", lambda: self._add(ip, ports, row))
        b.pack(side="right", padx=12)
        self.rows[ip] = row

    def _add(self, ip, ports, row):
        kind = KIND_RTSP if 554 in ports else KIND_NATIVE
        n = len(self.app.cameras) + 1

        def saved(cam):
            self.app.add_camera(cam)
            for w in row.winfo_children():
                if isinstance(w, ctk.CTkButton):
                    w.configure(text=tr("Added"), state="disabled", image=icon("check", 16, TXT))

        CameraDialog(self, {"name": tr("Camera {n}").format(n=n), "ip": ip, "kind": kind}, on_save=saved,
                     open_ports=ports)
