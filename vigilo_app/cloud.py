"""
ICSee / XMeye cloud connection through NetSdk.dll, run in a separate process (xmcloud_bridge).
"""

import os
import sys
import json
import time
import struct
import threading
import subprocess
from collections import deque

from i18n import tr
from .common import CONFIG_DIR, ENTRY_SCRIPT, kill_with_app, NOWIN, ROOT_DIR
from .dvrip import DvripAuthError, DvripError


# ----------------------------------------------------------------------------- ICSee / XMeye cloud (NetSdk.dll)

APP_DIR = ROOT_DIR
SDK_HELP = ("The cloud connection needs NetSdk.dll (the Xiongmai SDK library).\n"
            "Put NetSdk.dll and StreamReader.dll in the \"sdk\" folder next to Vigilo.exe "
            "(see the README for details).")
PTZ_SDK = {"DirectionUp": 0, "DirectionDown": 1, "DirectionLeft": 2, "DirectionRight": 3,
           "DirectionLeftUp": 4, "DirectionLeftDown": 5, "DirectionRightUp": 6, "DirectionRightDown": 7}
PTZ_SDK_EX = {"SetPreset": 17, "ClearPreset": 18, "GotoPreset": 19}
_SDK_CACHE = [None, 0.0]
CLOUD_APP = {}      # optional Jftech developer account from settings["cloud_app"]: uuid, key, secret, moved


def _dll_is_x64(path):
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
        pe = struct.unpack_from("<I", head, 0x3C)[0]
        return head[pe:pe + 4] == b"PE\0\0" and struct.unpack_from("<H", head, pe + 4)[0] == 0x8664
    except (OSError, struct.error):
        return False


