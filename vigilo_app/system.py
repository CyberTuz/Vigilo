"""
Windows integration: start with Windows, single instance, keep awake, tray icon, crash log.
"""

import os
import sys
import json
import time
import hashlib
import threading
import traceback

from i18n import tr
from i18n import set_language
from .common import APP_NAME, applog, CONFIG_DIR, CONFIG_FILE, ENTRY_SCRIPT, LEGACY_STARTUP_BAT, STARTUP_BAT


def set_startup(enabled):
    try:
        if enabled:
            if getattr(sys, "frozen", False):
                cmd = f'start "" "{sys.executable}"'
            else:
                pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                if not os.path.exists(pyw):
                    pyw = sys.executable
                cmd = f'start "" "{pyw}" "{ENTRY_SCRIPT}"'
            with open(STARTUP_BAT, "w", encoding="utf-8") as f:
                f.write("@echo off\r\ntimeout /t 20 /nobreak >nul\r\n" + cmd + "\r\n")
        elif os.path.exists(STARTUP_BAT):
            os.remove(STARTUP_BAT)
        if os.path.exists(LEGACY_STARTUP_BAT):      # do not start the old version as well
            os.remove(LEGACY_STARTUP_BAT)
    except Exception as e:
        from tkinter import messagebox
        messagebox.showwarning(APP_NAME, tr("Cannot set up automatic start:\n{err}").format(err=e))


# ----------------------------------------------------------------------------- single instance

def _instance_id():
    return hashlib.md5(CONFIG_DIR.lower().encode()).hexdigest()[:10]


def show_event_name():
    # mutexes and events share one namespace: the name must differ from the mutex name
    return "Vigilo_show_" + _instance_id()


def single_instance():
    """Prevent opening the program twice (it would record everything twice). If Vigilo is already
    running, its window is brought to the front instead (also from the notification area)."""
    try:
        import ctypes
        name = "Vigilo_" + _instance_id()
        for _attempt in range(20):        # after a restart the old instance may still be closing
            handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
            if ctypes.windll.kernel32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
                return handle
            ctypes.windll.kernel32.CloseHandle(handle)
            if "--restarted" not in sys.argv:
                break
            time.sleep(0.5)
        if signal_running_instance():
            return None
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                set_language(json.load(f).get("settings", {}).get("lang", "en"))
        except Exception:
            pass
        ctypes.windll.user32.MessageBoxW(None, tr("Vigilo is already open."), APP_NAME, 0x40)
        return None
    except Exception:
        return True


def release_instance(lock):
    if isinstance(lock, int) and lock:
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(lock)
        except Exception:
            pass


def _kernel32():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)    # own instance: argtypes stay local
    k.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    k.CreateEventW.restype = wintypes.HANDLE
    k.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    k.OpenEventW.restype = wintypes.HANDLE
    k.SetEvent.argtypes = [wintypes.HANDLE]
    k.SetEvent.restype = wintypes.BOOL
    k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k.WaitForSingleObject.restype = wintypes.DWORD
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.CloseHandle.restype = wintypes.BOOL
    return k


class ShowSignal:
    """Named Windows event: a second start of Vigilo sets it, the running instance polls it and
    shows its window."""

    def __init__(self, name=None):
        self._k = _kernel32()
        self.handle = self._k.CreateEventW(None, False, False, name or show_event_name())   # auto-reset

    def poll(self):
        return bool(self.handle) and self._k.WaitForSingleObject(self.handle, 0) == 0   # WAIT_OBJECT_0

    def close(self):
        h, self.handle = self.handle, None
        if h:
            self._k.CloseHandle(h)


def signal_running_instance(name=None):
    """Ask the running Vigilo to show its window. False if no instance is listening."""
    try:
        k = _kernel32()
        h = k.OpenEventW(0x0002, False, name or show_event_name())    # EVENT_MODIFY_STATE
        if not h:
            return False
        try:
            return bool(k.SetEvent(h))
        finally:
            k.CloseHandle(h)
    except Exception:
        return False


def restart_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--restarted"]
    return [sys.executable, ENTRY_SCRIPT, "--restarted"]


