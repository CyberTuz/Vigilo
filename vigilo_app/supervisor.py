"""
Watchdog: runs the real program as a child process and starts it again if it crashes.

Standard library only (plus the tiny i18n module), so the supervisor process costs almost nothing
while it waits. What happens when the child exits:
  0             closed normally -> the supervisor exits too
  EXIT_RESTART  start again now (for example after a language change)
  anything else crash -> start again after a pause (5 s, doubling up to 60 s), with --recovered;
                after MAX_CRASHES crashes within CRASH_WINDOW seconds it gives up and says so.
"""

import os
import sys
import json
import time
import datetime
import subprocess

EXIT_RESTART = 3
MAX_CRASHES = 5
CRASH_WINDOW = 600
BASE_DELAY = 5
MAX_DELAY = 60
SUPERVISOR_FLAGS = ("--no-supervisor",)


def wanted(argv, environ=None):
    """True when this process should act as the supervisor (normal start of Vigilo)."""
    environ = os.environ if environ is None else environ
    return not ({"--child", "--no-supervisor"} & set(argv)) and environ.get("VIGILO_NO_SUPERVISOR") != "1"


def child_command(argv, entry_script):
    args = [a for a in argv if a not in SUPERVISOR_FLAGS] + ["--child"]
    if getattr(sys, "frozen", False):
        return [sys.executable] + args
    return [sys.executable, entry_script] + args


def config_dir(environ=None):
    """Same rule as common.CONFIG_DIR (repeated here so that the supervisor stays light)."""
    environ = os.environ if environ is None else environ
    appdata = environ.get("APPDATA", os.path.expanduser("~"))
    return (environ.get("VIGILO_CONFIG_DIR") or environ.get("TELECAMERE_CONFIG_DIR")
            or os.path.join(appdata, "Vigilo"))


def log(msg):
    try:
        d = config_dir()
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "vigilo.log"), "a", encoding="utf-8") as f:
            f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + "[watchdog] " + msg + "\n")
    except OSError:
        pass


def decide(code, crashes, now, max_crashes=MAX_CRASHES, window=CRASH_WINDOW):
    """What to do after the child exited with `code`. `crashes` holds the times of the recent
    crashes and is updated in place. Returns ("exit" | "restart" | "give_up", delay_seconds)."""
    if code == 0:
        return "exit", 0
    if code == EXIT_RESTART:
        return "restart", 0
    crashes[:] = [t for t in crashes if now - t < window] + [now]
    if len(crashes) >= max_crashes:
        return "give_up", 0
    return "restart", min(MAX_DELAY, BASE_DELAY * 2 ** (len(crashes) - 1))


def _run_child(cmd):
    return subprocess.call(cmd)


def _show_give_up():
    try:
        from i18n import tr, set_language
        try:
            with open(os.path.join(config_dir(), "config.json"), encoding="utf-8") as f:
                set_language(json.load(f).get("settings", {}).get("lang", "en"))
        except (OSError, ValueError):
            pass
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, tr("Vigilo stopped working several times in a row and will not be restarted again.\n"
                     "Details are in vigilo.log in {folder}.").format(folder=config_dir()), "Vigilo", 0x30)
    except Exception:
        pass


def supervise(cmd, run=_run_child, sleep=time.sleep, clock=time.time, on_give_up=_show_give_up):
    """Run `cmd` (the child command line) until it closes normally. Returns the exit code."""
    crashes = []
    extra = []
    while True:
        try:
            code = run(cmd + extra)
        except KeyboardInterrupt:
            return 0
        except OSError as e:
            log(f"cannot start Vigilo: {e}")
            return 1
        action, delay = decide(code, crashes, clock())
        if action == "exit":
            return 0
        if action == "give_up":
            log(f"Vigilo exited with an error {len(crashes)} times in {CRASH_WINDOW // 60} minutes "
                f"(last exit code {code}): it will not be restarted again")
            on_give_up()
            return code
        if code == EXIT_RESTART:
            extra = []
        else:
            log(f"Vigilo exited with an error (exit code {code}, 0x{code & 0xFFFFFFFF:08X}): "
                f"restarting it in {delay} s")
            extra = ["--recovered"]
        if delay:
            try:
                sleep(delay)
            except KeyboardInterrupt:
                return 0