def find_cloud_sdk(refresh=False):
    """Folder holding a 64-bit NetSdk.dll: first the program's "sdk" folder, then an installed VMS."""
    if not refresh and _SDK_CACHE[0] and time.time() - _SDK_CACHE[1] < 300:
        return _SDK_CACHE[0]
    cands = [os.environ.get("VIGILO_SDK_DIR", "") or os.environ.get("TELECAMERE_SDK_DIR", ""),
             os.path.join(APP_DIR, "sdk"), os.path.join(CONFIG_DIR, "sdk")]
    roots = {os.environ.get(v, "") for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")}
    roots |= {"C:\\Program Files", "C:\\Program Files (x86)"}
    hints = ("vms", "cms", "xmeye", "icsee", "netsurveillance", "general", "xiongmai", "jftech")
    for root in sorted(r for r in roots if r and os.path.isdir(r)):
        try:
            for d1 in os.scandir(root):
                if not d1.is_dir() or not any(h in d1.name.lower() for h in hints):
                    continue
                cands.append(d1.path)
                try:
                    cands += [d2.path for d2 in os.scandir(d1.path) if d2.is_dir()]
                except OSError:
                    pass
        except OSError:
            pass
    found = None
    for d in cands:
        dll = os.path.join(d, "NetSdk.dll") if d else ""
        if dll and os.path.isfile(dll) and _dll_is_x64(dll):
            found = d
            break
    _SDK_CACHE[:] = [found, time.time()]
    return found


def bridge_cmd():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--cloud-bridge"]
    return [sys.executable, ENTRY_SCRIPT, "--cloud-bridge"]


class CloudClient:
    """Camera via the cloud (serial number). Same interface as DvripClient:
    connect / start_stream / frames / ptz / close. The real work is done by a separate
    process (xmcloud_bridge) that loads NetSdk.dll, so a crash there cannot take the app down."""
    HDR = struct.Struct("<BBHI")

    def __init__(self, cam, want_ptz=False, mode="cloud"):
        self.cam = cam
        self.want_ptz = want_ptz
        self.mode = mode
        self.proc = None
        self.info = {}
        self.progress = ""
        self.errlog = deque(maxlen=20)
        self.lock = threading.Lock()
        self.pending = deque()

    # --------------------------------------------------------- channel to the bridge process
    def _send(self, obj):
        try:
            with self.lock:
                self.proc.stdin.write(json.dumps(obj).encode("utf-8") + b"\n")
                self.proc.stdin.flush()
        except (OSError, ValueError, AttributeError):
            raise ConnectionError(tr("Cloud connection closed"))

    def _read_exact(self, n):
        p = self.proc
        if p is None:
            raise ConnectionError(tr("Cloud connection closed"))
        buf = bytearray()
        while len(buf) < n:
            chunk = p.stdout.read(n - len(buf))
            if not chunk:
                raise ConnectionError(tr("Cloud connection interrupted"))
            buf += chunk
        return bytes(buf)

    def _read(self):
        typ, flags, fps, ln = self.HDR.unpack(self._read_exact(self.HDR.size))
        if ln > 32 * 1024 * 1024:
            raise DvripError(tr("Invalid data from the cloud connection"))
        return typ, flags, fps, self._read_exact(ln)

    def _status(self, data):
        try:
            return json.loads(data.decode("utf-8", "ignore"))
        except ValueError:
            return {}

    def _raise(self, ev):
        raise (DvripAuthError if ev.get("auth") else DvripError)(cloud_error_text(ev))

    def _wait(self, events):
        """Read until one of the expected events arrives (video received meanwhile is kept)."""
        while True:
            typ, flags, fps, data = self._read()
            if typ != 1:
                self.pending.append((typ, flags, fps, data))
                continue
            ev = self._status(data)
            name = ev.get("event")
            if name == "error":
                self._raise(ev)
            if name == "progress":
                self.progress = ev.get("msg", "")
            if name in events:
                return ev

    def _stderr(self, p):
        for line in p.stderr:
            t = line.decode("utf-8", "ignore").strip()
            if t:
                self.errlog.append(t)

    # --------------------------------------------------------- common interface
    def connect(self):
        sdk = find_cloud_sdk()
        if not sdk:
            raise DvripError(tr("NetSdk.dll not found (see the README)"))
        dev = self.cam.get("cloud_id", "").strip() if self.mode == "cloud" else self.cam.get("ip", "")
        if not dev:
            raise DvripError(tr("The camera serial number is missing"))
        p = subprocess.Popen(bridge_cmd(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, creationflags=NOWIN, cwd=APP_DIR)
        kill_with_app(p)
        self.proc = p
        threading.Thread(target=self._stderr, args=(p,), daemon=True).start()
        cfg = {"dll_dir": sdk, "mode": self.mode, "id": dev,
               "port": int(self.cam.get("dvrip_port", 34567) or 34567),
               "user": self.cam.get("user", "admin"), "password": self.cam.get("password", ""),
               "want_ptz": self.want_ptz}
        if CLOUD_APP.get("key"):
            cfg["app"] = CLOUD_APP
        self._send(cfg)
        try:
            self.info = self._wait({"login"})
        except ConnectionError:
            if self.proc is None:
                raise
            err = " ".join(list(self.errlog)[-2:])
            raise DvripError(tr("The cloud connection closed") + (f": {err[-200:]}" if err else ""))

    def supports_ptz(self):
        return self.info.get("ptz")

    def start_stream(self, channel=0, stream="Main"):
        self._send({"cmd": "start", "channel": int(channel), "stream": 0 if stream == "Main" else 1})
        ev = self._wait({"started", "start_error"})
        if ev.get("event") == "start_error":
            raise DvripError(cloud_error_text(ev, tr("The camera refused the video")))

    def frames(self):
        while True:
            if self.pending:
                typ, flags, fps, data = self.pending.popleft()
            else:
                typ, flags, fps, data = self._read()
            if typ == 2:
                yield ("video", bool(flags & 1), "hevc" if flags & 2 else "h264", fps, data)
            elif typ == 1:
                ev = self._status(data)
                if ev.get("event") == "error":
                    self._raise(ev)

    def ptz(self, cmd, preset=-1, step=4, channel=0):
        if cmd in PTZ_SDK:
            self._send({"cmd": "ptz", "op": PTZ_SDK[cmd], "stop": preset == -1, "speed": 4,
                        "channel": int(channel)})
        elif cmd in PTZ_SDK_EX:
            self._send({"cmd": "ptzex", "op": PTZ_SDK_EX[cmd], "p1": int(preset), "channel": int(channel)})
        else:
            return False
        return bool(self._wait({"ptz"}).get("ok"))

    def close(self):
        p, self.proc = self.proc, None
        if not p:
            return
        try:
            p.stdin.write(b'{"cmd": "quit"}\n')
            p.stdin.flush()
            p.stdin.close()
        except Exception:
            pass

        def reap():
            try:
                p.wait(4)   # the bridge logs out of the camera cleanly
            except Exception:
                pass
            try:
                p.kill()
            except Exception:
                pass
        threading.Thread(target=reap, daemon=True).start()


CLOUD_ERRORS = {   # NetSdk error codes -> English text (translated with tr() when shown)
    -10005: "Timed out",
    -10007: "Network error",
    -11200: "Cannot open the video (is the camera offline?)",
    -11202: "Video connection failed (is the camera offline?)",
    -11204: "Too many simultaneous cloud viewers",
    -11300: "Insufficient permissions",
    -11301: "Wrong user name or password",
    -11302: "User does not exist (newer cameras may use a random user name or a token)",
    -11303: "User locked after too many attempts (try again later)",
    -11305: "User already logged in",
    -11307: "Camera not found",
    -11318: "Wrong user name or password",
    -11602: "Name resolution failed",
    -11604: "Camera offline (the cloud cannot find it)",
    -11605: "Cloud server busy",
    -11608: "Cannot reach the cloud server",
    -11611: "Connection failed",
    -11612: "Cloud server full",
    -11615: "Too many open connections",
    -11619: "User does not exist",
    -11620: "Wrong user name or password",
    -12003: "This NetSdk.dll requires a developer account (see the README)",
}


def cloud_error_text(ev, default=None):
    """Readable, translated text for an error event coming from the cloud bridge."""
    code = ev.get("code") or 0
    if code in CLOUD_ERRORS:
        txt = tr(CLOUD_ERRORS[code])
    elif ev.get("key") == "Connection failed" and code:
        txt = tr("Connection failed (code {code})").format(code=code)
    elif ev.get("key"):
        txt = tr(ev["key"])
    elif code:
        txt = tr("Connection failed (code {code})").format(code=code)
    else:
        txt = ev.get("msg") or default or tr("Cloud connection error")
    if ev.get("detail"):
        txt += f" [{ev['detail']}]"
    return txt
