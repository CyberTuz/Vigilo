# Changelog

## 1.1.0 — 2026-11-25

- Closing the window keeps Vigilo running in the notification area (tray icon with *Show* / *Quit*);
  recording continues. Option in *Settings → Startup and background*.
- The PC is kept awake while recording (the screen can still turn off). Option in Settings.
- Watchdog: Vigilo is started again automatically after a crash, with a message; after repeated
  crashes it stops trying and says so.
- GPU video decoding (D3D11VA: AMD, NVIDIA, Intel) for live view and playback: 60–75 % less decoding
  CPU on full-resolution streams (1080p / 5 MP, H.264 / H.265), no change on the small secondary
  streams of the grid. Checked at start, falls back to the CPU by itself, *Settings → Performance*.
  With the GPU on, RTSP cameras are decoded by ffmpeg instead of OpenCV.
- Live tiles are drawn more than twice as fast (UI thread −41 % with 4 cameras): faster resize, the
  name / REC / MOTION overlay is cached, Tk images are reused. Same look.
- Starting Vigilo a second time brings the running window to the front instead of an error message.
- Unhandled errors (also in background threads and in the user interface) are written to `vigilo.log`.
- Code split from one 4,200-line file into the `vigilo_app` package; automated tests (`pytest`),
  including end-to-end tests against the fake camera.
- Fake camera: fixed its G.711 A-law encoder (the test tone was one segment too loud).
- New dependency: `pystray`.
- Third-party licenses listed in `THIRD_PARTY_NOTICES.md`, also included in the zip.

## 1.0.0 — 2026-11-08

First public version (renamed from the private "Telecamere Casa").

- English and Italian user interface, language chosen at first start and in Settings.
- Live audio (native protocol and RTSP) and audio recording, including the native protocol.
- Audio in playback at 1x speed.
- Motion-only recording mode with pre-recording and configurable minutes after the motion.
- "Armed" state for motion mode on tiles and in the sidebar.
- Recordings default to `Videos\Vigilo`; configuration in `%APPDATA%\Vigilo` with automatic import of
  the old configuration.
- Experimental cloud bridge: error codes translated, developer-account (InitAppInfo) support.
- Fake ICSee camera with audio for testing (`tools/fake_dvrip.py`).
