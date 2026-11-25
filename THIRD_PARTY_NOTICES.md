# Third-party software

Vigilo's own code is released under the [MIT License](LICENSE). The ready-made Windows build
(`Vigilo-<version>-win64.zip`) also contains the following third-party software, each under its own
license.

| Component | License | Source |
|---|---|---|
| [FFmpeg](https://ffmpeg.org) 9.0.2, "essentials" build by gyan.dev, shipped by imageio-ffmpeg | **GPL v3** (built with `--enable-gpl --enable-version3`) | [ffmpeg.org/download](https://ffmpeg.org/download.html) · [gyan.dev builds](https://www.gyan.dev/ffmpeg/builds/) |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | BSD-2-Clause | GitHub |
| [Python](https://www.python.org) 3.11 | PSF License | python.org |
| Tcl/Tk (tkinter) | Tcl/Tk License (BSD-style) | [tcl.tk](https://www.tcl.tk) |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | MIT | GitHub |
| [OpenCV](https://github.com/opencv/opencv-python) (opencv-python) | Apache 2.0; its bundled FFmpeg backend is LGPL 2.1 | GitHub |
| [NumPy](https://numpy.org) | BSD-3-Clause | numpy.org |
| [Pillow](https://python-pillow.org) | MIT-CMU (HPND) | GitHub |
| [psutil](https://github.com/giampaolo/psutil) | BSD-3-Clause | GitHub |
| [python-sounddevice](https://github.com/spatialaudio/python-sounddevice) and PortAudio | MIT / MIT-style | GitHub |
| [pystray](https://github.com/moses-palmer/pystray) | LGPL v3 | GitHub |
| [PyInstaller](https://pyinstaller.org) bootloader | GPL v2 with an exception that allows distributing applications built with it | pyinstaller.org |

FFmpeg is a separate program (`ffmpeg-win-x86_64-*.exe` inside the `_internal` folder) that Vigilo
starts as a child process; it is not linked into Vigilo. Its complete source code is available from
the links above.

Not included: the ICSee / XMeye cloud SDK (`NetSdk.dll`) is proprietary and is never distributed with
Vigilo (see [sdk/README.md](sdk/README.md)).

ICSee, XMeye, VMS, Xiongmai and Jftech are names of their respective owners and are used only to
describe compatibility.
