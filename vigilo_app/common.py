"""
Constants, configuration file, paths and small helpers shared by the whole program.
"""

import os
import sys
import json
import socket
import shutil
import subprocess
import datetime

import cv2
import imageio_ffmpeg

from i18n import tr


APP_NAME = "Vigilo"
APP_VERSION = "1.1.0"
FROZEN = getattr(sys, "frozen", False)
# folder of Vigilo.exe, or of vigilo.py when running from source
ROOT_DIR = (os.path.dirname(sys.executable) if FROZEN
            else os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENTRY_SCRIPT = os.path.join(ROOT_DIR, "vigilo.py")   # starts helper processes from source
_APPDATA = os.environ.get("APPDATA", os.path.expanduser("~"))
CONFIG_DIR = (os.environ.get("VIGILO_CONFIG_DIR") or os.environ.get("TELECAMERE_CONFIG_DIR")
              or os.path.join(_APPDATA, "Vigilo"))
LEGACY_CONFIG_DIR = os.path.join(_APPDATA, "TelecamereCasa")   # name used by early versions
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
APP_ICO = os.path.join(CONFIG_DIR, "app.ico")
DEFAULT_REC_DIR = os.path.join(os.path.expanduser("~"), "Videos", "Vigilo")
NOWIN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
STARTUP_DIR = os.path.join(_APPDATA, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
STARTUP_BAT = os.path.join(STARTUP_DIR, "Vigilo.bat")
LEGACY_STARTUP_BAT = os.path.join(STARTUP_DIR, "TelecamereCasa.bat")
# Sub-folders inside each camera folder (the Italian names are from early versions)
SNAP_DIR, EVENTS_DIR, EXPORT_DIR = "Snapshots", "events", "Exports"
LEGACY_EVENTS_DIR = "eventi"
SKIP_DIRS = {SNAP_DIR, EVENTS_DIR, EXPORT_DIR, "Foto", "eventi", "Esportati"}

DEFAULT_SETTINGS = {
    "rec_dir": DEFAULT_REC_DIR,
    "segment_min": 10,      # length of each recorded file (small, handy files)
    "keep_days": 14,        # delete recordings older than N days (0 = never)
    "min_free_gb": 20,      # when free space drops below this, delete the oldest
    "max_rec_gb": 0,        # maximum space for recordings (0 = no limit)
    "autorec": True,        # resume recording at startup
    "audio": True,          # also record audio when the camera has it
    "rec_mode": "continuous",  # continuous | motion (keep only what is around motion)
    "motion_post_min": 2,   # motion mode: keep this many minutes after the last motion
    "motion_pre_sec": 10,   # motion mode: keep this many seconds before the motion
    "motion_mode_since": 0,  # timestamp when motion mode was turned on (older files are never pruned)
    "motion_sens": "medium",  # motion detection sensitivity
    "layout": "auto",       # auto | focus
    "tray_on_close": True,  # closing the window keeps Vigilo running in the notification area
    "keep_awake": True,     # keep the PC awake while recording
    "hw_decode": "auto",    # live view / playback decoding on the GPU: auto | off
}

# Connection types (the stored values are kept for compatibility)
KIND_RTSP = "xmeye"     # ICSee/XMeye via RTSP (port 554)
KIND_NATIVE = "dvrip"   # ICSee/XMeye via the native protocol (port 34567)
KIND_CUSTOM = "custom"  # any rtsp:// URL
KIND_CLOUD = "cloud"    # ICSee/XMeye via the cloud (serial number), also from another house
KIND_LABEL = {KIND_RTSP: "ICSee · RTSP", KIND_NATIVE: "ICSee · Native", KIND_CLOUD: "ICSee · Cloud",
              KIND_CUSTOM: "Other RTSP"}
KIND_SHORT = {KIND_RTSP: "RTSP", KIND_NATIVE: "Native", KIND_CLOUD: "Cloud", KIND_CUSTOM: "RTSP"}
KIND_HINT = {
    KIND_RTSP: "Standard RTSP stream (port 554). The lightest connection.",
    KIND_NATIVE: "The ICSee app protocol (port 34567). Use it when port 554 is closed.",
    KIND_CLOUD: "Through the ICSee cloud with the serial number: works for cameras in another "
                "house too. Experimental: needs NetSdk.dll (see the README).",
    KIND_CUSTOM: "Any camera with an rtsp:// address (Hikvision, Dahua, Reolink...).",
}
STREAM_KINDS = (KIND_NATIVE, KIND_CLOUD)   # raw video that we decode ourselves with ffmpeg
MOTION_SENS = {"low": 0.035, "medium": 0.012, "high": 0.004}
_LEGACY_SENS = {"bassa": "low", "media": "medium", "alta": "high"}
PTZ_DIRS = ["DirectionRight", "DirectionRightUp", "DirectionUp", "DirectionLeftUp",
            "DirectionLeft", "DirectionLeftDown", "DirectionDown", "DirectionRightDown"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ----------------------------------------------------------------------------- configuration

def _migrate_legacy_config():
    """First start after the rename: copy the configuration of the early versions."""
    old = os.path.join(LEGACY_CONFIG_DIR, "config.json")
    if os.path.exists(CONFIG_FILE) or not os.path.exists(old) or os.environ.get("VIGILO_CONFIG_DIR"):
        return
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        shutil.copy2(old, CONFIG_FILE)
        if os.path.isdir(os.path.join(LEGACY_CONFIG_DIR, "sdk")):
            shutil.copytree(os.path.join(LEGACY_CONFIG_DIR, "sdk"), os.path.join(CONFIG_DIR, "sdk"),
                            dirs_exist_ok=True)
    except OSError:
        pass


def load_config():
    _migrate_legacy_config()
    cfg = {"settings": dict(DEFAULT_SETTINGS), "cameras": []}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        saved = data.get("settings", {})
        if "rec_dir" not in saved and data.get("cameras"):
            saved["rec_dir"] = os.path.join(os.path.expanduser("~"), "Videos", "Telecamere")
        cfg["settings"].update(saved)
        cfg["cameras"] = data.get("cameras", [])
    except FileNotFoundError:
        pass
    except Exception as e:
        from tkinter import messagebox
        messagebox.showwarning(APP_NAME, tr("The configuration cannot be read, a new one will be created.\n{err}")
                               .format(err=e))
    s = cfg["settings"]
    s["motion_sens"] = _LEGACY_SENS.get(s.get("motion_sens"), s.get("motion_sens"))
    if s["motion_sens"] not in MOTION_SENS:
        s["motion_sens"] = "medium"
    for c in cfg["cameras"]:
        c.setdefault("kind", KIND_RTSP)
        c.setdefault("port", 554)
        c.setdefault("dvrip_port", 34567)
        c.setdefault("user", "admin")
        c.setdefault("password", "")
        c.setdefault("channel", 1)
        c.setdefault("ptz", False)
        c.setdefault("motion", True)
        c.setdefault("presets", {})
        c.setdefault("cloud_id", "")
    return cfg


def applog(msg):
    """Small diagnostic log in the configuration folder (vigilo.log, kept under ~200 KB)."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        path = os.path.join(CONFIG_DIR, "vigilo.log")
        if os.path.exists(path) and os.path.getsize(path) > 200_000:
            os.replace(path, path + ".old")
        with open(path, "a", encoding="utf-8") as f:
            f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_FILE)


def safe_name(name):
    keep = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()
    return keep or "Camera"


def cam_url(cam, sub=False):
    """Camera RTSP URL. sub=True -> secondary stream (light, for the preview)."""
    if cam.get("kind") == KIND_CUSTOM:
        main = cam.get("url_main", "").strip()
        sub_url = cam.get("url_sub", "").strip()
        return (sub_url or main) if sub else main
    return ("rtsp://{ip}:{port}/user={user}&password={pwd}&channel={ch}&stream={s}.sdp?real_stream"
            .format(ip=cam.get("ip", ""), port=cam.get("port", 554), user=cam.get("user", "admin"),
                    pwd=cam.get("password", ""), ch=cam.get("channel", 1), s=1 if sub else 0))


def cam_address(cam):
    if cam.get("kind") == KIND_CUSTOM:
        from urllib.parse import urlsplit
        try:
            u = urlsplit(cam.get("url_main", ""))
            return f"{u.hostname}:{u.port or 554}" if u.hostname else "URL"
        except ValueError:
            return "URL"
    if cam.get("kind") == KIND_CLOUD:
        return cam.get("cloud_id", "")
    port = cam.get("dvrip_port", 34567) if cam.get("kind") == KIND_NATIVE else cam.get("port", 554)
    return f"{cam.get('ip', '')}:{port}"


def open_capture(url):
    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG,
                               [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 15000,
                                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000])
    except Exception:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return cap


def port_open(host, port, timeout=2.0):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent, it only selects the interface
        return s.getsockname()[0]
    except Exception:
        return "192.168.1.100"
    finally:
        s.close()


def fmt_gb(b):
    gb = b / 1024**3
    return f"{gb:.0f} GB" if gb >= 10 else f"{gb:.1f} GB"


def fmt_size(b):
    return f"{b / 1024**2:.0f} MB" if b < 1024**3 else fmt_gb(b)


_JOB = None


def kill_with_app(proc):
    """Tie an ffmpeg process to the program with a Windows Job Object: if the program exits
    or crashes, Windows kills ffmpeg too (no orphan recordings)."""
    global _JOB
    if os.name != "nt":
        return
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        if _JOB is None:
            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ulonglong) for n in (
                    "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                    "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

            class BASIC(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                            ("SchedulingClass", wintypes.DWORD)]

            class EXT(ctypes.Structure):
                _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS),
                            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

            job = k32.CreateJobObjectW(None, None)
            info = EXT()
            info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            k32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info))
            _JOB = job
        k32.AssignProcessToJobObject(wintypes.HANDLE(_JOB), wintypes.HANDLE(int(proc._handle)))
    except Exception:
        pass
