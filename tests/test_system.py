"""Windows integration: keep awake, show signal of the running instance, crash log, watchdog."""
import os
import sys
import uuid

import pytest

from vigilo_app import common, supervisor, system
from vigilo_app.system import ES_CONTINUOUS, ES_SYSTEM_REQUIRED, KeepAwake, ShowSignal, signal_running_instance


def test_keep_awake_calls_windows_only_on_changes():
    calls = []
    k = KeepAwake(api=lambda flags: calls.append(flags) or 1)
    k.set(True)
    k.set(True)
    k.set(False)
    k.set(False)
    assert calls == [ES_CONTINUOUS | ES_SYSTEM_REQUIRED, ES_CONTINUOUS]


def test_keep_awake_failure_keeps_state():
    k = KeepAwake(api=lambda flags: 0)
    k.set(True)
    assert k.active is False


@pytest.mark.skipif(os.name != "nt", reason="Windows named events")
def test_show_signal_between_instances():
    name = "Vigilo_test_" + uuid.uuid4().hex
    assert signal_running_instance(name) is False          # nobody listening
    sig = ShowSignal(name)
    try:
        assert sig.poll() is False
        assert signal_running_instance(name) is True
        assert sig.poll() is True
        assert sig.poll() is False                          # auto-reset: one show per signal
    finally:
        sig.close()
    assert signal_running_instance(name) is False


def test_log_exception_is_rate_limited(monkeypatch):
    logged = []
    monkeypatch.setattr(system, "applog", logged.append)
    monkeypatch.setattr(system, "_last_logged", {})
    for _ in range(3):
        try:
            raise ValueError("boom")
        except ValueError:
            system.log_exception("a 15 fps loop")
    assert len(logged) == 1 and "ValueError: boom" in logged[0]


# ----------------------------------------------------------------------------- watchdog

def test_supervisor_wanted():
    assert supervisor.wanted([], environ={})
    assert not supervisor.wanted(["--child"], environ={})
    assert not supervisor.wanted(["--no-supervisor"], environ={})
    assert not supervisor.wanted([], environ={"VIGILO_NO_SUPERVISOR": "1"})


def test_child_command_from_source():
    cmd = supervisor.child_command(["--no-supervisor", "--restarted"], "C:/x/vigilo.py")
    assert cmd == [sys.executable, "C:/x/vigilo.py", "--restarted", "--child"]


def test_supervisor_config_dir_matches_the_program():
    assert supervisor.config_dir() == common.CONFIG_DIR


def test_decide():
    crashes = []
    assert supervisor.decide(0, crashes, 1000) == ("exit", 0)
    assert supervisor.decide(supervisor.EXIT_RESTART, crashes, 1000) == ("restart", 0)
    delays = [supervisor.decide(1, crashes, 1000 + i)[1] for i in range(4)]
    assert delays == [5, 10, 20, 40]
    assert supervisor.decide(0xC0000005, crashes, 1010) == ("give_up", 0)
    crashes[:] = [0, 1, 2, 3]                              # old crashes are forgotten
    assert supervisor.decide(1, crashes, 5000) == ("restart", 5)


def test_supervise_restart_crash_and_normal_exit():
    codes, cmds, sleeps = [supervisor.EXIT_RESTART, 7, 0], [], []

    def run(cmd):
        cmds.append(cmd)
        return codes.pop(0)
    assert supervisor.supervise(["vigilo"], run=run, sleep=sleeps.append) == 0
    assert cmds == [["vigilo"], ["vigilo"], ["vigilo", "--recovered"]]
    assert sleeps == [5]


def test_supervise_gives_up_on_a_crash_loop():
    gave_up, sleeps = [], []
    code = supervisor.supervise(["vigilo"], run=lambda cmd: 1, sleep=sleeps.append,
                                on_give_up=lambda: gave_up.append(True))
    assert code == 1 and gave_up == [True] and sleeps == [5, 10, 20, 40]


def test_supervise_real_process(tmp_path):
    counter = tmp_path / "runs"
    script = ("import sys, pathlib; p = pathlib.Path(sys.argv[1]); n = int(p.read_text()) if p.exists() else 0; "
              "p.write_text(str(n + 1)); sys.exit(9 if n == 0 else 0)")
    assert supervisor.supervise([sys.executable, "-c", script, str(counter)], sleep=lambda s: None) == 0
    assert counter.read_text() == "2"                      # crashed once, started again, closed normally
