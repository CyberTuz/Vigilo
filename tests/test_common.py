"""Configuration and small helpers."""
import json

from vigilo_app import common
from vigilo_app.common import KIND_CLOUD, KIND_CUSTOM, KIND_NATIVE, KIND_RTSP, cam_address, cam_url, fmt_gb, safe_name


def test_safe_name():
    assert safe_name("Cancello / ingresso") == "Cancello _ ingresso"
    assert safe_name("") == "Camera"
    assert safe_name("Garage-2_sud") == "Garage-2_sud"


def test_cam_url():
    cam = {"kind": KIND_RTSP, "ip": "10.0.0.5", "port": 554, "user": "admin", "password": "pw", "channel": 1}
    assert cam_url(cam) == "rtsp://10.0.0.5:554/user=admin&password=pw&channel=1&stream=0.sdp?real_stream"
    assert "stream=1.sdp" in cam_url(cam, sub=True)
    custom = {"kind": KIND_CUSTOM, "url_main": "rtsp://h/main", "url_sub": ""}
    assert cam_url(custom, sub=True) == "rtsp://h/main"        # no secondary URL: main stream


def test_cam_address():
    assert cam_address({"kind": KIND_NATIVE, "ip": "10.0.0.5", "dvrip_port": 34567}) == "10.0.0.5:34567"
    assert cam_address({"kind": KIND_CLOUD, "cloud_id": "abc123"}) == "abc123"
    assert cam_address({"kind": KIND_CUSTOM, "url_main": "rtsp://user:pw@cam.local:8554/x"}) == "cam.local:8554"


def test_fmt_gb():
    assert fmt_gb(5 * 1024**3) == "5.0 GB"
    assert fmt_gb(250 * 1024**3) == "250 GB"


def test_config_round_trip_and_migrations(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(common, "CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setattr(common, "LEGACY_CONFIG_DIR", str(tmp_path / "legacy"))
    (tmp_path / "config.json").write_text(json.dumps({
        "settings": {"motion_sens": "media"},          # Italian value of the early versions
        "cameras": [{"name": "Cortile", "ip": "10.0.0.7"}],
    }), encoding="utf-8")
    cfg = common.load_config()
    s = cfg["settings"]
    assert s["motion_sens"] == "medium"
    assert s["rec_dir"].endswith("Telecamere")         # old installs keep their recordings folder
    assert s["tray_on_close"] is True and s["keep_awake"] is True
    c = cfg["cameras"][0]
    assert (c["kind"], c["port"], c["dvrip_port"], c["user"]) == (KIND_RTSP, 554, 34567, "admin")
    s["keep_awake"] = False
    common.save_config(cfg)
    assert common.load_config()["settings"]["keep_awake"] is False
    assert not (tmp_path / "config.json.tmp").exists()
