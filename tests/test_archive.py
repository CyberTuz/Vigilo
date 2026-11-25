"""Recordings on disk: segment listing, motion events, automatic overwrite."""
import os
import time
import datetime

from vigilo_app.archive import cleanup_recordings, list_segments, read_events

D = datetime.datetime


def make(folder, name, size, mtime):
    p = folder / name
    p.write_bytes(b"\0" * size)
    os.utime(p, (mtime, mtime))
    return p


def test_list_segments_order_and_end_times(tmp_path):
    t1, t2 = D(2026, 11, 20, 10, 0, 0), D(2026, 11, 20, 10, 10, 0)
    make(tmp_path, "Cam_2026-11-20_10-10-00.mkv", 5000, (t2 + datetime.timedelta(minutes=10)).timestamp())
    # closed late: its end must be clamped to the start of the next file
    make(tmp_path, "Cam_2026-11-20_10-00-00.mkv", 5000, (t2 + datetime.timedelta(seconds=30)).timestamp())
    make(tmp_path, "notes.txt", 10, t1.timestamp())
    segs = list_segments(str(tmp_path), segment_min=10)
    assert [s[0] for s in segs] == [t1, t2]
    assert segs[0][1] == t2
    assert segs[1][1] == t2 + datetime.timedelta(minutes=10)


def test_list_segments_drops_tiny_files_except_the_last(tmp_path):
    t = D(2026, 11, 20, 9, 0, 0)
    make(tmp_path, "Cam_2026-11-20_09-00-00.mkv", 100, (t + datetime.timedelta(minutes=5)).timestamp())
    make(tmp_path, "Cam_2026-11-20_09-10-00.mkv", 5000, (t + datetime.timedelta(minutes=20)).timestamp())
    make(tmp_path, "Cam_2026-11-20_09-20-00.mkv", 100, (t + datetime.timedelta(minutes=25)).timestamp())
    assert [s[0].minute for s in list_segments(str(tmp_path), 10)] == [10, 20]


def test_read_events_includes_events_crossing_midnight(tmp_path):
    ev = tmp_path / "events"
    ev.mkdir()
    a = D(2026, 11, 19, 23, 59, 50).timestamp()
    (ev / "2026-11-19.txt").write_text(f"{a:.1f} {a + 30:.1f}\n", encoding="utf-8")
    b = D(2026, 11, 20, 8, 0, 0).timestamp()
    (ev / "2026-11-20.txt").write_text(f"{b:.1f} {b + 5:.1f}\ngarbage line\n", encoding="utf-8")
    out = read_events(str(tmp_path), datetime.date(2026, 11, 20))
    assert [s for s, _ in out] == [D(2026, 11, 19, 23, 59, 50), D(2026, 11, 20, 8, 0, 0)]


def settings(root, **kw):
    s = {"rec_dir": str(root), "keep_days": 0, "max_rec_gb": 0, "min_free_gb": 0}
    s.update(kw)
    return s


def test_cleanup_keep_days(tmp_path):
    cam = tmp_path / "Cam"
    cam.mkdir()
    now = time.time()
    old = make(cam, "Cam_old.mkv", 1000, now - 3 * 86400)
    new = make(cam, "Cam_new.mkv", 1000, now - 3600)
    snaps = tmp_path / "Cam" / "Snapshots"
    snaps.mkdir()
    keep = make(snaps, "clip.mp4", 1000, now - 30 * 86400)        # skipped folder: never deleted
    logs = []
    total = cleanup_recordings(settings(tmp_path, keep_days=1), logs.append)
    assert not old.exists() and new.exists() and keep.exists()
    assert total == 1000 and len(logs) == 1


def test_cleanup_max_space_keeps_files_being_written(tmp_path):
    cam = tmp_path / "Cam"
    cam.mkdir()
    now = time.time()
    a = make(cam, "a.mkv", 1000, now - 7200)
    b = make(cam, "b.mkv", 1000, now - 3600)
    writing = make(cam, "c.mkv", 1000, now - 10)                 # modified seconds ago: being written
    # 3000 bytes in all (the file being written counts too), limit 2500: only the oldest goes
    total = cleanup_recordings(settings(tmp_path, max_rec_gb=2500 / 1024**3), lambda m: None)
    assert not a.exists() and b.exists() and writing.exists()
    assert total == 2000
