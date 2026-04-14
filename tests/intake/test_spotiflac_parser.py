from __future__ import annotations

from pathlib import Path

from tagslut.intake.spotiflac_parser import (
    _detect_format,
    build_manifest,
    classify_failure_reason,
    parse_log,
    parse_log_next,
)


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

NEXT_FORMAT_LOG = """\
Download Report - 4/13/2026, 4:59:33 PM
--------------------------------------------------

[SUCCESS] What's Next - Ramon Tapia
[SUCCESS] Shanghai Spinner - Oliver Huntemann
1. Der Spatz Auf Dem Dach - Peter Juergens; Oliver Klein (Berlin Underground Selection)
   Error: [Qobuz A] track not found for ISRC: DEAA20900927 | [Deezer A] deezer api returned status: 502
   ID: 4CMBoQOCX7KNjJqCB800Rm
   URL: https://open.spotify.com/track/4CMBoQOCX7KNjJqCB800Rm

2. Show of Hands - Bushwacka! (Berlin Underground Selection)
   Error: [Apple Music] Song not available in ALAC | [Qobuz A] track not found for ISRC: GBLPN0900005
   ID: 70MluEOJd2DaXur42Kk2rC
   URL: https://open.spotify.com/track/70MluEOJd2DaXur42Kk2rC

[SUCCESS] Burn Myself - Coyu; Edu Imbernon
"""


def _write_next_log(tmp_path: Path, name: str = "Berlin Underground Selection.txt") -> Path:
    log_path = tmp_path / name
    log_path.write_text(NEXT_FORMAT_LOG, encoding="utf-8")
    return log_path


def _parse_next_tracks(tmp_path: Path) -> list:
    return parse_log_next(_write_next_log(tmp_path))


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


def test_detect_format_next(tmp_path: Path) -> None:
    assert _detect_format(_write_next_log(tmp_path)) == "next"


def test_detect_format_legacy(tmp_path: Path) -> None:
    log_path = tmp_path / "legacy.txt"
    log_path.write_text(
        "[00:54:07] [debug] trying qobuz for: Track - Artist\n",
        encoding="utf-8",
    )
    assert _detect_format(log_path) == "legacy"


def test_parse_log_next_success_count(tmp_path: Path) -> None:
    tracks = _parse_next_tracks(tmp_path)
    assert len([track for track in tracks if not track.failed]) == 3
    assert len([track for track in tracks if track.failed]) == 2


def test_parse_log_next_isrc_extracted(tmp_path: Path) -> None:
    failed_tracks = [track for track in _parse_next_tracks(tmp_path) if track.failed]
    assert failed_tracks[0].isrc == "DEAA20900927"


def test_parse_log_next_spotify_id(tmp_path: Path) -> None:
    failed_tracks = [track for track in _parse_next_tracks(tmp_path) if track.failed]
    assert failed_tracks[0].spotify_id == "4CMBoQOCX7KNjJqCB800Rm"


def test_parse_log_next_display_title_strips_playlist(tmp_path: Path) -> None:
    failed_tracks = [track for track in _parse_next_tracks(tmp_path) if track.failed]
    assert (
        failed_tracks[0].display_title
        == "Der Spatz Auf Dem Dach - Peter Juergens; Oliver Klein"
    )


def test_parse_log_next_succeeded_provider_unknown(tmp_path: Path) -> None:
    succeeded_tracks = [track for track in _parse_next_tracks(tmp_path) if not track.failed]
    assert succeeded_tracks[0].provider == "unknown"


def test_build_manifest_next_prefers_original_m3u8(tmp_path: Path) -> None:
    log_path = _write_next_log(tmp_path)
    (tmp_path / "Berlin Underground Selection.m3u8").write_text(
        """\
#EXTM3U
What's Next - Ramon Tapia.flac
Shanghai Spinner - Oliver Huntemann.flac
Burn Myself - Coyu; Edu Imbernon.flac
""",
        encoding="utf-8",
    )
    (tmp_path / "Berlin Underground Selection_converted.m3u8").write_text(
        """\
#EXTM3U
What's Next - Ramon Tapia.mp3
Shanghai Spinner - Oliver Huntemann.mp3
Burn Myself - Coyu; Edu Imbernon.mp3
""",
        encoding="utf-8",
    )
    (tmp_path / "Berlin Underground Selection_Failed.txt").write_text(
        """\
1. Der Spatz Auf Dem Dach - Peter Juergens; Oliver Klein
   Error: should be ignored
""",
        encoding="utf-8",
    )

    tracks = build_manifest(log_path)
    by_title = {track.display_title: track for track in tracks}

    assert by_title["What's Next - Ramon Tapia"].file_path is not None
    assert by_title["What's Next - Ramon Tapia"].file_path.name == "What's Next - Ramon Tapia.flac"
    assert by_title["Der Spatz Auf Dem Dach - Peter Juergens; Oliver Klein"].failure_reason is not None
    assert "deezer api returned status: 502" in (
        by_title["Der Spatz Auf Dem Dach - Peter Juergens; Oliver Klein"].failure_reason or ""
    ).lower()


