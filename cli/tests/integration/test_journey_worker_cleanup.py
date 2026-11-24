"""The journey must reap its own separate worker sessions on exit and cancellation."""

import importlib.util
import os
from pathlib import Path
import select
import signal
import subprocess
import sys

import pytest


PATH = Path(__file__).resolve().parents[1] / "journey/runtime.py"
SPEC = importlib.util.spec_from_file_location("journey_runtime_cleanup", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize("cancelled", [False, True])
def test_owned_worker_group_reaps_leader_and_term_resistant_child(tmp_path, cancelled):
    """A leader exit alone cannot leave its same-group prefork child alive."""
    ready = tmp_path / "child-ready"
    child_code = (
        "import signal,sys,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "Path(sys.argv[1]).write_text('ready'); time.sleep(360)"
    )
    leader_code = (
        "import signal,subprocess,sys,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN if sys.argv[2]=='1' "
        "else lambda *_: sys.exit(0)); "
        "child=subprocess.Popen([sys.executable,'-c',sys.argv[3],sys.argv[1]]); "
        "ready=Path(sys.argv[1]); "
        "[time.sleep(.01) for _ in range(500) if not ready.exists()]; "
        "print(child.pid,flush=True); time.sleep(360)"
    )
    leader = subprocess.Popen(
        [sys.executable, "-c", leader_code, str(ready), str(int(cancelled)), child_code],
        start_new_session=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert leader.stdout is not None
        assert select.select([leader.stdout], [], [], 5)[0]
        child = int(leader.stdout.readline().strip())
        assert ready.is_file()
        assert MODULE._live_group_members(leader.pid) == {leader.pid, child}
        if cancelled:
            MODULE._interrupt_owned_groups([leader])
        else:
            MODULE._stop_owned_group(leader, graceful_seconds=0.2, force_seconds=3)
        leader.wait(timeout=5)
        assert not MODULE._live_group_members(leader.pid)
    finally:
        if MODULE._live_group_members(leader.pid):
            os.killpg(leader.pid, signal.SIGKILL)
        leader.wait(timeout=5)
        if leader.stdout is not None:
            leader.stdout.close()


def test_group_exit_between_snapshot_and_signal_is_already_drained(monkeypatch):
    class Exited:
        pid = 424242

        def poll(self):
            return 0

        def wait(self, *, timeout):
            return 0

    observations = iter(({Exited.pid}, set(), set()))
    monkeypatch.setattr(MODULE, "_live_group_members", lambda _: next(observations))
    monkeypatch.setattr(
        MODULE.os,
        "killpg",
        lambda *_: (_ for _ in ()).throw(ProcessLookupError()),
    )
    MODULE._stop_owned_group(Exited(), graceful_seconds=0, force_seconds=0)


def test_failed_group_does_not_skip_other_owned_group(monkeypatch):
    first, second = object(), object()
    expected = RuntimeError("first group refused to drain")
    observed = []

    def stop(process):
        observed.append(process)
        if process is second:
            raise expected

    monkeypatch.setattr(MODULE, "_stop_owned_group", stop)
    assert MODULE._stop_owned_groups([first, second]) is expected
    assert observed == [second, first]
