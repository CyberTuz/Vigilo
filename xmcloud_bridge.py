"""
ICSee / XMeye cloud bridge for Vigilo (experimental).

Runs in a separate process (Vigilo.exe --cloud-bridge) so that a crash inside the
vendor DLL cannot take the main program down.

It uses NetSdk.dll (the Xiongmai SDK used by the "VMS" client) to reach a camera by
its serial number (Cloud ID), also when the camera is in another house.

Protocol with the main program:
  stdin  -> JSON lines. The first one is the configuration:
            {"dll_dir", "mode": "cloud"|"ip", "id", "port", "user", "password",
             optional "tries", "want_ptz", "app": {"uuid","key","secret","moved"}, "api": "loginex"}
            then commands: {"cmd": "start", "channel", "stream"}
                           {"cmd": "ptz", "op", "stop", "speed"}
                           {"cmd": "ptzex", "op", "p1"}
                           {"cmd": "quit"}
  stdout -> binary messages: header "<BBHI" (type, flags, fps, length) + data
            type 1 = status (JSON), type 2 = video (flag bit0 = keyframe, bit1 = H.265)
            Error statuses carry "code" (NetSdk error), "key" (English text the main program
            translates) and "detail" (extra information from the SDK).
Standard library only: no heavy imports.
"""

import os
import sys
import json
import time
import queue
import struct
import ctypes
import threading
from ctypes import (Structure, POINTER, WINFUNCTYPE, c_int, c_uint, c_long, c_ulong, c_ushort,
                    c_char, c_char_p, c_void_p, c_bool, byref, string_at, create_string_buffer)

T_STATUS, T_VIDEO = 1, 2
HDR = struct.Struct("<BBHI")


class SDK_SYSTEM_TIME(Structure):
    _fields_ = [(n, c_int) for n in ("year", "month", "day", "wday", "hour", "minute", "second", "isdst")]


class H264_DVR_DEVICEINFO(Structure):
    _fields_ = [
        ("sSoftWareVersion", c_char * 64), ("sHardWareVersion", c_char * 64),
        ("sEncryptVersion", c_char * 64), ("tmBuildTime", SDK_SYSTEM_TIME),
        ("sSerialNumber", c_char * 64), ("byChanNum", c_int), ("iVideoOutChannel", c_int),
        ("byAlarmInPortNum", c_int), ("byAlarmOutPortNum", c_int), ("iTalkInChannel", c_int),
        ("iTalkOutChannel", c_int), ("iExtraChannel", c_int), ("iAudioInChannel", c_int),
        ("iCombineSwitch", c_int), ("iDigChannel", c_int), ("uiDeviceRunTime", c_uint),
        ("deviceTye", c_int), ("sHardWare", c_char * 64), ("uUpdataTime", c_char * 20),
        ("uUpdataType", c_uint), ("sDeviceModel", c_char * 16), ("nLanguage", c_int),
        ("sCloudErrCode", c_char * 260), ("status", c_int * 32),
        ("_spare", c_char * 4096),   # margin: newer DLL versions have more fields
    ]


class H264_DVR_CLIENTINFO(Structure):
    _fields_ = [("nChannel", c_int), ("nStream", c_int), ("nMode", c_int), ("nComType", c_int),
                ("hWnd", c_void_p), ("_spare", c_char * 256)]


class PACKET_INFO_EX(Structure):
    _fields_ = [
        ("nPacketType", c_int), ("pPacketBuffer", c_void_p), ("dwPacketSize", c_uint),
        ("nEncodeType", c_uint), ("nYear", c_int), ("nMonth", c_int), ("nDay", c_int),
        ("nHour", c_int), ("nMinute", c_int), ("nSecond", c_int), ("dwTimeStamp", c_uint),
        ("dwTimeStampHigh", c_uint), ("dwFrameNum", c_uint), ("dwFrameRate", c_uint),
        ("uWidth", c_ushort), ("uHeight", c_ushort), ("Reserved", c_uint * 6),
    ]


class SDK_AccountInfo(Structure):
    _fields_ = [("szUuid", c_char * 64), ("szAppKey", c_char * 64),
                ("szAppSecret", c_char * 64), ("nMovedCard", c_int)]


