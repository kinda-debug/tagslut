from __future__ import annotations

from pathlib import Path

from tagslut.intake.spotiflac_parser import build_manifest, classify_failure_reason


SAMPLE_LOG = """\
[00:54:07] [debug] trying qobuz for: Urmel - okuma
[00:54:08] [error] qobuz error: track not found for ISRC: DEPQ62201210
[00:54:08] [debug] trying tidal for: Urmel - okuma
[00:54:48] [success] tidal: Urmel - okuma
[00:54:48] [success] downloaded: Urmel - okuma
[00:54:53] [debug] trying qobuz for: Low Battery - Atric, Frida Darko
[00:54:54] [error] qobuz error: track not found for ISRC: DEY472275018
[00:54:54] [debug] trying amazon for: Low Battery - Atric, Frida Darko
[00:54:55] [success] amazon: Low Battery - Atric, Frida Darko
[00:54:55] [success] downloaded: Low Battery - Atric, Frida Darko
[01:27:08] [debug] trying qobuz for: Wirrwarr - NUAH Remix - Air Horse One, NUAH
[01:27:09] [error] qobuz error: track not found for ISRC: US83Z2476192
[01:27:09] [debug] trying tidal for: Wirrwarr - NUAH Remix - Air Horse One, NUAH
[01:27:10] [error] tidal error: failed to write file: write /Volumes/SAD/...: input/output error
[01:27:10] [error] failed: Wirrwarr - NUAH Remix - Air Horse One, NUAH
"""

SAMPLE_M3U8 = """\
#EXTM3U
../Playlist/okuma/[2022] Urmel Kalkutta/Urmel - okuma.flac
../Playlist/Atric, Frida Darko/[2022] Low Battery/Low Battery - Atric, Frida Darko.flac
"""


def test_spotiflac_manifest_parsing(tmp_path: Path) -> None:
    log_path = tmp_path / "SpotiFLAC_20260413_005407.txt"
    m3u8_path = tmp_path / "Playlist.m3u8"

    log_path.write_text(SAMPLE_LOG, encoding="utf-8")
    m3u8_path.write_text(SAMPLE_M3U8, encoding="utf-8")

    tracks = build_manifest(log_path, m3u8_path=m3u8_path)
    by_title = {t.display_title: t for t in tracks}

    urmel = by_title["Urmel - okuma"]
    assert urmel.isrc == "DEPQ62201210"
    assert urmel.provider == "tidal"
    assert urmel.failed is False
    assert urmel.file_path is not None
    assert urmel.file_path.name == "Urmel - okuma.flac"

    low_battery = by_title["Low Battery - Atric, Frida Darko"]
    assert low_battery.isrc == "DEY472275018"
    assert low_battery.provider == "amazon"
    assert low_battery.failed is False
    assert low_battery.file_path is not None
    assert low_battery.file_path.name == "Low Battery - Atric, Frida Darko.flac"

    wirrwarr = by_title["Wirrwarr - NUAH Remix - Air Horse One, NUAH"]
    assert wirrwarr.isrc == "US83Z2476192"
    assert wirrwarr.failed is True
    assert wirrwarr.failure_reason is not None
    assert "input/output error" in wirrwarr.failure_reason.lower()
    assert classify_failure_reason(wirrwarr.failure_reason) == "retryable"

