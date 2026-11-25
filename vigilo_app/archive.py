"""
Recordings on disk: listing, motion events, clip export and automatic overwrite.
"""

import os
import re
import time
import shutil
import tempfile
import subprocess
import datetime

from i18n import tr
from .common import EVENTS_DIR, FFMPEG, LEGACY_EVENTS_DIR, NOWIN, SKIP_DIRS


# ----------------------------------------------------------------------------- recordings archive

REC_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.(mkv|mp4)$", re.I)


def list_segments(folder, segment_min=10):
    """Recordings of one camera: sorted list of (start, end, path, size)."""
    files = []
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    for n in names:
        m = REC_RE.search(n)
        if not m:
            continue
        try:
            start = datetime.datetime.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H-%M-%S")
            p = os.path.join(folder, n)
            st = os.stat(p)
        except (ValueError, OSError):
            continue
        files.append([start, datetime.datetime.fromtimestamp(st.st_mtime), p, st.st_size])
    files.sort()
    now = datetime.datetime.now()
    for i, f in enumerate(files):
        nxt = files[i + 1][0] if i + 1 < len(files) else None
        if nxt is None and (now - f[0]).total_seconds() < segment_min * 60 + 120:
            f[1] = max(f[1], now)   # file being written (Windows updates the date only on close)
        if nxt is not None and f[1] > nxt:
            f[1] = nxt
        if f[1] <= f[0]:
            f[1] = min(f[0] + datetime.timedelta(seconds=segment_min * 60), nxt or now)
    return [tuple(f) for f in files if f[1] > f[0] and (f[3] > 2048 or f is files[-1])]


def read_events(folder, day):
    """Motion events of one day: list of (start, end) datetimes."""
    out = []
    for d in (day - datetime.timedelta(days=1), day):
        for sub in (EVENTS_DIR, LEGACY_EVENTS_DIR):
            p = os.path.join(folder, sub, d.strftime("%Y-%m-%d") + ".txt")
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            a, b = line.split()
                            s, e = datetime.datetime.fromtimestamp(float(a)), datetime.datetime.fromtimestamp(float(b))
                        except ValueError:
                            continue
                        if s.date() == day or e.date() == day:
                            out.append((s, e))
            except OSError:
                pass
    out.sort()
    return out


def estimate_rate(rec_dir, segment_min):
    """Average bytes per second per camera, measured on recordings already closed."""
    rates = []
    try:
        dirs = [os.path.join(rec_dir, d) for d in os.listdir(rec_dir)]
    except OSError:
        return None
    for d in dirs:
        if not os.path.isdir(d):
            continue
        segs = list_segments(d, segment_min)[:-1][-6:]
        tot_b = sum(s[3] for s in segs)
        tot_t = sum((s[1] - s[0]).total_seconds() for s in segs)
        if tot_t > 60 and tot_b > 0:
            rates.append(tot_b / tot_t)
    return sum(rates) / len(rates) if rates else None


def video_codec(path):
    try:
        r = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, timeout=15,
                           creationflags=NOWIN)
        txt = r.stderr.decode("utf-8", "ignore")
        return "hevc" if "Video: hevc" in txt else "h264" if "Video: h264" in txt else None
    except Exception:
        return None


def export_clip(segments, t, dur, out_path):
    segs = [s for s in segments if s[1] > t and s[0] < t + datetime.timedelta(seconds=dur)]
    if not segs:
        return False, tr("There are no recordings at that time.")
    off = max(0.0, (t - segs[0][0]).total_seconds())
    lst = os.path.join(tempfile.gettempdir(), f"tc_concat_{os.getpid()}.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for s in segs:
            f.write("file '" + s[2].replace("\\", "/").replace("'", "'\\''") + "'\n")
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
           "-ss", f"{off:.2f}", "-i", lst, "-t", str(dur), "-map", "0:v:0", "-map", "0:a:0?",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart"]
    if video_codec(segs[0][2]) == "hevc":
        cmd += ["-tag:v", "hvc1"]
    cmd.append(out_path)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=600, creationflags=NOWIN)
    finally:
        try:
            os.remove(lst)
        except OSError:
            pass
    if r.returncode != 0 or not os.path.exists(out_path):
        return False, r.stderr.decode("utf-8", "ignore").strip()[-300:] or tr("Export error")
    return True, out_path


# ----------------------------------------------------------------------------- disk cleanup / overwrite

def cleanup_recordings(settings, log):
    """Automatic overwrite. Returns the space used by the recordings."""
    root = settings["rec_dir"]
    if not os.path.isdir(root):
        return 0
    now = time.time()
    files = []
    total = 0
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for n in names:
            if n.lower().endswith((".mkv", ".mp4")):
                p = os.path.join(dirpath, n)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                total += st.st_size
                if now - st.st_mtime < 180 or st.st_size == 0:  # file being written
                    continue
                files.append((st.st_mtime, p, st.st_size))
    files.sort()
    removed = 0

    def drop(f):
        nonlocal removed, total
        try:
            os.remove(f[1])
            removed += 1
            total -= f[2]
            return True
        except OSError:
            return False

    keep_days = float(settings.get("keep_days", 0) or 0)
    if keep_days > 0:
        limit = now - keep_days * 86400
        while files and files[0][0] < limit:
            drop(files.pop(0))
    max_rec = float(settings.get("max_rec_gb", 0) or 0) * 1024**3
    if max_rec > 0:
        while files and total > max_rec:
            drop(files.pop(0))
    min_free = float(settings.get("min_free_gb", 0) or 0) * 1024**3
    if min_free > 0:
        while files and shutil.disk_usage(root).free < min_free:
            drop(files.pop(0))
    if removed:
        log(tr("Overwrite: deleted {n} old recordings").format(n=removed))
    return total
