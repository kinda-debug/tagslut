from __future__ import annotations

import io

from tagslut.utils.console_ui import ConsoleUI


def test_console_ui_plain_mode_avoids_ansi_sequences() -> None:
    stream = io.StringIO()
    ui = ConsoleUI(stream=stream, err_stream=io.StringIO(), force_tty=False)

    ui.begin_command("Scan", target="/Volumes/MUSIC/library/Artist/Album/track.flac", mode="dry-run")
    ui.stage("Register", "ok", detail="done")
    ui.finish("ok", [("Updated", 1)])

    output = stream.getvalue()
    assert "== Scan ==" in output
    assert "[OK] Register" in output
    assert "Updated: 1" in output
    assert "\x1b[" not in output


def test_console_ui_rich_mode_emits_styled_output() -> None:
    stream = io.StringIO()
    ui = ConsoleUI(stream=stream, err_stream=io.StringIO(), force_tty=True)

    ui.begin_command("Scan", target="/tmp/input.flac", mode="execute")
    ui.stage("Register", "ok", detail="done")

    output = stream.getvalue()
    assert "Scan" in output
    assert "Register" in output
    assert "\x1b[" in output


def test_console_ui_abbreviates_paths_when_not_verbose() -> None:
    ui = ConsoleUI(stream=io.StringIO(), err_stream=io.StringIO(), force_tty=False)
    path = "/Volumes/MUSIC/MASTER_LIBRARY/Very/Long/Path/To/Some/Deeply/Nested/Track Name.flac"

    rendered = ui.display_path(path)

    assert rendered != path
    assert "Track Name.flac" in rendered


def test_console_ui_preserves_full_paths_in_verbose_mode() -> None:
    ui = ConsoleUI(verbose=True, stream=io.StringIO(), err_stream=io.StringIO(), force_tty=False)
    path = "/Volumes/MUSIC/MASTER_LIBRARY/Very/Long/Path/To/Some/Deeply/Nested/Track Name.flac"

    assert ui.display_path(path) == path
