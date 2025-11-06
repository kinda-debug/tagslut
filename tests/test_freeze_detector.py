import time
from types import SimpleNamespace

from scripts.lib import common


def test_freeze_detector_issues_pkill_term_then_kill(monkeypatch):
    """Ensure freeze detector calls pkill -TERM then pkill -KILL.

    The test mocks shutil.which and subprocess.run so no real signals
    are sent.
    """

    # Make the last progress timestamp look old so the detector triggers
    common.last_progress_timestamp = time.time() - 60.0
    common.last_progress_file = "/tmp/fake_stalled.flac"
    common.freeze_detector_stop.clear()

    calls = []

    def fake_which(name):
        if name in ("pkill", "pgrep", "killall"):
            return f"/usr/bin/{name}"
        return None

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        # Simulate pgrep finding ffmpeg processes
        if cmd and isinstance(cmd, (list, tuple)) and cmd[0].endswith("pgrep"):
            return SimpleNamespace(returncode=0, stdout=b"123\n")
        return SimpleNamespace(returncode=0, stdout=b"")

    monkeypatch.setattr(common.shutil, "which", fake_which)
    monkeypatch.setattr(common.subprocess, "run", fake_run)

    # Start the watcher thread and wait for it to finish
    thr = common.start_freeze_detector_watcher(
        root=None, auto_quarantine=False, kill_in_terminal=False
    )
    thr.join(timeout=10)

    assert not thr.is_alive()

    found_term = any(
        call[:3] == ["/usr/bin/pkill", "-TERM", "ffmpeg"] for call in calls
    )
    found_kill = any(
        call[:3] == ["/usr/bin/pkill", "-KILL", "ffmpeg"] for call in calls
    )

    assert found_term, f"TERM pkill not called, calls={calls}"
    assert found_kill, f"KILL pkill not called, calls={calls}"

    # Make sure other tests are not affected
    common.freeze_detector_stop.set()