REALDATA_CB = WINFUNCTYPE(c_int, c_long, POINTER(PACKET_INFO_EX), c_long)
DISCONNECT_CB = WINFUNCTYPE(None, c_long, c_char_p, c_long, c_ulong)

VIDEO_TYPES = {1, 2, 3, 4, 5}   # I, B, P, BP, BBP
AUTH_ERRORS = {-11300, -11301, -11302, -11303, -11304, -11314, -11318, -11619, -11620}
# PTZ commands of the DLL (enum PTZ_ControlType)
PTZ_SET, PTZ_DEL, PTZ_GOTO = 17, 18, 19


def clean_nals(buf):
    """Remove the DLL's internal pseudo-NAL units (forbidden_zero_bit = 1) that confuse decoders."""
    if not (buf[:4] == b"\x00\x00\x00\x01" or buf[:3] == b"\x00\x00\x01"):
        # length-prefixed (AVCC) format: convert to Annex-B
        out, i, n = bytearray(), 0, len(buf)
        while i + 4 <= n:
            ln = int.from_bytes(buf[i:i + 4], "big")
            i += 4
            if ln <= 0 or i + ln > n:
                break
            out += b"\x00\x00\x00\x01" + buf[i:i + ln]
            i += ln
        if out:
            buf = bytes(out)
    n = len(buf)
    starts = []
    i = buf.find(b"\x00\x00\x01")
    while i >= 0:
        s = i - 1 if i > 0 and buf[i - 1] == 0 else i
        starts.append((s, i + 3))
        i = buf.find(b"\x00\x00\x01", i + 3)
    if not starts or not any(h < n and buf[h] & 0x80 for _, h in starts):
        return buf
    parts = []
    for k, (s, h) in enumerate(starts):
        e = starts[k + 1][0] if k + 1 < len(starts) else n
        if h < n and not buf[h] & 0x80:
            parts.append(buf[s:e])
    return b"".join(parts)


def sniff_codec(buf, enc):
    if enc == 5:
        return True
    if enc == 2:
        return False
    if b"\x00\x00\x01\x40\x01" in buf or b"\x00\x00\x01\x42\x01" in buf:
        return True
    return False


def _std_streams():
    """Binary stdin/stdout even in the console-less exe. The real stdout is reserved for
    our messages and the "normal" one is redirected to stderr, so printf calls inside
    the DLL cannot corrupt the video stream."""
    k32 = ctypes.WinDLL("kernel32")
    k32.GetStdHandle.restype = c_void_p
    k32.SetStdHandle.argtypes = [c_ulong, c_void_p]
    import msvcrt

    def fd_for(std, flags):
        try:
            f = (sys.stdin, sys.stdout, sys.stderr)[(-10 - std)]
            if f is not None:
                return os.dup(f.fileno())
        except Exception:
            pass
        h = k32.GetStdHandle(c_ulong(std & 0xFFFFFFFF))
        return msvcrt.open_osfhandle(h, flags)

    fin = os.fdopen(fd_for(-10, os.O_RDONLY), "rb", buffering=0)
    fout = os.fdopen(fd_for(-11, 0), "wb", buffering=0)
    try:
        err_h = k32.GetStdHandle(c_ulong(-12 & 0xFFFFFFFF))
        k32.SetStdHandle(c_ulong(-11 & 0xFFFFFFFF), err_h)
        try:
            os.dup2(fd_for(-12, 0), 1)
        except Exception:
            pass
        sys.stdout = sys.stderr
    except Exception:
        pass
    return fin, fout


