"""
Vigilo - a simple viewer and recorder for IP cameras
(ICSee / XMeye / Xiongmai and any RTSP camera). Windows, Python 3.11.

- Live view: automatic grid or "focus" layout, video-only full screen
- RTSP (port 554) or the native ICSee/XMeye protocol (DVRIP/Sofia, port 34567)
  for cameras without RTSP; experimental cloud connection via NetSdk.dll
- Live audio and audio recording
- PTZ control and saved positions for motorized cameras
- Continuous or motion-only recording without re-encoding, N-minute files
- Automatic overwrite (maximum space, days to keep, minimum free space)
- Motion detection with events on the timeline
- Playback by day and time, snapshots and clip export
- LAN camera discovery, CPU / RAM / disk usage
- Runs in the notification area, keeps the PC awake while recording, restarts itself after a crash
- English and Italian user interface

This file is only the entry point: the program lives in the vigilo_app package.

    vigilo.py                  watchdog (supervisor) that runs and restarts the program
    vigilo.py --child          the program itself (started by the watchdog)
    vigilo.py --no-supervisor  the program without the watchdog (debugging)
    vigilo.py --cloud-bridge   helper process for the cloud connection (xmcloud_bridge.py)
    vigilo.py --make-icon F    write the program icon to F (build)
"""

import os
import sys

# Cloud bridge process: dispatched before any other import (faster start, less RAM)
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--cloud-bridge":
    import xmcloud_bridge
    xmcloud_bridge.main()


def main():
    argv = sys.argv[1:]
    if len(argv) >= 2 and argv[0] == "--make-icon":
        from vigilo_app.ui.theme import ensure_app_icon
        ensure_app_icon(argv[1])
        return 0
    from vigilo_app import supervisor          # standard library only: the watchdog stays light
    if supervisor.wanted(argv):
        return supervisor.supervise(supervisor.child_command(argv, os.path.abspath(__file__)))
    from vigilo_app.ui.main_window import run_app
    return run_app(argv)


if __name__ == "__main__":
    sys.exit(main())
