"""
Video decoding on the graphics card (GPU) with ffmpeg's D3D11VA: works with AMD, NVIDIA and Intel
GPUs on Windows 10/11.

probe() checks once, in about 0.2 s, whether the GPU really decodes H.264 and H.265: it decodes a
tiny clip made on the spot and downloads the frames from the GPU, which fails when ffmpeg fell back
to software decoding. ffmpeg also falls back to software by itself when a stream cannot be decoded
on the GPU, and the viewers switch a camera to software if its GPU decoder gives no picture.
"""

import threading
import subprocess

from .common import applog, FFMPEG, NOWIN

HWACCEL = "d3d11va"
GPU_GRACE = 6.0          # seconds a GPU decoder may take to give its first picture
_lock = threading.Lock()
_result = None


def _make_clip(fmt, encoder):
    extra = ["-x265-params", "log-level=error"] if encoder == "libx265" else []
    r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "testsrc2=size=256x144:rate=10", "-frames:v", "3", "-c:v", encoder] + extra
                       + ["-f", fmt, "-"], capture_output=True, timeout=30, creationflags=NOWIN)
    return r.stdout if r.returncode == 0 else b""


def _gpu_decodes(fmt, encoder):
    try:
        clip = _make_clip(fmt, encoder)
        if not clip:
            return False
        r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-hwaccel", HWACCEL,
                            "-hwaccel_output_format", "d3d11", "-f", fmt, "-i", "-",
                            "-vf", "hwdownload,format=nv12", "-f", "null", "-"],
                           input=clip, capture_output=True, timeout=30, creationflags=NOWIN)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def probe(refresh=False):
    """{"h264": bool, "hevc": bool}: codecs the GPU decodes. Checked once, then cached."""
    global _result
    with _lock:
        if _result is None or refresh:
            _result = {"h264": _gpu_decodes("h264", "libx264"), "hevc": _gpu_decodes("hevc", "libx265")}
            applog(f"GPU video decoding ({HWACCEL}): {gpu_name() or 'unknown graphics card'} · "
                   f"H.264 {'yes' if _result['h264'] else 'no'} · H.265 {'yes' if _result['hevc'] else 'no'}")
        return dict(_result)


def available():
    return any(probe().values())


def decode_args(settings, codec=None):
    """ffmpeg input options for GPU decoding, or [] for software. codec: "h264" / "hevc" / None (unknown
    yet: GPU if it decodes anything, ffmpeg falls back to software for a codec it cannot do)."""
    if (settings or {}).get("hw_decode", "auto") == "off":
        return []
    p = probe()
    ok = p.get(codec, False) if codec in p else any(p.values())
    return ["-hwaccel", HWACCEL] if ok else []


def gpu_name():
    """Name of the graphics card that drives the main screen ("" if unknown)."""
    try:
        import ctypes
        from ctypes import wintypes

        class DISPLAY_DEVICEW(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                        ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                        ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]

        names = []
        for i in range(16):
            d = DISPLAY_DEVICEW()
            d.cb = ctypes.sizeof(d)
            if not ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(d), 0):
                break
            if d.StateFlags & 0x4:          # DISPLAY_DEVICE_PRIMARY_DEVICE
                return d.DeviceString
            if d.DeviceString and d.DeviceString not in names:
                names.append(d.DeviceString)
        return names[0] if names else ""
    except Exception:
        return ""
