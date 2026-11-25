"""
Live view: one thread per camera that keeps only the latest frame.

Decoding happens on the graphics card (GPU) when it can (see hwaccel): RTSP cameras then use an
ffmpeg decoder instead of OpenCV, native cameras pass the GPU options to their ffmpeg decoder.
A camera whose GPU decoder gives no picture is switched to software decoding.
"""

import time
import threading
import subprocess

import numpy as np

from i18n import tr
from . import hwaccel
from .common import (
    applog, cam_url, FFMPEG, kill_with_app, KIND_CLOUD, MOTION_SENS, NOWIN, open_capture, STREAM_KINDS,
)
from .dvrip import DvripAuthError, DvripError
from .devices import stream_client
from .motion import MotionDetector
from .audio import decode_g711, dvrip_audio_format


def tile_filter(w, h):
    """ffmpeg filter: fit the picture in a w x h box (black bars), the size the UI reads."""
    return f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"


# ----------------------------------------------------------------------------- live view

class BaseViewer(threading.Thread):
    """Reads the stream on its own thread and keeps only the latest frame."""

    def __init__(self, cam, app=None):
        super().__init__(daemon=True)
        self.cam = cam
        self.app = app
        self.sub = True
        self.running = True
        self.frame = None
        self.frame_id = 0
        self.last_frame_t = 0.0
        self.status = tr("Connecting...")
        self.has_audio = None          # True once audio frames have been seen
        self.lock = threading.Lock()
        self.det = MotionDetector()
        self.last_motion = 0.0
        self.ev_start = None
        self.motion_mute_until = 0.0
        self.decoder = ""              # "gpu" or "cpu" while a decoder runs (shown in the UI)
        self.reload_decoder = False    # the GPU setting changed: start the decoder again
        self.gpu_failed = False        # the GPU gave no picture for this camera: software from now on

    def _hw_args(self, codec=None):
        if self.gpu_failed:
            return []
        return hwaccel.decode_args(self.app.settings if self.app is not None else {}, codec)

    def _sleep(self, sec):
        end = time.time() + sec
        while self.running and time.time() < end:
            time.sleep(0.2)

    def _set_frame(self, fr):
        with self.lock:
            self.frame = fr
            self.frame_id += 1
            self.last_frame_t = time.time()
        self.status = ""
        if self.cam.get("motion", True) and self.app is not None:
            try:
                self._motion(fr)
            except Exception:
                pass

    def _motion(self, fr):
        now = time.time()
        r = self.det.feed(fr, now)
        if r is None:
            return
        if now < self.motion_mute_until:   # the camera is moving (PTZ)
            self.det.reset()
            return
        thr = MOTION_SENS.get(self.app.settings.get("motion_sens", "medium"), 0.012)
        if r > thr:
            self.last_motion = now
            if self.ev_start is None:
                self.ev_start = now
        elif self.ev_start is not None and now - self.last_motion > 8:
            self.app.motion_event(self.cam, self.ev_start, max(self.last_motion, self.ev_start + 1))
            self.ev_start = None

    def get(self):
        with self.lock:
            return self.frame, self.frame_id

    def stop(self):
        self.running = False
        if self.ev_start is not None and self.app is not None:
            self.app.motion_event(self.cam, self.ev_start, max(self.last_motion, self.ev_start + 1))
            self.ev_start = None