def test_spotiflacnext_manifest_parsing(tmp_path: Path) -> None:
    log_path = _write_next_log(tmp_path)
    m3u8_path = tmp_path / "Berlin Underground Selection_converted.m3u8"
    m3u8_path.write_text(
        """\
#EXTM3U
What's Next - Ramon Tapia.mp3
Shanghai Spinner - Oliver Huntemann.mp3
Burn Myself - Coyu; Edu Imbernon.mp3
""",
        encoding="utf-8",
    )

    tracks = build_manifest(log_path, m3u8_path=m3u8_path)
    by_title = {track.display_title: track for track in tracks}

    success = by_title["What's Next - Ramon Tapia"]
    assert success.failed is False
    assert success.provider == "unknown"
    assert success.spotify_id is None
    assert success.file_path is not None


def test_parse_log_extracts_spotify_album_id(tmp_path: Path) -> None:
    log_path = tmp_path / "legacy_spotify.log"
    log_path.write_text(
        """\
[08:38:51] [info] fetching album metadata...
[08:38:51] [debug] url: https://open.spotify.com/album/2U0b5MfkMUgzdvRUI69mya
[08:39:05] [debug] trying qobuz for: Track One - Artist A
[08:39:08] [success] qobuz: Track One - Artist A
[08:39:08] [success] downloaded: Track One - Artist A
""",
        encoding="utf-8",
    )
    tracks = parse_log(log_path)
    assert tracks[0].spotify_id == "2U0b5MfkMUgzdvRUI69mya"
    assert tracks[0].album_source_url == "https://open.spotify.com/album/2U0b5MfkMUgzdvRUI69mya"


def test_parse_log_extracts_qobuz_album_id(tmp_path: Path) -> None:
    log_path = tmp_path / "legacy_qobuz.log"
    log_path.write_text(
        """\
[08:48:08] [info] fetching direct link metadata...
[08:48:08] [debug] url: https://open.qobuz.com/album/ldgvxrkvvvfpb
[08:48:17] [debug] direct link: trying qobuz for: Someone Like You  - Fred Everything
[08:48:48] [success] direct link qobuz: Someone Like You  - Fred Everything
[08:48:48] [success] downloaded: Someone Like You  - Fred Everything
""",
        encoding="utf-8",
    )
    tracks = parse_log(log_path)
    assert tracks[0].qobuz_album_id == "ldgvxrkvvvfpb"
    assert tracks[0].spotify_id is None


def test_parse_log_multi_batch_ids_do_not_bleed(tmp_path: Path) -> None:
    log_path = tmp_path / "legacy_multi.log"
    log_path.write_text(
        """\
[08:38:51] [info] fetching album metadata...
[08:38:51] [debug] url: https://open.spotify.com/album/2U0b5MfkMUgzdvRUI69mya
[08:39:05] [debug] trying qobuz for: Track One - Artist A
[08:39:08] [success] qobuz: Track One - Artist A
[08:39:08] [success] downloaded: Track One - Artist A
[08:48:08] [info] fetching direct link metadata...
[08:48:08] [debug] url: https://open.qobuz.com/album/ldgvxrkvvvfpb
[08:48:17] [debug] direct link: trying qobuz for: Someone Like You  - Fred Everything
[08:48:48] [success] direct link qobuz: Someone Like You  - Fred Everything
[08:48:48] [success] downloaded: Someone Like You  - Fred Everything
""",
        encoding="utf-8",
    )
    tracks = parse_log(log_path)
    assert tracks[0].spotify_id == "2U0b5MfkMUgzdvRUI69mya"
    assert tracks[0].qobuz_album_id is None
    assert tracks[1].qobuz_album_id == "ldgvxrkvvvfpb"
    assert tracks[1].spotify_id is None
