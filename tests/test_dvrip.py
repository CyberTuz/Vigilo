"""DVRIP protocol: password hash and the frame parser (split, merged, resync, H.265, audio)."""
import struct

import pytest

from vigilo_app.dvrip import DvripClient, sofia_hash


def test_sofia_hash_of_empty_password():
    # well-known value: the hash every XMeye camera expects for an empty password
    assert sofia_hash("") == "tlJwpbo6"


def test_sofia_hash_shape():
    h = sofia_hash("una password con spazi è ok")
    assert len(h) == 8 and h.isalnum()
    assert h == sofia_hash("una password con spazi è ok") != sofia_hash("other")


class FakeSock:
    def __init__(self, packets):
        self.buf = b"".join(packets)
        self.sent = []

    def recv(self, n):
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def sendall(self, data):
        self.sent.append(data)


def pkt(msgid, payload, session=0x1A):
    return DvripClient.HDR.pack(0xFF, 1, session, 0, msgid, len(payload)) + payload


def iframe(data, media=2, fps=15):
    return b"\x00\x00\x01\xfc" + bytes([media, fps, 0, 0]) + struct.pack("<II", 0, len(data)) + data


def pframe(data):
    return b"\x00\x00\x01\xfd" + struct.pack("<I", len(data)) + data


def audio(data, media=0x0E, rate=2):
    return b"\x00\x00\x01\xfa" + bytes([media, rate]) + struct.pack("<H", len(data)) + data


def frames_of(packets):
    c = DvripClient("camera")
    c.sock = FakeSock(packets)
    out = []
    with pytest.raises(ConnectionError):     # the fake socket ends: "connection closed"
        for f in c.frames():
            out.append(f)
    return out, c


def test_frame_split_over_packets_and_frames_sharing_a_packet():
    key = b"\x00\x00\x00\x01\x67" + bytes(range(256)) * 40     # bigger than one packet
    blob = iframe(key)
    out, c = frames_of([
        pkt(1412, blob[:700]), pkt(1412, blob[700:5000]), pkt(1412, blob[5000:]),
        pkt(1007, b'{"Name": "KeepAlive", "Ret": 100}\n\x00'),       # not video: ignored
        pkt(1412, pframe(b"P1") + audio(b"\xd5" * 320) + pframe(b"P2")),
    ])
    assert [(f[0], f[1]) for f in out] == [("video", True), ("video", False), ("audio", False), ("video", False)]
    assert out[0][2:] == ("h264", 15, key)
    assert out[1][4] == b"P1" and out[3][4] == b"P2"
    assert out[2][2:4] == (0x0E, 2) and out[2][4] == b"\xd5" * 320
    assert c.session == 0x1A


def test_hevc_is_detected_and_kept_for_p_frames():
    out, _ = frames_of([pkt(1412, iframe(b"K" * 10, media=3) + pframe(b"P"))])
    assert [f[2] for f in out] == ["hevc", "hevc"]


def test_resync_after_garbage():
    out, _ = frames_of([pkt(1412, b"\x12\x34 not a frame \xff" + iframe(b"KEY") + pframe(b"P"))])
    assert [f[4] for f in out] == [b"KEY", b"P"]


def test_absurd_frame_size_is_skipped():
    bad = b"\x00\x00\x01\xfd" + struct.pack("<I", 0x7FFFFFFF)
    out, _ = frames_of([pkt(1412, bad + iframe(b"OK"))])
    assert [f[4] for f in out] == [b"OK"]