class RtspViewer(BaseViewer):
    """RTSP camera (or any URL): ffmpeg on the GPU when possible, otherwise OpenCV in software."""

    def __init__(self, cam, app=None):
        super().__init__(cam, app)
        self.proc = None

    def run(self):
        while self.running:
            want_sub = self.sub
            if not self.status:
                self.status = tr("Connecting...")
            self.reload_decoder = False
            url = cam_url(self.cam, want_sub)
            hw = self._hw_args()
            outcome = self._run_ffmpeg(url, want_sub, hw) if hw else self._run_opencv(url, want_sub)[0]
            self.decoder = ""
            if not self.running or self.sub != want_sub or outcome == "reload":
                continue
            if outcome == "unreachable":
                self.status = tr("Unreachable - retrying...")
                self._sleep(5)
            else:
                self.status = tr("Signal lost - retrying...")
                self._sleep(3)

    def _keep_going(self, want_sub):
        return self.running and self.sub == want_sub and not self.reload_decoder

    def _run_opencv(self, url, want_sub):
        """Software decoding. Returns (outcome, frames): outcome "unreachable" | "lost" | "reload"."""
        cap = open_capture(url)
        if not cap.isOpened():
            cap.release()
            return "unreachable", 0
        self.decoder = "cpu"
        fails = frames = 0
        while self._keep_going(want_sub):
            ok, fr = cap.read()
            if not ok or fr is None:
                fails += 1
                if fails > 10:
                    break
                time.sleep(0.1)
                continue
            fails = 0
            frames += 1
            self._set_frame(fr)
        cap.release()
        return ("reload" if self.reload_decoder else "lost"), frames

    def _run_ffmpeg(self, url, want_sub, hw):
        """GPU decoding with ffmpeg (decoded frames come back scaled to the tile box)."""
        w, h = (960, 540) if want_sub else (1920, 1080)
        # nobuffer drops what is read while ffmpeg analyses the stream: keep that analysis short (1 s)
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "quiet", "-fflags", "nobuffer", "-flags", "low_delay",
               "-probesize", "1000000", "-analyzeduration", "1000000"]
        if url.lower().startswith("rtsp"):
            cmd += ["-rtsp_transport", "tcp", "-timeout", "10000000"]
        cmd += hw + ["-i", url, "-an", "-sn", "-vf", tile_filter(w, h), "-fps_mode", "passthrough",
                     "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1"]
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, creationflags=NOWIN)
        except OSError:
            return "unreachable"
        kill_with_app(p)
        self.proc = p
        self.decoder = "gpu"
        n, frames = w * h * 3, 0
        try:
            while self._keep_going(want_sub):
                b = p.stdout.read(n)
                if not b or len(b) < n:
                    break
                frames += 1
                self._set_frame(np.frombuffer(b, np.uint8).reshape(h, w, 3))
        except (OSError, ValueError, AttributeError):
            pass
        finally:
            self._kill_proc()
        if self.reload_decoder:
            return "reload"
        if frames == 0 and self.running and self.sub == want_sub:
            # no picture at all: is the camera unreachable, or is it the GPU? software decoding tells
            outcome, sw_frames = self._run_opencv(url, want_sub)
            if sw_frames:
                self.gpu_failed = True
                applog(f"{self.cam.get('name', '?')}: no picture with GPU decoding, using software decoding")
            return outcome
        return "lost"

    def _kill_proc(self):
        p, self.proc = self.proc, None
        if p:
            try:
                p.kill()
            except Exception:
                pass

    def stop(self):
        super().stop()
        self._kill_proc()


