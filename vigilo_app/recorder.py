"""
Recording to disk with ffmpeg, without re-encoding the video.
"""

import os
import time
import queue
import socket
import threading
import subprocess
from collections import deque

from .common import cam_url, FFMPEG, kill_with_app, KIND_CLOUD, NOWIN, safe_name, STREAM_KINDS
from .dvrip import DvripAuthError, DvripError
from .devices import stream_client
from .audio import dvrip_audio_format


# ----------------------------------------------------------------------------- recording

class Recorder:
    """Records the main stream to disk with ffmpeg (video copied without re-encoding).
    In motion mode it records 1-minute files and App.prune_motion() deletes the ones
    without motion, which also gives a few seconds of pre-recording."""

    def __init__(self, app, cam):
        self.app = app
        self.cam = cam
        self.proc = None
        self.client = None
        self.want = False
        self.thread = None
        self.errors = deque(maxlen=5)
        self.last_write = 0.0   # last time frames were written
        self.retry_delay = 5
        self.audio_sock = None

    @property
    def active(self):
        """True only when it is really writing video to disk."""
        p = self.proc
        return p is not None and p.poll() is None and time.time() - self.last_write < 15

    def start(self):
        if self.want:
            return
        self.want = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _sleep(self, sec):
        end = time.time() + sec
        while self.want and time.time() < end:
            time.sleep(0.2)

    def segment_seconds(self):
        if self.app.motion_mode_for(self.cam):
            return 60
        return int(self.app.settings["segment_min"]) * 60

    def _output_args(self):
        s = self.app.settings
        name = safe_name(self.cam["name"])
        folder = os.path.join(s["rec_dir"], name)
        os.makedirs(folder, exist_ok=True)
        pattern = os.path.join(folder, name + "_%Y-%m-%d_%H-%M-%S.mkv")
        return ["-f", "segment", "-segment_time", str(self.segment_seconds()),
                "-segment_format", "matroska", "-reset_timestamps", "1", "-strftime", "1", pattern]

    def _loop(self):
        while self.want:
            self.retry_delay = 5
            try:
                if self.cam.get("kind") in STREAM_KINDS:
                    self._run_native()
                else:
                    self._run_rtsp()
            except Exception as e:
                self.errors.append(str(e))
            self.proc = None
            if self.want:
                self._sleep(self.retry_delay)  # camera off / network down: retry

    def _read_stderr(self, proc):
        for line in proc.stderr:
            txt = line.decode("utf-8", "ignore").strip()
            if txt:
                self.errors.append(txt)

    def _read_progress(self, proc):
        last_frame = -1
        for line in proc.stdout:
            if line.startswith(b"frame="):
                try:
                    n = int(line[6:].strip())
                except ValueError:
                    continue
                if n > last_frame:
                    last_frame = n
                    self.last_write = time.time()

    def _run_rtsp(self):
        url = cam_url(self.cam, False)
        cmd = [FFMPEG, "-hide_banner", "-nostats", "-loglevel", "error", "-progress", "pipe:1"]
        if url.lower().startswith("rtsp"):
            cmd += ["-rtsp_transport", "tcp", "-timeout", "10000000"]
        cmd += ["-fflags", "+genpts", "-i", url, "-map", "0:v:0"]
        if self.app.settings.get("audio", True):
            # cameras usually send G.711, which Matroska cannot store: re-encode it to small AAC
            cmd += ["-map", "0:a:0?", "-c:v", "copy", "-c:a", "aac", "-b:a", "48k", "-ac", "1"]
        else:
            cmd += ["-c", "copy"]
        cmd += self._output_args()
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, creationflags=NOWIN)
        kill_with_app(self.proc)
        threading.Thread(target=self._read_progress, args=(self.proc,), daemon=True).start()
        self._read_stderr(self.proc)
        self.proc.wait()

    def _start_native_ffmpeg(self, codec, audio_fmt):
        """ffmpeg for the native protocol: video on stdin and, if present, audio on a local
        TCP socket (ffmpeg connects to us), muxed into the same segmented files."""
        cmd = [FFMPEG, "-hide_banner", "-nostats", "-loglevel", "error",
               "-thread_queue_size", "512", "-use_wallclock_as_timestamps", "1", "-fflags", "+genpts",
               "-f", codec, "-i", "pipe:0"]
        server = None
        if audio_fmt:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            server.settimeout(20)
            port = server.getsockname()[1]
            # -copyts: both inputs keep their wall-clock timestamps, so the segment muxer's
            # timestamp reset applies equally to audio and video (otherwise audio stays at epoch time)
            cmd += ["-thread_queue_size", "512", "-use_wallclock_as_timestamps", "1",
                    "-f", audio_fmt[0], "-ar", str(audio_fmt[1]), "-ac", "1", "-i", f"tcp://127.0.0.1:{port}",
                    "-copyts", "-avoid_negative_ts", "make_zero",
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "32k"]
        else:
            cmd += ["-map", "0:v:0", "-c", "copy"]
        proc = subprocess.Popen(cmd + self._output_args(), stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, creationflags=NOWIN)
        kill_with_app(proc)
        threading.Thread(target=self._read_stderr, args=(proc,), daemon=True).start()
        if server is not None:
            def accept():
                try:
                    conn, _ = server.accept()
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.audio_sock = conn
                except OSError:
                    pass
                finally:
                    server.close()
            threading.Thread(target=accept, daemon=True).start()
        return proc

    def _pump(self, q, write, on_ok=None):
        """Writer thread: video and audio go through separate queues, so a stalled input in
        ffmpeg (for example while it probes the other one) can never block the network loop."""
        while True:
            item = q.get()
            if item is None:
                break
            try:
                write(item)
                if on_ok:
                    on_ok()
            except (OSError, ValueError, AttributeError):
                break

    def _run_native(self):
        cam = self.cam
        c = stream_client(cam)
        self.client = c
        proc = None
        self.audio_sock = None
        want_audio = self.app.settings.get("audio", True)
        vq = queue.Queue(maxsize=900)
        aq = queue.Queue(maxsize=400)
        writers = []

        def put(q, item):
            try:
                q.put_nowait(item)
            except queue.Full:        # ffmpeg is not reading: drop instead of blocking
                pass

        def send_audio(data):
            sock = self.audio_sock
            if sock is not None:
                sock.sendall(data)

        def video_ok():
            self.last_write = time.time()

        try:
            c.connect()
            c.start_stream(int(cam.get("channel", 1)) - 1, "Main")
            codec = None
            pending = []          # video held back for ~1.5 s to find out whether there is audio
            audio_fmt = None
            hold_until = None
            for kind, key, fcodec, fps, data in c.frames():
                if not self.want:
                    break
                if kind == "audio":
                    if want_audio and audio_fmt is None and proc is None:
                        audio_fmt = dvrip_audio_format(fcodec, fps)
                    if proc is not None and audio_fmt and self.audio_sock is not None:
                        put(aq, data)
                    continue
                if kind != "video":
                    continue
                if proc is None:
                    if not pending:
                        if not key:
                            continue
                        codec = fcodec
                        hold_until = time.time() + 1.5
                    pending.append(data)
                    if time.time() < hold_until and len(pending) < 400:
                        continue
                    proc = self._start_native_ffmpeg(codec, audio_fmt)
                    self.proc = proc
                    writers = [threading.Thread(target=self._pump, args=(vq, proc.stdin.write, video_ok), daemon=True)]
                    if audio_fmt:
                        writers.append(threading.Thread(target=self._pump, args=(aq, send_audio), daemon=True))
                    for w in writers:
                        w.start()
                    for d in pending:
                        put(vq, d)
                    pending = []
                    continue
                if fcodec != codec or proc.poll() is not None:
                    break
                put(vq, data)
        except DvripAuthError as e:
            self.errors.append(str(e))
            self.retry_delay = 60
        except (DvripError, OSError, ConnectionError, ValueError) as e:
            self.errors.append(str(e))
            if cam.get("kind") == KIND_CLOUD:
                self.retry_delay = 15
        finally:
            c.close()
            self.client = None
            for q in (vq, aq):
                try:
                    q.put_nowait(None)
                except queue.Full:
                    pass
            for w in writers:
                w.join(3)
            sock, self.audio_sock = self.audio_sock, None
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            if proc:
                try:
                    proc.stdin.close()  # ffmpeg closes the file cleanly
                except Exception:
                    pass
                try:
                    proc.wait(6)
                except Exception:
                    proc.kill()

    def stop(self, wait=True):
        self.want = False
        c = self.client
        if c:
            c.close()
        p = self.proc
        if p and p.poll() is None and self.cam.get("kind") not in STREAM_KINDS:
            try:
                p.stdin.write(b"q")  # clean close of the file
                p.stdin.flush()
            except Exception:
                pass
        if wait and self.thread:
            self.thread.join(8)
            p = self.proc
            if p and p.poll() is None:
                p.kill()
