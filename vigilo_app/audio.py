"""
G.711 decoding, live audio output and the audio-only RTSP tap.
"""

import time
import queue
import threading
import subprocess

import numpy as np

from .common import cam_url, FFMPEG, kill_with_app, NOWIN


# ----------------------------------------------------------------------------- audio

try:
    import sounddevice as sd
except Exception:          # PortAudio missing: the program still works, without live audio
    sd = None


def _g711_tables():
    """Lookup tables G.711 A-law / u-law -> 16-bit PCM."""
    alaw = np.zeros(256, np.int16)
    ulaw = np.zeros(256, np.int16)
    for i in range(256):
        a = i ^ 0x55
        seg = (a & 0x70) >> 4
        t = (a & 0x0F) << 4
        t = t + 8 if seg == 0 else (t + 0x108) << (seg - 1)
        alaw[i] = t if a & 0x80 else -t
        u = ~i & 0xFF
        t = ((u & 0x0F) << 3) + 0x84
        t <<= (u & 0x70) >> 4
        ulaw[i] = (0x84 - t) if u & 0x80 else (t - 0x84)
    return alaw, ulaw


ALAW_TABLE, ULAW_TABLE = _g711_tables()
DVRIP_ULAW_MEDIA = {0x0A}           # media byte of u-law audio frames (A-law otherwise)
DVRIP_AUDIO_RATES = {1: 4000, 2: 8000, 3: 11025, 4: 16000, 5: 22050, 6: 32000, 7: 44100, 8: 48000}


def dvrip_audio_format(media, rate_code):
    """(ffmpeg format, sample rate) of a DVRIP audio frame."""
    return ("mulaw" if media in DVRIP_ULAW_MEDIA else "alaw"), DVRIP_AUDIO_RATES.get(rate_code, 8000)


def decode_g711(data, media):
    table = ULAW_TABLE if media in DVRIP_ULAW_MEDIA else ALAW_TABLE
    return table[np.frombuffer(data, np.uint8)].tobytes()


class AudioOut:
    """Live audio output: one camera at a time (like an NVR). Fed by the viewers."""

    def __init__(self):
        self.q = queue.Queue(maxsize=40)
        self.owner = None
        self.rate = None
        self.stream = None
        self.error = ""
        if sd is not None:
            threading.Thread(target=self._run, daemon=True).start()

    @property
    def available(self):
        return sd is not None

    def set_owner(self, cid):
        self.owner = cid
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass

    def push(self, owner, pcm, rate):
        if owner != self.owner or sd is None:
            return
        try:
            self.q.put_nowait((pcm, rate))
        except queue.Full:          # we are behind: drop old audio to keep the delay low
            try:
                self.q.get_nowait()
            except queue.Empty:
                pass

    def _run(self):
        while True:
            pcm, rate = self.q.get()
            try:
                if rate != self.rate or self.stream is None:
                    if self.stream is not None:
                        self.stream.close()
                    self.stream = sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16",
                                                     latency="low")
                    self.stream.start()
                    self.rate = rate
                self.stream.write(pcm)
                self.error = ""
            except Exception as e:      # no output device, device unplugged...
                self.error = str(e)
                self.stream = None
                time.sleep(1)


class RtspAudioTap(threading.Thread):
    """Live audio for RTSP cameras: an audio-only ffmpeg that outputs 16 kHz PCM."""
    RATE = 16000

    def __init__(self, cam, audio_out):
        super().__init__(daemon=True)
        self.cam, self.out = cam, audio_out
        self.running = True
        self.proc = None

    def run(self):
        url = cam_url(self.cam, True)
        while self.running:
            cmd = [FFMPEG, "-hide_banner", "-loglevel", "quiet", "-fflags", "nobuffer"]
            if url.lower().startswith("rtsp"):
                cmd += ["-rtsp_transport", "tcp"]
            cmd += ["-i", url, "-vn", "-ac", "1", "-ar", str(self.RATE), "-f", "s16le", "pipe:1"]
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         stdin=subprocess.DEVNULL, creationflags=NOWIN)
            kill_with_app(self.proc)
            while self.running:
                b = self.proc.stdout.read(self.RATE // 10 * 2)   # 100 ms
                if not b:
                    break
                self.out.push(self.cam["id"], b, self.RATE)
            self._kill()
            for _ in range(30):
                if not self.running:
                    break
                time.sleep(0.1)

    def _kill(self):
        p = self.proc
        if p:
            try:
                p.kill()
            except Exception:
                pass

    def stop(self):
        self.running = False
        self._kill()