class Bridge:
    def __init__(self, fin, fout):
        self.fin, self.fout = fin, fout
        self.q = queue.Queue()
        self.qbytes = 0
        self.qlock = threading.Lock()
        self.need_key = True
        self.dll = None
        self.login_id = 0
        self.real = 0
        self.last_frame = 0.0
        self.started_at = 0.0
        self.alive = True
        self._cb = None
        self._dc = None
        self.writer = threading.Thread(target=self._writer, daemon=True)
        self.writer.start()

    # ------------------------------------------------------------- output
    def _writer(self):
        while True:
            msg = self.q.get()
            if msg is None:
                break
            with self.qlock:
                self.qbytes -= len(msg)
            try:
                self.fout.write(msg)
            except (OSError, ValueError):
                os._exit(0)   # the main program has exited

    def _put(self, msg):
        with self.qlock:
            self.qbytes += len(msg)
        self.q.put(msg)

    def status(self, **ev):
        data = json.dumps(ev).encode("utf-8")
        self._put(HDR.pack(T_STATUS, 0, 0, len(data)) + data)

    def video(self, key, hevc, fps, data):
        with self.qlock:
            backlog = self.qbytes
        if backlog > 8 * 1024 * 1024 and not key:
            self.need_key = True       # the program is behind: skip to the next keyframe
            return
        if self.need_key and not key:
            return
        self.need_key = False
        self._put(HDR.pack(T_VIDEO, (1 if key else 0) | (2 if hevc else 0), min(fps, 255), len(data)) + data)

    def fail(self, key, code=0, auth=False, exit_code=2, clean=True, detail=""):
        """Report the error and exit. clean=False when called from a DLL thread
        (calling into the DLL from there can deadlock)."""
        self.status(event="error", key=key, msg=key, code=code, auth=auth, detail=detail)
        self.q.put(None)
        self.writer.join(2)
        if clean:
            t = threading.Thread(target=self.cleanup, daemon=True)
            t.start()
            t.join(4)
        os._exit(exit_code)

    # ------------------------------------------------------------- DLL
    def load(self, dll_dir):
        os.chdir(dll_dir)
        try:
            os.add_dll_directory(dll_dir)
        except (AttributeError, OSError):
            pass
        try:
            d = ctypes.WinDLL(os.path.join(dll_dir, "NetSdk.dll"))
        except OSError as e:
            if getattr(e, "winerror", 0) == 14001:   # the Visual C++ runtime needed by the DLL is missing
                self.fail("This NetSdk.dll needs the Microsoft Visual C++ 2005 Redistributable (x64)")
            self.fail("Cannot load NetSdk.dll", detail=str(e))
        d.H264_DVR_Init.argtypes = [DISCONNECT_CB, c_ulong]
        d.H264_DVR_Init.restype = c_long
        d.H264_DVR_SetConnectTime.argtypes = [c_long, c_long]
        d.H264_DVR_SetConnectTime.restype = c_bool
        d.H264_DVR_Login_Cloud.argtypes = [c_char_p, c_ushort, c_char_p, c_char_p,
                                           POINTER(H264_DVR_DEVICEINFO), POINTER(c_int), c_char_p]
        d.H264_DVR_Login_Cloud.restype = c_long
        try:
            d.H264_DVR_InitAppInfo.argtypes = [POINTER(SDK_AccountInfo)]
            d.H264_DVR_InitAppInfo.restype = c_long
        except AttributeError:
            pass
        d.H264_DVR_Login.argtypes = [c_char_p, c_ushort, c_char_p, c_char_p,
                                     POINTER(H264_DVR_DEVICEINFO), POINTER(c_int), c_int]
        d.H264_DVR_Login.restype = c_long
        # LoginEx_V2 (used by VMS). The 2019 documentation says socketType=1 means "cloud serial",
        # but in the DLLs tested 1 = UDP: kept only as an experimental option.
        d.H264_DVR_LoginEx_V2.argtypes = [c_char_p, c_ushort, c_char_p, c_char_p,
                                          POINTER(H264_DVR_DEVICEINFO), c_int, POINTER(c_int), c_int]
        d.H264_DVR_LoginEx_V2.restype = c_long
        d.H264_DVR_RealPlay.argtypes = [c_long, POINTER(H264_DVR_CLIENTINFO)]
        d.H264_DVR_RealPlay.restype = c_long
        d.H264_DVR_SetRealDataCallBack_V2.argtypes = [c_long, REALDATA_CB, c_long]
        d.H264_DVR_SetRealDataCallBack_V2.restype = c_bool
        d.H264_DVR_StopRealPlay.argtypes = [c_long, c_void_p]
        d.H264_DVR_StopRealPlay.restype = c_bool
        d.H264_DVR_PTZControl.argtypes = [c_long, c_int, c_long, c_bool, c_long]
        d.H264_DVR_PTZControl.restype = c_bool
        d.H264_DVR_PTZControlEx.argtypes = [c_long, c_int, c_long, c_long, c_long, c_long, c_bool]
        d.H264_DVR_PTZControlEx.restype = c_bool
        d.H264_DVR_Logout.argtypes = [c_long]
        d.H264_DVR_Logout.restype = c_long
        d.H264_DVR_Cleanup.restype = c_bool
        d.H264_DVR_GetLastError.restype = c_long
        try:
            d.H264_DVR_GetDevConfig_JsonV2.argtypes = [c_long, c_char_p, c_int, c_int, c_char_p, c_ulong,
                                                       POINTER(c_ulong), c_int]
            d.H264_DVR_GetDevConfig_JsonV2.restype = c_long
        except AttributeError:
            pass
        self.dll = d

        def on_disconnect(login_id, ip, port, user):
            if login_id == self.login_id and self.alive:
                self.fail("Lost connection to the camera", clean=False)
        self._dc = DISCONNECT_CB(on_disconnect)
        if d.H264_DVR_Init(self._dc, 0) <= 0:
            self.fail("SDK initialization failed")
        d.H264_DVR_SetConnectTime(15000, 2)

    def login(self, cfg):
        d = self.dll
        mode = cfg.get("mode", "cloud")
        dev_id = str(cfg["id"]).strip().encode()
        user = str(cfg.get("user", "admin")).encode()
        pwd = str(cfg.get("password", "")).encode("utf-8")
        port = int(cfg.get("port") or 34567)
        # the cloud needs many attempts: behind a symmetric NAT the DLL switches to the
        # relay only after several rounds (VMS and xmeye_cloud_to_rtsp do the same)
        tries = int(cfg.get("tries") or (20 if mode == "cloud" else 1))
        app = cfg.get("app") or {}
        if mode == "cloud" and (app or cfg.get("init_app")) and hasattr(d, "H264_DVR_InitAppInfo"):
            ai = SDK_AccountInfo(szUuid=str(app.get("uuid", "")).encode(),
                                 szAppKey=str(app.get("key", "")).encode(),
                                 szAppSecret=str(app.get("secret", "")).encode(),
                                 nMovedCard=int(app.get("moved", 0)))
            r = d.H264_DVR_InitAppInfo(byref(ai))
            self.status(event="progress", msg=f"InitAppInfo={r}")
        if mode == "cloud":
            time.sleep(3)   # the P2P part of the DLL needs a few seconds after Init
        code, cloud_err = 0, ""
        for attempt in range(1, tries + 1):
            info = H264_DVR_DEVICEINFO()
            err = c_int(0)
            if mode == "cloud" and cfg.get("api") == "loginex":
                lid = d.H264_DVR_LoginEx_V2(dev_id, port, user, pwd, byref(info),
                                            int(cfg.get("ltype", 3)), byref(err), 1)
            elif mode == "cloud":
                lid = d.H264_DVR_Login_Cloud(dev_id, port, user, pwd, byref(info), byref(err), b"")
            else:
                lid = d.H264_DVR_Login(dev_id, port, user, pwd, byref(info), byref(err), 0)
            if lid > 0:
                self.login_id = lid
                return info
            code = err.value or d.H264_DVR_GetLastError()
            cloud_err = info.sCloudErrCode.decode("utf-8", "ignore").strip("\x00 ")
            if code in AUTH_ERRORS:
                break
            if attempt < tries:
                self.status(event="progress", msg=f"Attempt {attempt + 1}/{tries}...")
                time.sleep(3 if mode == "cloud" else 5)
        self.fail("Connection failed", code, code in AUTH_ERRORS, detail=cloud_err)

    def ptz_support(self):
        try:
            buf = create_string_buffer(64 * 1024)
            n = c_ulong(0)
            r = self.dll.H264_DVR_GetDevConfig_JsonV2(self.login_id, b"SystemFunction", 1360, -1,
                                                      buf, len(buf), byref(n), 4000)
            if r <= 0 or not n.value:
                return None
            data = json.loads(buf.raw[:n.value].rstrip(b"\x00\n\r ").decode("utf-8", "ignore"))
            sf = data.get("SystemFunction", data)
            of = sf.get("OtherFunction", {}) if isinstance(sf, dict) else {}
            return bool(of.get("SupportPTZDirectionControl") or of.get("SupportPTZTour"))
        except Exception:
            return None

    def start(self, channel, stream):
        d = self.dll
        if self.real:
            return self.status(event="started")
        ci = H264_DVR_CLIENTINFO(nChannel=int(channel), nStream=int(stream), nMode=0, nComType=0, hWnd=None)
        h = d.H264_DVR_RealPlay(self.login_id, byref(ci))
        if not h:
            code = d.H264_DVR_GetLastError()
            return self.status(event="start_error", code=code, key="The camera refused the video")

        def on_data(handle, pframe, user):
            try:
                f = pframe.contents
                if f.nPacketType in VIDEO_TYPES and f.dwPacketSize and f.pPacketBuffer:
                    raw = string_at(f.pPacketBuffer, f.dwPacketSize)
                    key = f.nPacketType == 1
                    self.last_frame = time.time()
                    self.video(key, sniff_codec(raw, f.nEncodeType), int(f.dwFrameRate or 0), clean_nals(raw))
            except Exception:
                pass
            return 0

        self._cb = REALDATA_CB(on_data)
        if not d.H264_DVR_SetRealDataCallBack_V2(h, self._cb, 0):
            d.H264_DVR_StopRealPlay(h, None)
            return self.status(event="start_error", code=0, key="Cannot receive the video")
        self.real = h
        self.started_at = time.time()
        self.status(event="started")
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _watchdog(self):
        while self.alive:
            time.sleep(2)
            ref = max(self.last_frame, self.started_at)
            if self.real and time.time() - ref > 25:
                self.fail("The video stopped arriving" if self.last_frame else "Connected, but no video arrives")

    def cleanup(self):
        if not self.alive or self.dll is None:
            return
        self.alive = False
        d = self.dll
        try:
            if self.real:
                d.H264_DVR_StopRealPlay(self.real, None)
            if self.login_id:
                d.H264_DVR_Logout(self.login_id)
            d.H264_DVR_Cleanup()
        except Exception:
            pass

    def run(self):
        line = self.fin.readline()
        if not line:
            return 0
        cfg = json.loads(line.decode("utf-8"))
        dll_dir = cfg.get("dll_dir", "")
        if not os.path.isfile(os.path.join(dll_dir, "NetSdk.dll")):
            self.fail("NetSdk.dll not found.")
        self.load(dll_dir)
        info = self.login(cfg)
        self.status(event="login", serial=info.sSerialNumber.decode("utf-8", "ignore").strip("\x00 "),
                    model=info.sHardWare.decode("utf-8", "ignore").strip("\x00 "),
                    version=info.sSoftWareVersion.decode("utf-8", "ignore").strip("\x00 "),
                    chans=int(info.byChanNum), limits=list(info.status[:4]),
                    ptz=self.ptz_support() if cfg.get("want_ptz") else None)
        while True:
            line = self.fin.readline()
            if not line:
                break
            try:
                c = json.loads(line.decode("utf-8"))
            except ValueError:
                continue
            cmd = c.get("cmd")
            if cmd == "start":
                self.start(c.get("channel", 0), c.get("stream", 0))
            elif cmd == "ptz":
                ok = self.dll.H264_DVR_PTZControl(self.login_id, int(c.get("channel", 0)), int(c["op"]),
                                                  bool(c.get("stop")), int(c.get("speed", 4)))
                self.status(event="ptz", ok=bool(ok))
            elif cmd == "ptzex":
                ok = self.dll.H264_DVR_PTZControlEx(self.login_id, int(c.get("channel", 0)), int(c["op"]),
                                                    int(c.get("p1", 0)), 0, 0, False)
                self.status(event="ptz", ok=bool(ok))
            elif cmd == "quit":
                break
        self.cleanup()
        self.q.put(None)
        return 0


def main():
    fin, fout = _std_streams()
    b = Bridge(fin, fout)
    try:
        code = b.run()
    except Exception as e:
        b.fail("Internal error of the cloud connection", detail=str(e))
        code = 2
    time.sleep(0.3)
    os._exit(code)


if __name__ == "__main__":
    main()
