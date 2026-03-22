from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pytest
from rich.console import Console


@pytest.fixture(autouse=True)
def _artifacts_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TAGSLUT_ARTIFACTS", str(tmp_path / "artifacts"))
    os.chdir(tmp_path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    now = time.time() + 3
    os.utime(path, (now, now))


def test_plain_report_is_stable_and_auditable(tmp_path: Path) -> None:
    from tagslut.exec import get_intake_console as mod

    started = time.time()
    decisions = tmp_path / "artifacts" / "compare" / "precheck_decisions_20260318_000000.csv"
    _write_text(
        decisions,
        (
            "domain,track_id,track_index,title,artist,decision,reason\n"
            "tidal,111,1,First Track,Alpha,keep,no inventory match\n"
            "tidal,222,2,Second Track,Beta,skip,same or better already exists\n"
        ),
    )
    raw_log = tmp_path / "artifacts" / "intake" / "logs" / "get_intake_20260318_000000.log"
    _write_text(raw_log, "")

    parser = mod.GetIntakeLogParser()
    for line in [
        "Intake Config\n",
        "  Source        tidal\n",
        "  URL           https://tidal.com/album/123/u\n",
        "  Batch root    /Volumes/MUSIC/mdl/tidal\n",
        "  DB            /tmp/music.db\n",
        "  Library root  /Volumes/MUSIC/MASTER_LIBRARY\n",
        "[1/2] Pre-download check\n",
        "Precheck\n",
        "  Total         2\n",
        "  Keep          1\n",
        "  Skip          1\n",
        "[2/2] Download from Tidal\n",
        "Selected for download: 1 track(s)\n",
        "[1/1] https://tidal.com/browse/track/111\n",
        "Downloaded First Track  16-bit, 44.1 kHz /Volumes/MUSIC/mdl/tidal/Alpha/Album A\n",
        "Tagged:  0\n",
        "Resolved 0 promoted identity ids\n",
    ]:
        parser.feed_line(line)
    report = parser.finalize()

    artifacts = mod._discover_artifacts(started=started, raw_log=raw_log)
    assert artifacts.precheck_decisions_csv is not None
    mod._load_precheck_decisions(report, artifacts.precheck_decisions_csv)
    mod.reconcile_outcomes(report)
    mod.apply_precheck_skips(report)
    mod._write_outcomes_csv(artifacts=artifacts, report=report)
    assert artifacts.outcomes_csv and artifacts.outcomes_csv.exists()

    buf = io.StringIO()
    mod._render_plain(report, artifacts, out=buf, success_limit=40)
    out = buf.getvalue()
    assert "\x1b[" not in out
    assert "tools/get Run" in out
    assert "Download Accountability:" in out
    assert "per-track:" in out


def test_source_selection_and_existing_dest_are_reported(tmp_path: Path) -> None:
    from tagslut.exec import get_intake_console as mod

    started = time.time()
    decisions = tmp_path / "artifacts" / "compare" / "precheck_decisions_20260318_000001.csv"
    _write_text(
        decisions,
        (
            "domain,source_link,track_id,track_index,isrc,title,artist,album,decision,reason,db_path,"
            "source_selection_attempted,source_selection_winner,source_selection_reason,tidal_audio_quality\n"
            "beatport,https://beatport.com/chart/x,111,1,USAAA111,Song A,Artist A,Album A,skip,"
            "same or better already exists,/Volumes/MUSIC/MASTER_LIBRARY/A.flac,1,tidal,tidal_verified_lossless,LOSSLESS\n"
            "beatport,https://beatport.com/chart/x,222,2,USBBB222,Song B,Artist B,Album B,keep,"
            "no inventory match,,1,beatport,tidal_not_better_quality,\n"
        ),
    )
    raw_log = tmp_path / "artifacts" / "intake" / "logs" / "get_intake_20260318_000001.log"
    _write_text(raw_log, "")

    report = mod.RunReport()
    artifacts = mod._discover_artifacts(started=started, raw_log=raw_log)
    assert artifacts.precheck_decisions_csv is not None
    mod._load_precheck_decisions(report, artifacts.precheck_decisions_csv)
    mod.apply_precheck_skips(report)
    mod._compute_precheck_counts(report)

    assert report.precheck_total == 2
    assert report.precheck_keep == 1
    assert report.precheck_skip == 1
    assert report.source_selection_attempted == 2
    assert report.source_selection_tidal == 1
    assert report.source_selection_beatport == 1
    assert report.source_selection_not_better == 1

    tr = report.tracks[("beatport", "111")]
    assert tr.outcome == "skipped"
    assert tr.dest.endswith("A.flac")


def test_rich_report_renders_key_sections(tmp_path: Path) -> None:
    from tagslut.exec import get_intake_console as mod

    started = time.time()
    decisions = tmp_path / "artifacts" / "compare" / "precheck_decisions_20260318_000002.csv"
    _write_text(
        decisions,
        (
            "domain,track_id,track_index,title,artist,decision,reason\n"
            "tidal,111,1,First Track,Alpha,keep,no inventory match\n"
            "tidal,222,2,Second Track,Beta,skip,same or better already exists\n"
        ),
    )
    raw_log = tmp_path / "artifacts" / "intake" / "logs" / "get_intake_20260318_000002.log"
    _write_text(raw_log, "")

    parser = mod.GetIntakeLogParser()
    for line in [
        "Intake Config\n",
        "  Source        tidal\n",
        "  URL           https://tidal.com/album/123/u\n",
        "  Batch root    /Volumes/MUSIC/mdl/tidal\n",
        "  DB            /tmp/music.db\n",
        "  Library root  /Volumes/MUSIC/MASTER_LIBRARY\n",
        "[1/1] Pre-download check\n",
        "Precheck\n",
        "  Total         2\n",
        "  Keep          1\n",
        "  Skip          1\n",
    ]:
        parser.feed_line(line)
    report = parser.finalize()

    artifacts = mod._discover_artifacts(started=started, raw_log=raw_log)
    assert artifacts.precheck_decisions_csv is not None
    mod._load_precheck_decisions(report, artifacts.precheck_decisions_csv)
    mod.apply_precheck_skips(report)
    mod._compute_precheck_counts(report)
    mod._write_outcomes_csv(artifacts=artifacts, report=report)

    console = Console(record=True, force_terminal=True, width=140)
    mod._render_rich(report, artifacts, verbose=False, success_limit=40, console=console)
    out = console.export_text()
    assert "tools/get Run" in out
    assert "Download Accountability" in out
    assert "Metadata / Tagging" in out
    assert "Key Artifacts" in out


def test_stage_header_gating_ignores_non_run_totals() -> None:
    from tagslut.exec import get_intake_console as mod

    parser = mod.GetIntakeLogParser()
    for line in [
        "Intake Config\n",
        "  Source        bpdl\n",
        "  URL           https://beatport.com/chart/x\n",
        "  Batch root    /Volumes/MUSIC/mdl/bpdl\n",
        "  DB            /tmp/music.db\n",
        "  Library root  /Volumes/MUSIC/MASTER_LIBRARY\n",
        "[1/10] Pre-download check\n",
        "[5/10] Local identify + tag prep\n",
        "[1/1] 07. Riva Starr - Vicino O' Mare (Reprise) (Extended Mix).flac\n",
        "Tagged:  1\n",
    ]:
        parser.feed_line(line)
    report = parser.finalize()

    assert len(report.stages) == 2
    assert report.stages[0].total == 10
    assert all("Riva Starr" not in st.name for st in report.stages)


def test_run_summary_kv_block_is_parsed() -> None:
    from tagslut.exec import get_intake_console as mod

    parser = mod.GetIntakeLogParser()
    for line in [
        "Run Summary\n",
        "  Precheck      keep=2 skip=33 total=35\n",
        "  Promoted      2\n",
        "  Stashed       0\n",
        "  Quarantine    1\n",
        "  Fix skips     3\n",
        "  Discard       4\n",
        "  Roon M3U      /Volumes/MUSIC/MASTER_LIBRARY/playlists/roon-bpdl-test.m3u\n",
        "  DJ exports    0\n",
        "  DJ M3U        /Volumes/MUSIC/DJ_LIBRARY/playlists/dj-bpdl-test.m3u\n",
        "→ poetry run python -m tagslut.exec.intake_pretty_summary --out-dir /tmp\n",
    ]:
        parser.feed_line(line)
    report = parser.finalize()

    assert report.precheck_keep == 2
    assert report.precheck_skip == 33
    assert report.precheck_total == 35
    assert report.run_promoted == 2
    assert report.run_stashed == 0
    assert report.run_quarantined == 1
    assert report.run_fix_skips == 3
    assert report.run_discarded == 4
    assert report.m3u_paths == ["/Volumes/MUSIC/MASTER_LIBRARY/playlists/roon-bpdl-test.m3u"]
    assert report.run_dj_exports == 0
    assert report.dj_m3u_paths == ["/Volumes/MUSIC/DJ_LIBRARY/playlists/dj-bpdl-test.m3u"]


def test_apply_plans_execute_counts_capture_skips() -> None:
    from tagslut.exec import get_intake_console as mod

    parser = mod.GetIntakeLogParser()
    parser.feed_line("EXECUTE: planned=2 moved=1 skipped_missing=3 skipped_exists=4 failed=0\n")
    report = parser.finalize()

    assert report.apply_planned == 2
    assert report.apply_moved == 1
    assert report.apply_skipped_missing == 3
    assert report.apply_skipped_exists == 4
    assert report.apply_failed == 0
