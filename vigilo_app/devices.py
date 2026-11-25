"""
Camera clients by connection type, PTZ controller and the connection test.
"""

import time
import queue
import threading

from i18n import tr
from .common import cam_url, KIND_CLOUD, KIND_NATIVE, KIND_RTSP, open_capture, port_open
from .dvrip import DvripAuthError, DvripClient, DvripError
from .cloud import CloudClient, find_cloud_sdk, SDK_HELP


def stream_client(cam, timeout=8.0, want_ptz=False):
    """Client for raw video: native protocol on the LAN, or the cloud."""
    if cam.get("kind") == KIND_CLOUD:
        return CloudClient(cam, want_ptz=want_ptz)
    return DvripClient(cam.get("ip", ""), cam.get("dvrip_port", 34567), cam.get("user", "admin"),
                       cam.get("password", ""), timeout=timeout)


def detect_ptz(cam):
    """Ask the camera (native protocol) whether it is motorized. None if unknown."""
    c = DvripClient(cam.get("ip", ""), cam.get("dvrip_port", 34567), cam.get("user", "admin"),
                    cam.get("password", ""), timeout=5)
    try:
        c.connect()
        return c.supports_ptz()
    except Exception:
        return None
    finally:
        c.close()


class PtzController:
    """PTZ commands on a dedicated thread, reusing the connection."""

    def __init__(self, cam):
        self.cam = cam
        self.q = queue.Queue()
        self.client = None
        self.last_use = 0.0
        self.moving = None
        self.error = ""
        self.last_cmd_t = 0.0
        threading.Thread(target=self._run, daemon=True).start()

    def _get_client(self):
        # cloud connections are slow to open: keep them open longer
        idle = 180 if self.cam.get("kind") == KIND_CLOUD else 20
        if self.client and time.time() - self.last_use < idle:
            return self.client
        if self.client:
            self.client.close()
        c = stream_client(self.cam, timeout=5)
        self.client = c
        c.connect()
        self.client = c
        return c

    def _run(self):
        while True:
            cmd, preset = self.q.get()
            if cmd is None:
                break
            for _ in range(2):
                try:
                    self._get_client().ptz(cmd, preset, channel=int(self.cam.get("channel", 1)) - 1)
                    self.last_use = time.time()
                    self.error = ""
                    break
                except Exception as e:
                    self.error = str(e)
                    if self.client:
                        self.client.close()
                    self.client = None
        if self.client:
            self.client.close()

    def start(self, direction):
        self.last_cmd_t = time.time()
        if self.moving == direction:
            return
        if self.moving:
            self.q.put((self.moving, -1))
        self.moving = direction
        self.q.put((direction, 65535))

    def stop(self):
        self.last_cmd_t = time.time()
        if self.moving:
            self.q.put((self.moving, -1))
            self.moving = None

    def goto(self, n):
        self.last_cmd_t = time.time()
        self.q.put(("GotoPreset", int(n)))

    def save(self, n):
        self.q.put(("SetPreset", int(n)))

    def clear(self, n):
        self.q.put(("ClearPreset", int(n)))

    def close(self):
        self.stop()
        self.q.put((None, None))


# ----------------------------------------------------------------------------- connection test

def _test_cloud(cam, extra):
    if not find_cloud_sdk(refresh=True):
        return False, tr("NetSdk.dll not found.") + "\n" + tr(SDK_HELP), False, extra
    if not cam.get("cloud_id", "").strip():
        return False, tr("Enter the camera serial number"), False, extra
    c = CloudClient(cam, want_ptz=True)
    timer = threading.Timer(90, c.close)   # do not hang if the cloud does not answer
    timer.start()
    try:
        c.connect()
        extra["ptz"] = c.supports_ptz()
        c.start_stream(int(cam.get("channel", 1)) - 1, "Main")
        t0 = time.time()
        for kind_, key, codec, fps, _ in c.frames():
            if kind_ == "video" and key:
                lim = c.info.get("limits") or [0, 0, 0, 0]
                note = ""
                if 0 < lim[1] < 10:
                    note += " · " + tr("the cloud allows the preview stream only")
                if 0 < lim[2] < 10000:
                    note += " · " + tr("the cloud limits viewing to {n} min").format(n=lim[2])
                model = c.info.get("model") or ""
                vc = "H.265" if codec == "hevc" else "H.264"
                return (True, tr("{codec} video via cloud").format(codec=vc)
                        + (" · " + model if model else "") + note, False, extra)
            if time.time() - t0 > 25:
                break
        return False, tr("Connected via cloud, but no video arrives"), False, extra
    except DvripAuthError as e:
        return False, str(e), True, extra
    except DvripError as e:
        return False, str(e), False, extra
    except OSError:
        return False, tr("The cloud connection did not answer in time"), False, extra
    finally:
        timer.cancel()
        c.close()


def test_camera(cam):
    """Returns (ok, message, password_error, extra) - extra = {"ptz": True/False/None, "audio": ...}."""
    kind = cam.get("kind")
    extra = {"ptz": None}
    if kind == KIND_CLOUD:
        return _test_cloud(cam, extra)
    if kind == KIND_NATIVE:
        ip, port = cam.get("ip", ""), cam.get("dvrip_port", 34567)
        if not port_open(ip, port):
            return False, tr("Port {port} is closed or the camera does not answer").format(port=port), False, extra
        c = DvripClient(ip, port, cam.get("user", "admin"), cam.get("password", ""))
        try:
            c.connect()
            try:
                extra["ptz"] = c.supports_ptz()
            except Exception:
                pass
            c.start_stream(int(cam.get("channel", 1)) - 1, "Main")
            t0 = time.time()
            for kind_, key, codec, fps, _ in c.frames():
                if kind_ == "audio":
                    extra["audio"] = True
                if kind_ == "video" and key:
                    vc = "H.265" if codec == "hevc" else "H.264"
                    return True, tr("{codec} video · {fps} fps").format(codec=vc, fps=fps), False, extra
                if time.time() - t0 > 10:
                    break
            return False, tr("Connected, but no video arrives"), False, extra
        except DvripAuthError as e:
            return False, str(e), True, extra
        except DvripError as e:
            return False, str(e), False, extra
        except OSError:
            return False, tr("The camera does not answer"), False, extra
        finally:
            c.close()
    # RTSP
    if kind == KIND_RTSP and not port_open(cam.get("ip", ""), cam.get("port", 554)):
        return False, tr("Port {port} is closed (no RTSP)").format(port=cam.get("port", 554)), False, extra
    res = []
    for sub, label_ in ((False, tr("Main")), (True, tr("Preview"))):
        cap = open_capture(cam_url(cam, sub))
        ok, fr = cap.read() if cap.isOpened() else (False, None)
        cap.release()
        res.append((label_, fr.shape[1], fr.shape[0]) if ok and fr is not None else None)
        if res[0] is None:
            break
    if res[0] is None:
        return False, tr("No video: check user name and password"), False, extra
    if kind == KIND_RTSP and port_open(cam.get("ip", ""), cam.get("dvrip_port", 34567), 1.5):
        extra["ptz"] = detect_ptz(cam)
    msg = " · ".join(f"{r[0]} {r[1]}x{r[2]}" for r in res if r)
    return True, msg, False, extra