# ----------------------------------------------------------------------------- keep the PC awake

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


class KeepAwake:
    """Stops Windows from going to sleep by itself while Vigilo records. The screen can still turn
    off, and a sleep chosen by the user (menu, power button, lid) still happens.
    The request belongs to the calling thread: always call set() from the same thread (the UI one)."""

    def __init__(self, api=None):
        self._api = api
        self.active = False

    def _call(self, flags):
        if self._api is None:
            if os.name != "nt":
                return False
            import ctypes
            f = ctypes.windll.kernel32.SetThreadExecutionState
            f.argtypes = [ctypes.c_uint]
            f.restype = ctypes.c_uint
            self._api = f
        try:
            return bool(self._api(flags))
        except Exception:
            return False

    def set(self, on):
        on = bool(on)
        if on != self.active and self._call(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)):
            self.active = on
            applog("keep awake: " + ("on (recording)" if on else "off"))


# ----------------------------------------------------------------------------- tray icon

class TrayIcon:
    """Icon in the Windows notification area (pystray, on its own daemon thread).
    on_show and on_quit are called on the tray thread: they must hand the work to the UI thread."""

    def __init__(self, image, title, on_show, on_quit):
        self.icon = None
        self.error = ""
        self.running = False
        try:
            import pystray
            menu = pystray.Menu(
                pystray.MenuItem(tr("Show Vigilo"), lambda: on_show(), default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(tr("Quit Vigilo"), lambda: on_quit()))
            self.icon = pystray.Icon(APP_NAME, image, title, menu)
        except Exception as e:      # pystray missing, or no notification area
            self.error = str(e)
            applog(f"tray icon not available: {e}")

    @property
    def available(self):
        return self.icon is not None and self.running and not self.error

    def start(self):
        # not icon.run_detached(): on Windows it starts a non-daemon thread that keeps the process alive
        if self.icon is not None:
            threading.Thread(target=self._run, name="tray", daemon=True).start()

    def _run(self):
        def setup(icon):
            icon.visible = True
            self.running = True
        try:
            self.icon.run(setup=setup)
        except Exception as e:
            self.error = str(e)
            applog(f"tray icon error: {e}")
        finally:
            self.running = False

    def set_title(self, text):
        if self.available and self.icon.title != text[:127]:
            try:
                self.icon.title = text[:127]     # Windows tooltips are limited to 128 characters
            except Exception:
                pass

    def notify(self, message, title=None):
        if self.available:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    def stop(self):
        if self.icon is not None and self.running:
            try:
                self.icon.stop()
            except Exception:
                pass


# ----------------------------------------------------------------------------- crash log

_last_logged = {}


def _format(exc_type, exc, tb):
    return "".join(traceback.format_exception(exc_type, exc, tb)).rstrip()


def log_exception(where):
    """Write the current exception to vigilo.log (the exe has no console). The same error from the
    same place is written at most once a minute, so a failing 15 fps loop cannot flood the log."""
    exc_type, exc, tb = sys.exc_info()
    if exc_type is None:
        return
    key = (where, exc_type.__name__, str(exc))
    now = time.time()
    if now - _last_logged.get(key, 0) < 60:
        return
    _last_logged[key] = now
    applog(f"error in {where}:\n" + _format(exc_type, exc, tb))
    if sys.stderr:
        traceback.print_exception(exc_type, exc, tb)


def install_crash_log(root=None):
    """Unhandled errors (main thread, other threads, Tk callbacks) go to vigilo.log."""
    def excepthook(exc_type, exc, tb):
        applog("unhandled error:\n" + _format(exc_type, exc, tb))
        if sys.stderr:
            sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = excepthook

    def thread_hook(args):
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread else "?"
        applog(f"unhandled error in thread {name}:\n"
               + _format(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = thread_hook

    if root is not None:
        def tk_hook(exc_type, exc, tb):
            applog("error in the user interface:\n" + _format(exc_type, exc, tb))
            if sys.stderr:
                traceback.print_exception(exc_type, exc, tb)
        root.report_callback_exception = tk_hook
