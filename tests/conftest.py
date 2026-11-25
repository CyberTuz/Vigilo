import os
import sys
import socket
import tempfile
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Never touch the real %APPDATA%\Vigilo while testing (must be set before vigilo_app is imported)
os.environ["VIGILO_CONFIG_DIR"] = tempfile.mkdtemp(prefix="vigilo-test-config-")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FAKE_PASSWORD = "test-pw"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def h264_file(tmp_path_factory):
    """A 4-second 320x240 H.264 clip with access unit delimiters (needed by the fake camera)."""
    from vigilo_app.common import FFMPEG
    path = tmp_path_factory.mktemp("media") / "test.h264"
    r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                        "-i", "testsrc2=size=320x240:rate=15", "-t", "4", "-c:v", "libx264", "-g", "15",
                        "-bsf:v", "h264_metadata=aud=insert", "-f", "h264", str(path)],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not path.exists():
        pytest.skip("ffmpeg cannot create the test video: " + r.stderr[-200:])
    return path


@pytest.fixture(scope="module")
def fake_camera(h264_file):
    """Start tools/fake_dvrip.py (video + G.711 audio) on a free port; yields the port."""
    port = free_port()
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "fake_dvrip.py"), str(h264_file), str(port),
                          FAKE_PASSWORD], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(5):
            line = p.stdout.readline()
            if not line or line.startswith("listening"):
                break
        if p.poll() is not None:
            pytest.skip("the fake camera did not start")
        yield port
    finally:
        p.kill()
        p.wait(5)
