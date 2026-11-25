"""GPU (hardware) decoding: options, and live view / playback with the GPU and with its fallback."""
import time
import datetime
import subprocess

import pytest

from vigilo_app import hwaccel
from vigilo_app.common import FFMPEG, KIND_CUSTOM, KIND_NATIVE
from vigilo_app.player import Player
from vigilo_app.viewers import NativeViewer, RtspViewer
from conftest import FAKE_PASSWORD

GPU = hwaccel.available()
BROKEN = ["-hwaccel", "d3d11va", "-this_option_does_not_exist", "1"]     # makes the GPU decoder fail


def test_probe_result_shape():
    p = hwaccel.probe()
    assert set(p) == {"h264", "hevc"} and all(isinstance(v, bool) for v in p.values())
    assert isinstance(hwaccel.gpu_name(), str)


def test_decode_args(monkeypatch):
    monkeypatch.setattr(hwaccel, "probe", lambda refresh=False: {"h264": True, "hevc": False})
    gpu = ["-hwaccel", hwaccel.HWACCEL]
    assert hwaccel.decode_args({}) == gpu                         # codec not known yet
    assert hwaccel.decode_args({"hw_decode": "auto"}, "h264") == gpu
    assert hwaccel.decode_args({}, "hevc") == []                  # this GPU cannot do H.265
    assert hwaccel.decode_args({"hw_decode": "off"}, "h264") == []
    monkeypatch.setattr(hwaccel, "probe", lambda refresh=False: {"h264": False, "hevc": False})
    assert hwaccel.decode_args({}) == []


def wait_frame(v, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        frame, fid = v.get()
        if frame is not None:
            return frame
        time.sleep(0.1)
    return None


def native_cam(port):
    return {"id": "n1", "name": "Native", "kind": KIND_NATIVE, "ip": "127.0.0.1", "dvrip_port": port,
            "user": "admin", "password": FAKE_PASSWORD, "channel": 1}


@pytest.mark.e2e
def test_native_viewer_decodes_on_the_gpu(fake_camera):
    v = NativeViewer(native_cam(fake_camera))
    v.start()
    try:
        frame = wait_frame(v)
        assert frame is not None and frame.shape == (540, 960, 3)
        assert v.decoder == ("gpu" if GPU else "cpu")
    finally:
        v.stop()


@pytest.mark.e2e
def test_native_viewer_falls_back_to_software(fake_camera, monkeypatch):
    monkeypatch.setattr(hwaccel, "decode_args", lambda settings, codec=None: list(BROKEN))
    v = NativeViewer(native_cam(fake_camera))
    v.start()
    try:
        assert wait_frame(v) is not None
        assert v.gpu_failed is True and v.decoder == "cpu"
    finally:
        v.stop()


class FakeApp:
    def __init__(self):
        self.settings = {"hw_decode": "auto"}
        self.audio = type("Audio", (), {"owner": None})()


@pytest.mark.e2e
@pytest.mark.skipif(not GPU, reason="needs a GPU that decodes video")
def test_switching_the_setting_while_running(fake_camera):
    app = FakeApp()
    cam = dict(native_cam(fake_camera), motion=False)
    v = NativeViewer(cam, app)
    v.start()
    try:
        assert wait_frame(v) is not None and v.decoder == "gpu"
        app.settings["hw_decode"] = "off"         # what App.apply_settings does
        v.reload_decoder = True
        t0 = time.time()
        while v.decoder != "cpu" and time.time() - t0 < 10:
            time.sleep(0.1)
        assert v.decoder == "cpu"
        fid = v.get()[1]
        time.sleep(1.5)
        assert v.get()[1] > fid                   # still showing video
    finally:
        v.stop()


def url_cam(path):
    return {"id": "r1", "name": "Url", "kind": KIND_CUSTOM, "url_main": str(path), "url_sub": ""}


@pytest.mark.e2e
def test_rtsp_viewer_uses_ffmpeg_on_the_gpu(h264_file):
    v = RtspViewer(url_cam(h264_file))      # a file instead of rtsp://: same code path
    v.start()
    try:
        frame = wait_frame(v)
        assert frame is not None
        if GPU:
            assert frame.shape == (540, 960, 3) and not v.gpu_failed
    finally:
        v.stop()


@pytest.mark.e2e
def test_rtsp_viewer_falls_back_to_opencv(h264_file, monkeypatch):
    monkeypatch.setattr(hwaccel, "decode_args", lambda settings, codec=None: list(BROKEN))
    v = RtspViewer(url_cam(h264_file))
    v.start()
    try:
        frame = wait_frame(v)
        assert frame is not None and frame.shape == (240, 320, 3)    # OpenCV: the camera's own size
        t0 = time.time()
        while not v.gpu_failed and time.time() - t0 < 10:
            time.sleep(0.1)
        assert v.gpu_failed is True
    finally:
        v.stop()


@pytest.mark.e2e
def test_player_decodes_a_recording_on_the_gpu(tmp_path):
    rec = tmp_path / "Cam_2026-11-25_10-00-00.mkv"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=320x240:rate=15", "-t", "4", "-c:v", "libx264", "-g", "15", str(rec)],
                   check=True)
    t0 = datetime.datetime(2026, 11, 25, 10, 0, 0)
    p = Player(640, 360)
    p.hw_args = lambda: hwaccel.decode_args({})
    try:
        p.set_segments([(t0, t0 + datetime.timedelta(seconds=4), str(rec), rec.stat().st_size)])
        p.playing = True
        p.seek(t0 + datetime.timedelta(seconds=1))
        start = time.time()
        while p.frame is None and time.time() - start < 15:
            time.sleep(0.1)
        assert p.frame is not None and p.frame.shape == (360, 640, 3)
        assert p.decoder == ("gpu" if GPU else "cpu")
    finally:
        p.close()
