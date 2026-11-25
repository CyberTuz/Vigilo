# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build file for Vigilo.  Build with:  pyinstaller --noconfirm vigilo.spec
# (or run build.ps1, which also creates the icon and the zip)
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

datas = collect_data_files("imageio_ffmpeg") + collect_data_files("customtkinter")
datas += [("LICENSE", "."), ("README.md", "."), ("THIRD_PARTY_NOTICES.md", "."), ("CHANGELOG.md", "."),
          ("docs/USER_GUIDE.md", "docs"), ("docs/GUIDA_UTENTE.md", "docs")]
binaries = collect_dynamic_libs("imageio_ffmpeg") + collect_dynamic_libs("sounddevice")
try:
    datas += collect_data_files("_sounddevice_data")        # PortAudio DLL shipped with sounddevice
except Exception:
    pass

a = Analysis(
    ["vigilo.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    # the vigilo_app modules are imported lazily by vigilo.py (watchdog first), pystray picks its
    # backend at run time: list them explicitly
    hiddenimports=["xmcloud_bridge", "i18n", "sounddevice", "_sounddevice_data", "pystray._win32"]
                  + collect_submodules("vigilo_app"),
    excludes=["matplotlib", "scipy", "pandas", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Vigilo",
    console=False,
    icon="build/vigilo.ico",
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Vigilo")
