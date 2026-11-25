"""
Fake XMeye/ICSee camera (DVRIP protocol, TCP) for testing Vigilo without hardware.

    python tools/fake_dvrip.py video.h264 34567 password [--no-audio]

- Accepts the login "admin" + the given password (sofia hash, like real cameras).
- Streams the H.264 file in a loop at 15 fps, split into 7000-byte packets like real cameras.
- Sends G.711 A-law audio frames (a 440 Hz tone, 8 kHz, 40 ms per frame) unless --no-audio.
The H.264 file must contain access unit delimiters (ffmpeg: -bsf:v h264_metadata=aud=insert).
"""
import sys
import json
import math
import time
import socket
import struct
import hashlib
import threading

H264, PORT, PASSWORD = sys.argv[1], int(sys.argv[2]), sys.argv[3]
AUDIO = "--no-audio" not in sys.argv
HDR = struct.Struct("<BB2xII2xHI")


def sofia(pw):
    c = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    h = hashlib.md5(pw.encode()).digest()
    return "".join(c[(h[i] + h[i + 1]) % 62] for i in range(0, 16, 2))


def alaw_encode(sample):
    """16-bit PCM sample -> G.711 A-law byte."""
    sign = 0x80 if sample >= 0 else 0
    if sample < 0:
        sample = -sample - 1
    sample = min(sample, 32635) >> 3
    if sample >= 32:
        seg = int(math.log2(sample)) - 4         # 13-bit magnitude 32..63 -> segment 1 ... 2048.. -> 7
        mant = (sample >> seg) & 0x0F
        val = (seg << 4) | mant
    else:
        val = sample >> 1
    return (val | sign) ^ 0x55


TONE = bytes(alaw_encode(int(8000 * math.sin(2 * math.pi * 440 * i / 8000))) for i in range(8000))

data = open(H264, "rb").read()
idx = []
i = data.find(b"\x00\x00\x00\x01\x09")
while i >= 0:
    idx.append(i)
    i = data.find(b"\x00\x00\x00\x01\x09", i + 5)
idx.append(len(data))
frames = [data[idx[k]:idx[k + 1]] for k in range(len(idx) - 1)]
print("frames", len(frames), "audio", AUDIO, flush=True)


def is_key(f):
    j = 0
    while True:
        j = f.find(b"\x00\x00\x01", j)
        if j < 0 or j + 3 >= len(f):
            return False
        if f[j + 3] & 0x1F in (5, 7):
            return True
        j += 3


def handle(conn):
    session = 0x1A
    seq = [0]
    lock = threading.Lock()
    stop = threading.Event()

    def send(msgid, payload):
        with lock:
            conn.sendall(HDR.pack(0xFF, 1, session, seq[0], msgid, len(payload)) + payload)
            seq[0] += 1

    def reply(msgid, obj):
        send(msgid, json.dumps(obj).encode() + b"\x0a\x00")

    def recv_exact(n):
        b = b""
        while len(b) < n:
            c = conn.recv(n - len(b))
            if not c:
                raise ConnectionError
            b += c
        return b

    def streamer():
        k, t = 0, time.time()
        try:
            while not stop.is_set():
                f = frames[k % len(frames)]
                if is_key(f):
                    hdr = b"\x00\x00\x01\xfc" + bytes([2, 15, 160, 90]) + struct.pack("<II", 0, len(f))
                else:
                    hdr = b"\x00\x00\x01\xfd" + struct.pack("<I", len(f))
                blob = hdr + f
                for o in range(0, len(blob), 7000):
                    send(1412, blob[o:o + 7000])
                k += 1
                t += 1 / 15
                time.sleep(max(0, t - time.time()))
        except Exception:
            pass

    def audio():
        k, t = 0, time.time()
        try:
            while not stop.is_set():
                chunk = TONE[(k * 320) % 7680:(k * 320) % 7680 + 320]
                send(1412, b"\x00\x00\x01\xfa" + bytes([0x0E, 0x02]) + struct.pack("<H", len(chunk)) + chunk)
                k += 1
                t += 0.04
                time.sleep(max(0, t - time.time()))
        except Exception:
            pass

    try:
        while True:
            h = recv_exact(20)
            _, _, _, _, msgid, ln = HDR.unpack(h)
            body = json.loads(recv_exact(ln).rstrip(b"\x00\x0a"))
            if msgid == 1000:
                ok = body.get("UserName") == "admin" and body.get("PassWord") == sofia(PASSWORD)
                reply(1001, {"Ret": 100, "SessionID": "0x%08X" % session, "AliveInterval": 21} if ok else {"Ret": 203})
            elif msgid == 1413:
                reply(1414, {"Ret": 100, "Name": "OPMonitor"})
            elif msgid == 1410:
                threading.Thread(target=streamer, daemon=True).start()
                if AUDIO:
                    threading.Thread(target=audio, daemon=True).start()
            elif msgid == 1006:
                reply(1007, {"Ret": 100, "Name": "KeepAlive"})
            elif msgid == 1360:
                reply(1361, {"Ret": 100, "Name": "SystemFunction", "SystemFunction": {"OtherFunction": {}}})
    except Exception:
        pass
    finally:
        stop.set()
        conn.close()


srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", PORT))
srv.listen(16)
print("listening", PORT, flush=True)
while True:
    c, _ = srv.accept()
    threading.Thread(target=handle, args=(c,), daemon=True).start()
