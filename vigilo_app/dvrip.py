"""
Native ICSee / XMeye protocol (DVRIP / "Sofia", TCP 34567): login, PTZ, live video and audio.
"""

import json
import time
import socket
import struct
import hashlib
import threading

from i18n import tr


# ----------------------------------------------------------------------------- native ICSee / XMeye protocol (DVRIP)

class DvripError(Exception):
    pass


class DvripAuthError(DvripError):
    pass


DVRIP_OK = (100, 515)
DVRIP_AUTH_CODES = {106, 203, 205, 206, 207}
DVRIP_ERRORS = {   # English source text, translated with tr() when shown
    101: "Unknown camera error",
    102: "Unsupported version",
    103: "Operation not allowed",
    104: "User already logged in",
    106: "Wrong user name or password",
    107: "Insufficient permissions",
    203: "Wrong password",
    205: "User does not exist",
    206: "User locked after too many attempts (try again in a few minutes)",
    207: "User locked",
}
_VALID_FRAME = (0xF9, 0xFA, 0xFC, 0xFD, 0xFE)


def sofia_hash(password):
    """Password hash used by XMeye/ICSee cameras ("sofia hash")."""
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    h = hashlib.md5(password.encode("utf-8")).digest()
    return "".join(chars[(h[i] + h[i + 1]) % 62] for i in range(0, 16, 2))


