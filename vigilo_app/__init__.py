"""
Vigilo - a simple viewer and recorder for IP cameras (ICSee / XMeye / Xiongmai and any RTSP camera).

Modules (lower layers never import higher ones):
  common       constants, configuration, paths, small helpers
  dvrip        native ICSee/XMeye protocol (DVRIP, TCP 34567)
  cloud        cloud connection through NetSdk.dll (separate process: xmcloud_bridge.py)
  devices      client by connection type, PTZ controller, connection test
  motion       motion detection
  audio        G.711, live audio output, RTSP audio tap
  viewers      live view threads
  recorder     recording to disk with ffmpeg
  archive      recordings on disk: listing, events, export, automatic overwrite
  player       playback engine
  system       Windows integration: startup, single instance, keep awake, tray, crash log
  supervisor   watchdog process that restarts Vigilo after a crash (standard library only)
  ui/          CustomTkinter user interface
"""

import os

# Must be set before OpenCV is imported anywhere: cheap cameras work much better with RTSP over TCP
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|timeout;8000000")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