class NativeViewer(BaseViewer):
    """Native protocol: receives raw H.264/H.265 and decodes it with ffmpeg."""

    def __init__(self, cam, app=None):
        super().__init__(cam, app)
        self.client = None
        self.proc = None
        self.no_sub = False
        self._dec = {"frames": 0, "t0": 0.0}     # pictures from the current decoder, start time

    def _start_decoder(self, codec, w, h):
        hw = self._hw_args(codec)
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "quiet", "-fflags", "nobuffer", "-flags", "low_delay",
               "-probesize", "65536", "-analyzeduration", "500000"] + hw + [
               "-f", codec, "-i", "pipe:0", "-an", "-vf", tile_filter(w, h), "-fps_mode", "passthrough",
               "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1"]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, creationflags=NOWIN)
        kill_with_app(p)
        stats = {"frames": 0, "t0": time.time()}
        self._dec = stats
        self.decoder = "gpu" if hw else "cpu"
        threading.Thread(target=self._reader, args=(p, w, h, stats), daemon=True).start()
        return p

    def _reader(self, p, w, h, stats):
        n = w * h * 3
        while True:
            b = p.stdout.read(n)
            if not b or len(b) < n:
                break
            stats["frames"] += 1
            self._set_frame(np.frombuffer(b, np.uint8).reshape(h, w, 3))

    def _gpu_stalled(self):
        """The GPU decoder exited, or gave no picture within hwaccel.GPU_GRACE seconds."""
        if self.decoder != "gpu" or self._dec["frames"]:
            return False
        p = self.proc
        return p is None or p.poll() is not None or time.time() - self._dec["t0"] > hwaccel.GPU_GRACE

    def _use_software(self):
        applog(f"{self.cam.get('name', '?')}: no picture with GPU decoding, using software decoding")
        self.gpu_failed = True
        self._kill_decoder()

    def _kill_decoder(self):
        p, self.proc = self.proc, None
        self.decoder = ""
        if p:
            try:
                p.stdin.close()
            except Exception:
                pass
            try:
                p.kill()
            except Exception:
                pass

    def _cleanup(self):
        c, self.client = self.client, None
        if c:
            c.close()
        self._kill_decoder()

    def run(self):
        cam = self.cam
        while self.running:
            want_sub = self.sub
            stream = "Extra1" if (want_sub and not self.no_sub) else "Main"
            bw, bh = (960, 540) if want_sub else (1920, 1080)
            delay = 4
            got_video = False
            if not self.status:
                self.status = tr("Connecting...")
            try:
                c = stream_client(cam)
                self.client = c
                if cam.get("kind") == KIND_CLOUD:
                    self.status = tr("Connecting via cloud...")
                c.connect()
                try:
                    c.start_stream(int(cam.get("channel", 1)) - 1, stream)
                except DvripAuthError:
                    raise
                except DvripError:
                    if stream == "Extra1":   # no secondary stream: use the main one
                        self.no_sub = True
                        continue
                    raise
                codec = None
                for kind, key, fcodec, fps, data in c.frames():
                    if not self.running or self.sub != want_sub:
                        break
                    if self.reload_decoder:      # GPU setting changed: new decoder at the next key frame
                        self.reload_decoder = False
                        self._kill_decoder()
                    if kind == "audio":
                        self.has_audio = True
                        app = self.app
                        if app is not None and app.audio.owner == cam["id"]:
                            app.audio.push(cam["id"], decode_g711(data, fcodec),
                                           dvrip_audio_format(fcodec, fps)[1])
                        continue
                    if kind != "video":
                        continue
                    if self.proc is None:
                        if not key:
                            continue
                        codec = fcodec
                        self.proc = self._start_decoder(codec, bw, bh)
                    elif fcodec != codec:
                        break
                    try:
                        self.proc.stdin.write(data)
                        self.proc.stdin.flush()
                    except (OSError, ValueError, AttributeError):
                        # the decoder is gone. A GPU decoder that never gave a picture failed: software
                        # (do not wait for poll(): the pipe breaks before the process is marked as ended)
                        if self.decoder == "gpu" and not self._dec["frames"]:
                            self._use_software()
                            continue
                        break
                    if self._gpu_stalled():
                        self._use_software()     # wait for the next key frame, decode in software
                        continue
                    got_video = True
            except DvripAuthError as e:
                self.status = f"{e} · " + tr("retrying in 1 minute")
                delay = 60  # avoid locking the user out with too many attempts
            except DvripError as e:
                self.status = f"{e} · " + tr("retrying...")
                if cam.get("kind") == KIND_CLOUD:
                    delay = 15   # do not hammer the cloud server
            except (OSError, ConnectionError):
                self.status = tr("Signal lost - retrying...") if got_video else tr("Unreachable - retrying...")
            finally:
                self._cleanup()
            if self.running and self.sub == want_sub:
                if not self.status:
                    self.status = tr("Signal lost - retrying...")
                self._sleep(delay)

    def stop(self):
        super().stop()
        c = self.client
        if c:
            c.close()


def make_viewer(cam, app=None):
    return NativeViewer(cam, app) if cam.get("kind") in STREAM_KINDS else RtspViewer(cam, app)
