# Vigilo roadmap

Status: **Done** · **In progress** · **Planned**. Priority: P1 (next) · P2 · P3 (later).

## 1. Notifications and alerts — P1 · Planned

- Motion alert with a snapshot: Windows notification, Telegram bot, e-mail (SMTP). Per camera, with a
  quiet period so a windy afternoon does not send 200 messages.
- Camera offline / back online alert (after N minutes without video).
- Alert when a recording stops unexpectedly or the disk is almost full.
- The base is already there: every motion event goes through `App.motion_event()` and is stored in
  `<camera>/events/`.

## 2. Reliability as an always-on recorder — Done (1.1.0)

- Notification-area (tray) icon: closing the window keeps Vigilo running and recording.
- Keep the PC awake while recording (`SetThreadExecutionState`; the screen can still turn off).
- Watchdog: a small supervisor process restarts Vigilo if it crashes, and gives up after repeated
  crashes instead of looping forever.
- Starting Vigilo a second time brings the running window to the front.
- Unhandled errors (threads, Tk callbacks) are written to `vigilo.log`.
- Later: detect a frozen UI (heartbeat to the watchdog), optional Windows service mode.

## 3. Better motion detection — P1 · Planned

- Motion zones / masks per camera (ignore the road, trees, the timestamp overlay).
- Sensitivity per camera, minimum object size.
- Optional person / vehicle detection with a small ONNX model to cut false alarms. ONNX Runtime with
  DirectML runs on any DirectX 12 GPU (AMD, NVIDIA, Intel), see point 8.

## 4. Per-camera settings — P2 · Planned

- File length, days to keep, recording mode and disk quota per camera, falling back to the global
  values.
- Recording schedule (hours / days of the week).

## 5. Security — P2 · Planned

- Encrypt the camera passwords in `config.json` with Windows DPAPI (`CryptProtectData`, tied to the
  Windows user) instead of plain text, with a transparent migration of existing configurations.
- Export / import of the configuration (backup), with the passwords left out or encrypted.

## 6. Playback and UX — P3 · Planned

- Export a range selected on the timeline (start / end), not only fixed lengths.
- Digital zoom on live view and playback; thumbnail preview while hovering the timeline.
- Synchronized playback of several cameras.

## 7. Code health — Done (1.1.0)

- `vigilo.py` (4,200 lines) split into the `vigilo_app` package (16 modules, no import cycles):
  protocol, cloud, recorder, player, system, UI.
- 42 automated tests with `pytest` (about 10 s), including end-to-end tests against the fake camera
  (`tools/fake_dvrip.py`): login, video, audio, connection test and a real recording with audio.
- Later: CI (GitHub Actions), type hints on the protocol code, tests for the playback engine.

## 8. Performance and GPU — GPU decoding done (1.1.0) · more Planned

Where the CPU goes today:

| Work | Cost | GPU can help? |
|---|---|---|
| Recording | almost none: the video is copied, not re-encoded | no need |
| Live view decoding (one ffmpeg / OpenCV decoder per camera) | **the main cost**, grows with every camera, H.265 is heavier | **yes: hardware decoding** |
| Playback decoding | one decoder at a time | yes: hardware decoding |
| Drawing the tiles (resize + Tk image, ~15 fps per tile) | noticeable with many cameras, runs on the UI thread | indirectly: decode straight to tile size |
| Motion detection (160×90, 2.5 times a second) | negligible | not needed (yes for AI detection, point 3) |

Measured on a Ryzen 9 5900X + Radeon RX 5700 XT (2026-11-25) with the **exact live-view decoder
command** of Vigilo, fed in real time (15 fps); share of **one** CPU core per camera, median of 3 runs:

| Stream | Software | GPU (D3D11VA) | Saving |
|---|---|---|---|
| 640×360 H.264 (secondary stream, used by the grid) | 3.9 % | 3.9 % | none |
| 1080p H.264 | 11.3 % | 3.5 % | 69 % |
| 1080p H.265 | 14.9 % | 6.1 % | 59 % |
| 5 MP H.265 (2592×1944) | 44.4 % | 10.5 % | 76 % |

Four decoders at once, stream written to them through a pipe as the app does (1080p H.264):
41 % in software, 21–28 % on the GPU (about −40 %). A first benchmark without the app's `low_delay`
flag (multi-threaded decoding) showed 26 % vs 8 % per camera: that overstated the software cost.
Timings on a PC in use vary by several points between runs; the medians above are the reliable part.

Where it matters: the grid uses the cameras' light secondary streams, where the GPU changes nothing.
The wins are the enlarged / focus view and playback (full-resolution main stream), cameras without a
secondary stream, 5 MP+ and H.265 cameras, and small always-on PCs (mini PC, laptop).

Done in 1.1.0 (`vigilo_app/hwaccel.py`):

- Live view and playback decode on the GPU with ffmpeg's `-hwaccel d3d11va` (AMD, NVIDIA, Intel).
  At start Vigilo checks in about 0.5 s whether the GPU really decodes H.264 / H.265.
- RTSP cameras: OpenCV's own GPU option was measured and rejected (it used *more* CPU: 20–27 % against
  18 %), so with the GPU on they use an ffmpeg decoder; with the GPU off they keep using OpenCV.
- Three levels of fallback: ffmpeg falls back to software by itself; a camera whose GPU decoder gives
  no picture switches to software (logged); *Settings → Performance → Off* turns it off, live.
- The camera card shows "· GPU" and the Settings panel how many cameras decode on the GPU.

Drawing the live tiles — done in 1.1.0. Profiled on the UI thread, 4 cameras, 529×334 tiles:

| | Before | After |
|---|---|---|
| Drawing one tile (`_draw`) | 3.4 ms | 1.5 ms |
| Resize (`cv2.resize`) | 1.3 ms | 0.2 ms |
| UI thread | 21.7 % of a core | 12.9 % (−41 %), with 11 % more frames drawn |

- Linear resize down to half size (INTER_AREA, 7 times slower, only for stronger reductions).
- Dark band, name and REC / MOTION pills drawn into a cached RGBA overlay, rebuilt only when they
  change, and laid over each frame with one masked paste (same look: darkening by *g* = black with
  alpha 1 − *g*).
- Each tile reuses its Tk image (`PhotoImage.paste`) instead of creating a new one per frame.

Next:

- Secondary streams are decoded into a 960×540 box although they are usually 640×360: a smaller box
  would halve the data copied through the pipes and the resize work. Needs care for cameras with
  bigger secondary streams shown in big tiles.
- The rest of the UI thread is Tk itself (copying the image into the canvas): draw small tiles less
  often, or skip frames that would not change the picture.
- Scale on the GPU before downloading the frames: ffmpeg 9's `scale_d3d11` does not accept the
  decoder's surfaces yet ("Failed to configure output pad") and crashed in some tests: retry with a
  later ffmpeg.
