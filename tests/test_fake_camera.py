"""End-to-end tests against the fake ICSee camera: login, video, audio, connection test, recording."""
import time
import subprocess

import pytest

from conftest import FAKE_PASSWORD
from vigilo_app.audio import dvrip_audio_format
from vigilo_app.common import FFMPEG, KIND_NATIVE
from vigilo_app.devices import test_camera as connection_test
from vigilo_app.dvrip import DvripAuthError, DvripClient
from vigilo_app.recorder import Recorder

pytestmark = pytest.mark.e2e


def cam(port, password=FAKE_PASSWORD):
    return {"id": "c1", "name": "Test cam", "kind": KIND_NATIVE, "ip": "127.0.0.1", "dvrip_port": port,
            "user": "admin", "password": password, "channel": 1}


def test_login_video_and_audio(fake_camera):
    c = DvripClient("127.0.0.1", fake_camera, "admin", FAKE_PASSWORD, timeout=5)
    c.connect()
    try:
        assert c.supports_ptz() is False
        c.start_stream(0, "Main")
        key = sound = None
        t0 = time.time()
        for kind, is_key, codec, fps, data in c.frames():
            if kind == "video" and is_key and key is None:
                key = (codec, fps, data[:4])
            if kind == "audio" and sound is None:
                sound = dvrip_audio_format(codec, fps)
            if (key and sound) or time.time() - t0 > 10:
                break
        assert key == ("h264", 15, b"\x00\x00\x00\x01")
        assert sound == ("alaw", 8000)
    finally:
        c.close()


def test_wrong_password_is_an_auth_error(fake_camera):
    c = DvripClient("127.0.0.1", fake_camera, "admin", "wrong", timeout=5)
    try:
        with pytest.raises(DvripAuthError):
            c.connect()
    finally:
        c.close()


def test_connection_test(fake_camera):
    ok, msg, auth_error, extra = connection_test(cam(fake_camera))
    assert ok, msg
    assert "H.264" in msg and not auth_error and extra["ptz"] is False


class FakeApp:
    def __init__(self, rec_dir):
        self.settings = {"rec_dir": str(rec_dir), "segment_min": 1, "audio": True}

    def motion_mode_for(self, cam):
        return False


def test_native_recording_with_audio(fake_camera, tmp_path):
    r = Recorder(FakeApp(tmp_path), cam(fake_camera))
    r.start()
    try:
        t0 = time.time()
        while time.time() - t0 < 15 and not r.active:
            time.sleep(0.2)
        assert r.active, list(r.errors)
        time.sleep(4)
    finally:
        r.stop()
    files = sorted((tmp_path / "Test cam").glob("Test cam_*.mkv"))
    assert files, list(r.errors)
    info = subprocess.run([FFMPEG, "-hide_banner", "-i", str(files[0])], capture_output=True, text=True).stderr
    assert "Video: h264" in info, info
    assert "Audio: aac" in info, info
