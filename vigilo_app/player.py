"""
Playback engine: plays recorded files from an exact moment, with audio at 1x.
"""

import time
import threading
import subprocess
import datetime

import numpy as np

from .common import FFMPEG, kill_with_app, NOWIN


# ----------------------------------------------------------------------------- playback

class Player:
    """Plays a sequence of recorded files starting from an exact moment.
    At 1x speed it can also play the audio track through AudioOut."""
    FPS = 12

    def __init__(self, w=1280, h=720):
        self.w, self.h = w, h
        self.segments = []
        self.lock = threading.Lock()
        self.gen = 0
        self.target = None
        self.speed = 1
        self.playing = False
        self.cur_t = None
        self.frame = None
        self.frame_id = 0
        self.state = ""
        self.proc = None
        self.alive = True
        self.audio_out = None       # AudioOut, set by the playback window
        self.audio_on = False
        self.aproc = None
        self.hw_args = lambda: []   # ffmpeg GPU decoding options, set by the playback window
        self.decoder = ""           # "gpu" / "cpu": decoder of the file being played
        threading.Thread(target=self._run, daemon=True).start()

    def _kill_audio(self):
        p, self.aproc = self.aproc, None
        if p:
            try:
                p.kill()
            except Exception:
                pass

    def _spawn_audio(self, path, off, gen):
        self._kill_audio()
        out = self.audio_out
        if not (self.audio_on and out and out.available and self.speed == 1 and self.playing):
            return
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "quiet"]
        if off > 0.05:
            cmd += ["-ss", f"{off:.3f}"]
        cmd += ["-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, creationflags=NOWIN)
        kill_with_app(p)
        self.aproc = p

        def pump():
            while self.alive and self.gen == gen and self.playing and self.aproc is p:
                b = p.stdout.read(3200)
                if not b:
                    break
                out.push("playback", b, 16000)
                time.sleep(0.09)        # pace roughly in real time (AudioOut keeps the delay low)
            if self.aproc is p:
                self._kill_audio()
        threading.Thread(target=pump, daemon=True).start()

    def set_segments(self, segs):
        with self.lock:
            self.segments = list(segs)

    def seek(self, t):
        with self.lock:
            self.target = t
            self.gen += 1
        self._kill()

    def set_speed(self, s):
        self.speed = s
        if self.cur_t is not None:
            self.seek(self.cur_t)

    def _kill(self):
        p = self.proc
        if p:
            try:
                p.kill()
            except Exception:
                pass

    def close(self):
        self.alive = False
        self._kill()
        self._kill_audio()

    def _find(self, t):
        with self.lock:
            for seg in self.segments:
                if seg[1] > t:
                    return seg
        return None

    def _spawn(self, path, off, speed):
        w, h = self.w, self.h
        vf = (f"setpts=PTS/{speed},scale={w}:{h}:force_original_aspect_ratio=decrease,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "quiet"]
        if speed >= 8:
            cmd += ["-skip_frame", "nokey"]   # at high speed decode key frames only
        if off > 0.05:
            cmd += ["-ss", f"{off:.3f}"]
        try:
            hw = list(self.hw_args())
        except Exception:
            hw = []
        self.decoder = "gpu" if hw else "cpu"
        cmd += hw + ["-i", path, "-an", "-sn", "-vf", vf, "-r", str(self.FPS),
                "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, creationflags=NOWIN)
        kill_with_app(p)
        return p

    def _run(self):
        my_gen = -1
        proc = None
        seg = None
        base_t = None
        k = 0
        first = False
        due = None
        n = self.w * self.h * 3
        while self.alive:
            if self.gen != my_gen:
                with self.lock:
                    my_gen = self.gen
                    t = self.target
                speed = self.speed
                if proc:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                proc = None
                if t is None:
                    time.sleep(0.05)
                    continue
                seg = self._find(t)
                if seg is None:
                    self.state = "end"
                    self.playing = False
                    self.cur_t = t
                    while self.alive and self.gen == my_gen:
                        time.sleep(0.05)
                    continue
                if t < seg[0]:
                    t = seg[0]
                self.state = "loading"
                proc = self._spawn(seg[2], (t - seg[0]).total_seconds(), speed)
                self.proc = proc
                self._spawn_audio(seg[2], (t - seg[0]).total_seconds(), my_gen)
                base_t, k, first, due = t, 0, True, None
            if proc is None:
                time.sleep(0.05)
                continue
            if not first and not self.playing:
                due = None
                time.sleep(0.03)
                continue
            try:
                b = proc.stdout.read(n)
            except Exception:
                b = b""
            if len(b) < n:
                if self.gen != my_gen:
                    continue
                # end of file: go to the next one
                nxt = None
                with self.lock:
                    for s in self.segments:
                        if s[0] >= seg[1] - datetime.timedelta(seconds=1) and s[2] != seg[2]:
                            nxt = s
                            break
                if nxt:
                    with self.lock:
                        self.target = nxt[0]
                        self.gen += 1
                else:
                    self.state = "end"
                    self.playing = False
                    proc = None
                continue
            ft = base_t + datetime.timedelta(seconds=k * speed / self.FPS)
            k += 1
            if not first:
                now = time.time()
                if due is None:
                    due = now
                if due > now:
                    time.sleep(due - now)
                due += 1.0 / self.FPS
                if time.time() - due > 0.5:
                    due = time.time()
            first = False
            self.state = "play" if self.playing else "pause"
            with self.lock:
                self.frame = np.frombuffer(b, np.uint8).reshape(self.h, self.w, 3)
                self.frame_id += 1
                self.cur_t = ft