class DvripClient:
    HDR = struct.Struct("<BB2xII2xHI")
    LOGIN, KEEPALIVE, MONITOR_START, MONITOR_DATA, MONITOR_CLAIM = 1000, 1006, 1410, 1412, 1413
    PTZ, SYSFUNC = 1400, 1360

    def __init__(self, host, port=34567, user="admin", password="", timeout=8.0):
        self.host, self.port, self.user, self.password = host, int(port), user, password
        self.timeout = timeout
        self.sock = None
        self.session = 0
        self.seq = 0
        self.alive = 20
        self.lock = threading.Lock()

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        self._send(self.LOGIN, {"EncryptType": "MD5", "LoginType": "DVRIP-Web",
                                "PassWord": sofia_hash(self.password), "UserName": self.user})
        _, data = self._recv_msg()
        rep = self._json(data)
        ret = rep.get("Ret")
        if ret not in DVRIP_OK:
            msg = tr(DVRIP_ERRORS[ret]) if ret in DVRIP_ERRORS else tr("Access denied (code {code})").format(code=ret)
            raise (DvripAuthError if ret in DVRIP_AUTH_CODES else DvripError)(msg)
        sid = rep.get("SessionID")
        if isinstance(sid, str):
            try:
                self.session = int(sid, 16)
            except ValueError:
                pass
        try:
            self.alive = max(5, int(rep.get("AliveInterval") or 20))
        except (TypeError, ValueError):
            pass

    def _sid(self):
        return "0x%08X" % self.session

    def _send(self, msgid, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\x0a\x00"
        with self.lock:
            pkt = self.HDR.pack(0xFF, 0, self.session, self.seq, msgid, len(data)) + data
            self.sock.sendall(pkt)
            self.seq += 1

    def _recv_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(min(262144, n - len(buf)))
            if not chunk:
                raise ConnectionError(tr("Connection closed by the camera"))
            buf += chunk
        return bytes(buf)

    def _recv_msg(self):
        hdr = self._recv_exact(20)
        if hdr[0] != 0xFF:
            raise DvripError(tr("Invalid reply: this does not look like an ICSee/XMeye camera"))
        _, _, session, _, msgid, length = self.HDR.unpack(hdr)
        if length > 16 * 1024 * 1024:
            raise DvripError(tr("Invalid packet from the camera"))
        if session:
            self.session = session
        return msgid, self._recv_exact(length)

    @staticmethod
    def _json(data):
        try:
            return json.loads(data.rstrip(b"\x00\x0a\r ").decode("utf-8", "ignore"))
        except ValueError:
            return {}

    def command(self, msgid, name, payload=None):
        """Command with a reply (only on a connection that is NOT receiving video)."""
        obj = {"Name": name, "SessionID": self._sid()}
        if payload is not None:
            obj[name] = payload
        self._send(msgid, obj)
        _, data = self._recv_msg()
        return self._json(data)

    def ptz(self, cmd, preset=-1, step=5, channel=0):
        """Movement: preset=65535 starts, preset=-1 stops. For Goto/SetPreset, preset = number."""
        rep = self.command(self.PTZ, "OPPTZControl", {"Command": cmd, "Parameter": {
            "AUX": {"Number": 0, "Status": "On"}, "Channel": int(channel), "MenuOpts": "Enter",
            "POINT": {"bottom": 0, "left": 0, "right": 0, "top": 0}, "Pattern": "SetBegin",
            "Preset": int(preset), "Step": int(step), "Tour": 0}})
        return rep.get("Ret") in DVRIP_OK

    def supports_ptz(self):
        sf = self.command(self.SYSFUNC, "SystemFunction").get("SystemFunction", {})
        of = sf.get("OtherFunction", {}) if isinstance(sf, dict) else {}
        return bool(of.get("SupportPTZDirectionControl") or of.get("SupportPTZTour"))

    def start_stream(self, channel=0, stream="Main"):
        params = {"Channel": int(channel), "CombinMode": "NONE", "StreamType": stream, "TransMode": "TCP"}
        self._send(self.MONITOR_CLAIM, {"Name": "OPMonitor", "SessionID": self._sid(),
                                        "OPMonitor": {"Action": "Claim", "Parameter": params}})
        _, data = self._recv_msg()
        ret = self._json(data).get("Ret")
        if ret not in DVRIP_OK:
            raise DvripError(tr("The camera refused the {stream} stream (code {code})").format(stream=stream, code=ret))
        self._send(self.MONITOR_START, {"Name": "OPMonitor", "SessionID": self._sid(),
                                        "OPMonitor": {"Action": "Start", "Parameter": params}})

    @staticmethod
    def _resync(buf):
        i = 1
        while True:
            i = buf.find(b"\x00\x00\x01", i)
            if i < 0:
                return -1
            if i + 3 >= len(buf) or buf[i + 3] in _VALID_FRAME:
                return i
            i += 1

    def frames(self):
        """Generator of (type, keyframe, codec, fps, data). type = 'video' | 'audio'.
        For audio: codec = media byte of the frame header (G.711 A-law/u-law), fps = sample-rate byte.
        Frames may be split across packets, or several frames may share one packet."""
        buf = bytearray()
        codec, fps = "h264", 0
        last_ka = time.time()
        ka_every = max(5, min(20, self.alive * 0.5))
        while True:
            now = time.time()
            if now - last_ka > ka_every:
                self._send(self.KEEPALIVE, {"Name": "KeepAlive", "SessionID": self._sid()})
                last_ka = now
            msgid, data = self._recv_msg()
            if msgid != self.MONITOR_DATA:
                continue
            buf += data
            while len(buf) >= 8:
                if not (buf[0] == 0 and buf[1] == 0 and buf[2] == 1 and buf[3] in _VALID_FRAME):
                    i = self._resync(buf)
                    if i < 0:
                        del buf[:max(0, len(buf) - 3)]
                        break
                    del buf[:i]
                    continue
                t = buf[3]
                if t in (0xFC, 0xFE):
                    if len(buf) < 16:
                        break
                    media, f_fps = buf[4], buf[5]
                    size, hl = struct.unpack_from("<I", buf, 12)[0], 16
                elif t == 0xFD:
                    size, hl = struct.unpack_from("<I", buf, 4)[0], 8
                else:
                    media, f_fps = buf[4], buf[5]
                    size, hl = struct.unpack_from("<H", buf, 6)[0], 8
                if size > 16 * 1024 * 1024:
                    del buf[:4]
                    continue
                if len(buf) < hl + size:
                    break
                payload = bytes(buf[hl:hl + size])
                del buf[:hl + size]
                if t in (0xFC, 0xFE):
                    codec = {2: "h264", 3: "hevc"}.get(media, codec)
                    fps = f_fps or fps
                    yield ("video", t == 0xFC, codec, fps, payload)
                elif t == 0xFD:
                    yield ("video", False, codec, fps, payload)
                elif t == 0xFA:
                    yield ("audio", False, media, f_fps, payload)

    def close(self):
        s = self.sock
        self.sock = None
        if s:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass
