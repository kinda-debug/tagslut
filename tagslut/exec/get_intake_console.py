from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from rich.console import Console
from rich.rule import Rule

from tagslut.utils.env_paths import get_artifacts_dir


StageStatus = Literal["pending", "running", "ok", "skipped", "failed"]
TrackOutcome = Literal["downloaded", "present", "skipped", "failed", "unknown"]


_STEP_RE = re.compile(r"^\[(\d+)/(\d+)\]\s+(.*)$")
_CONFIG_KV_RE = re.compile(r"^\s{2}([A-Za-z][A-Za-z0-9 /_-]*?)\s{2,}(.+?)\s*$")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_TIDAL_TRACK_ID_RE = re.compile(r"/(?:browse/)?track/(\d+)", re.IGNORECASE)
_BPDL_OK_RE = re.compile(r"^[✓✔]\s+(.+?)(?:\s+\[(.+?)\])?\s*$")
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _norm_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def _abbrev_path(path: str, *, roots: dict[str, str]) -> str:
    value = (path or "").strip()
    if not value:
        return ""
    for label, root in roots.items():
        if root and value.startswith(root.rstrip("/") + "/"):
            return f"{label}:{value[len(root.rstrip('/'))+1:]}"
    if len(value) <= 72:
        return value
    head = value[:34]
    tail = value[-34:]
    return f"{head}…{tail}"


@dataclass
class Stage:
    idx: int
    total: int
    name: str
    status: StageStatus = "pending"
    details: list[str] = field(default_factory=list)


@dataclass
class TrackRow:
    domain: str
    source_link: str
    track_id: str
    isrc: str
    index: int | None
    title: str
    artist: str
    album: str
    precheck_decision: str
    confidence: str
    match_method: str
    precheck_reason: str
    db_path: str = ""
    db_download_source: str = ""
    existing_quality_rank: int | None = None
    candidate_quality_rank: int | None = None
    source_selection_attempted: bool = False
    source_selection_winner: str = ""
    source_selection_reason: str = ""
    tidal_match_method: str = ""
    tidal_track_id: str = ""
    tidal_audio_quality: str = ""
    tidal_audio_quality_rank: int | None = None
    duration_diff_ms: int | None = None
    outcome: TrackOutcome = "unknown"
    outcome_reason: str = ""
    dest: str = ""
    quality: str = ""
    inferred_from_log: bool = False


@dataclass
class RunArtifacts:
    raw_log: Path
    compare_dir: Path
    precheck_decisions_csv: Path | None = None
    precheck_tracks_csv: Path | None = None
    keep_urls_txt: Path | None = None
    keep_tidal_urls_txt: Path | None = None
    keep_bpdl_urls_txt: Path | None = None
    precheck_summary_csv: Path | None = None
    precheck_report_md: Path | None = None
    outcomes_csv: Path | None = None
    plan_summary_json: Path | None = None
    plan_promote_csv: Path | None = None
    plan_stash_csv: Path | None = None
    plan_quarantine_csv: Path | None = None
    fix_plan_summary_json: Path | None = None
    discard_plan_summary_json: Path | None = None
    moves_jsonl: Path | None = None
    promoted_txt: Path | None = None
    genre_normalization_report: Path | None = None
    genre_normalization_rows_csv: Path | None = None
    tag_hoard_summary_json: Path | None = None
    tag_hoard_values_csv: Path | None = None
    dj_identity_ids_txt: Path | None = None
    dj_manifest_csv: Path | None = None
    dj_receipts_jsonl: Path | None = None
    dj_playlist_inputs_txt: Path | None = None
    roon_m3u_inputs_txt: Path | None = None


@dataclass
class RunReport:
    source: str = ""
    url: str = ""
    batch_root: str = ""
    db_path: str = ""
    library_root: str = ""
    toggles: dict[str, str] = field(default_factory=dict)
    stages: list[Stage] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    requested_total: int | None = None
    precheck_total: int | None = None
    precheck_keep: int | None = None
    precheck_skip: int | None = None
    precheck_skip_reason_counts: dict[str, int] = field(default_factory=dict)
    selected_for_download: int | None = None
    source_selection_attempted: int | None = None
    source_selection_tidal: int | None = None
    source_selection_beatport: int | None = None
    source_selection_ambiguous: int | None = None
    source_selection_unverified: int | None = None
    source_selection_not_better: int | None = None
    source_selection_unavailable: int | None = None

    download_downloaded: int = 0
    download_present: int = 0
    download_failed: int = 0

    scan_discovered: int | None = None
    scan_succeeded: int | None = None
    scan_failed: int | None = None
    scan_failure_breakdown: dict[str, int] = field(default_factory=dict)

    plan_promote_move: int | None = None
    plan_promote_skip: int | None = None
    plan_stash_move: int | None = None
    plan_quarantine_move: int | None = None
    fix_planned_move: int | None = None
    discard_planned_move: int | None = None

    apply_planned: int | None = None
    apply_moved: int | None = None
    apply_skipped_missing: int | None = None
    apply_skipped_exists: int | None = None
    apply_failed: int | None = None

    m3u_count: int | None = None
    m3u_paths: list[str] = field(default_factory=list)
    dj_m3u_paths: list[str] = field(default_factory=list)

    hoard_scanned_files: int | None = None
    normalize_genres_scanned: int | None = None
    normalize_genres_updated: int | None = None
    tag_normalized_genres_scanned: int | None = None
    tag_normalized_genres_tagged: int | None = None

    tagged_count: int | None = None
    dj_identity_resolved: int | None = None
    run_promoted: int | None = None
    run_stashed: int | None = None
    run_quarantined: int | None = None
    run_fix_skips: int | None = None
    run_discarded: int | None = None
    run_dj_exports: int | None = None

    tracks: dict[tuple[str, str], TrackRow] = field(default_factory=dict)
    track_order: list[tuple[str, str]] = field(default_factory=list)
    pending_download_by_key: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    pending_download_by_title: list[dict[str, str]] = field(default_factory=list)
    keep_track_keys: list[tuple[str, str]] = field(default_factory=list)


def _latest_after(dir_path: Path, pattern: str, *, started: float) -> Path | None:
    if not dir_path.exists():
        return None
    candidates = sorted(dir_path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates:
        try:
            if p.stat().st_mtime >= started - 1.0:
                return p
        except OSError:
            continue
    return None


def _run_stamp_from_raw_log(raw_log: Path) -> str | None:
    stem = raw_log.stem
    prefix = "get_intake_"
    if not stem.startswith(prefix):
        return None
    stamp = stem[len(prefix) :]
    return stamp or None


def _artifact_for_run(
    dir_path: Path,
    pattern: str,
    *,
    started: float,
    run_stamp: str | None,
) -> Path | None:
    if not dir_path.exists():
        return None

    candidates: list[Path] = []
    for path in dir_path.glob(pattern):
        try:
            if path.stat().st_mtime >= started - 1.0:
                candidates.append(path)
        except OSError:
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    if run_stamp:
        stamped = [path for path in candidates if path.stem.endswith(f"_{run_stamp}")]
        if stamped:
            return stamped[0]

    return candidates[0]


def _discover_artifacts(*, started: float, raw_log: Path) -> RunArtifacts:
    artifacts_root = get_artifacts_dir().expanduser().resolve()
    compare_dir = artifacts_root / "compare"
    run_stamp = _run_stamp_from_raw_log(raw_log)
    out = RunArtifacts(raw_log=raw_log, compare_dir=compare_dir)
    out.precheck_decisions_csv = _artifact_for_run(
        compare_dir, "precheck_decisions_*.csv", started=started, run_stamp=run_stamp
    )
    out.precheck_tracks_csv = _artifact_for_run(
        compare_dir, "precheck_tracks_extracted_*.csv", started=started, run_stamp=run_stamp
    )
    out.keep_urls_txt = _artifact_for_run(
        compare_dir, "precheck_keep_track_urls_*.txt", started=started, run_stamp=run_stamp
    )
    out.keep_tidal_urls_txt = _artifact_for_run(
        compare_dir, "precheck_keep_tidal_urls_*.txt", started=started, run_stamp=run_stamp
    )
    out.keep_bpdl_urls_txt = _artifact_for_run(
        compare_dir, "precheck_keep_bpdl_urls_*.txt", started=started, run_stamp=run_stamp
    )
    out.precheck_summary_csv = _artifact_for_run(
        compare_dir, "precheck_summary_*.csv", started=started, run_stamp=run_stamp
    )
    out.precheck_report_md = _artifact_for_run(
        compare_dir, "precheck_report_*.md", started=started, run_stamp=run_stamp
    )
    out.plan_summary_json = _artifact_for_run(
        compare_dir, "plan_fpcalc_unique_final_summary_*.json", started=started, run_stamp=run_stamp
    )
    out.plan_promote_csv = _artifact_for_run(
        compare_dir, "plan_promote_fpcalc_unique_final_*.csv", started=started, run_stamp=run_stamp
    )
    out.plan_stash_csv = _artifact_for_run(
        compare_dir, "plan_stash_fpcalc_unique_final_*.csv", started=started, run_stamp=run_stamp
    )
    out.plan_quarantine_csv = _artifact_for_run(
        compare_dir, "plan_quarantine_fpcalc_unique_final_*.csv", started=started, run_stamp=run_stamp
    )
    out.fix_plan_summary_json = _artifact_for_run(
        compare_dir, "plan_move_skipped_to_fix_summary_*.json", started=started, run_stamp=run_stamp
    )
    out.discard_plan_summary_json = _artifact_for_run(
        compare_dir, "plan_move_skipped_to_discard_summary_*.json", started=started, run_stamp=run_stamp
    )
    out.promoted_txt = _artifact_for_run(
        compare_dir, "promoted_audio_*.txt", started=started, run_stamp=run_stamp
    ) or _artifact_for_run(
        compare_dir, "promoted_flacs_*.txt", started=started, run_stamp=run_stamp
    )
    out.moves_jsonl = _latest_after(artifacts_root, "moves_*.jsonl", started=started)
    report_md = artifacts_root / "genre_normalization_report.md"
    if report_md.exists() and report_md.stat().st_mtime >= started - 1.0:
        out.genre_normalization_report = report_md
    rows_csv = artifacts_root / "genre_normalization_rows.csv"
    if rows_csv.exists() and rows_csv.stat().st_mtime >= started - 1.0:
        out.genre_normalization_rows_csv = rows_csv
    hoard_summary = (Path("tag_hoard_out") / "tags_summary.json").resolve()
    if hoard_summary.exists() and hoard_summary.stat().st_mtime >= started - 1.0:
        out.tag_hoard_summary_json = hoard_summary
    hoard_values = (Path("tag_hoard_out") / "tags_values.csv").resolve()
    if hoard_values.exists() and hoard_values.stat().st_mtime >= started - 1.0:
        out.tag_hoard_values_csv = hoard_values
    out.dj_identity_ids_txt = _artifact_for_run(
        compare_dir, "dj_identity_ids_*.txt", started=started, run_stamp=run_stamp
    )
    out.dj_manifest_csv = _artifact_for_run(
        compare_dir, "dj_manifest_*.csv", started=started, run_stamp=run_stamp
    )
    out.dj_receipts_jsonl = _artifact_for_run(
        compare_dir, "dj_receipts_*.jsonl", started=started, run_stamp=run_stamp
    )
    out.dj_playlist_inputs_txt = _artifact_for_run(
        compare_dir, "dj_playlist_inputs_*.txt", started=started, run_stamp=run_stamp
    )
    out.roon_m3u_inputs_txt = _artifact_for_run(
        compare_dir, "roon_m3u_inputs_*.txt", started=started, run_stamp=run_stamp
    )
    return out


def _load_precheck_decisions(report: RunReport, path: Path) -> None:
    def _parse_int(value: str | None) -> int | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(text)
        except Exception:
            return None

    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            domain = (row.get("domain") or "").strip()
            source_link = (row.get("source_link") or "").strip()
            track_id = (row.get("track_id") or "").strip()
            isrc = (row.get("isrc") or "").strip()
            if not domain or not track_id:
                continue
            index = None
            try:
                index = int((row.get("track_index") or "").strip() or "0") or None
            except Exception:
                index = None
            tr = TrackRow(
                domain=domain,
                source_link=source_link,
                track_id=track_id,
                isrc=isrc,
                index=index,
                title=(row.get("title") or "").strip(),
                artist=(row.get("artist") or "").strip(),
                album=(row.get("album") or "").strip(),
                precheck_decision=(row.get("decision") or row.get("action") or "").strip().lower(),
                confidence=(row.get("confidence") or "").strip(),
                match_method=(row.get("match_method") or "").strip(),
                precheck_reason=(row.get("reason") or "").strip(),
            )
            tr.db_path = (row.get("db_path") or "").strip()
            tr.db_download_source = (row.get("db_download_source") or "").strip()
            tr.existing_quality_rank = _parse_int(row.get("existing_quality_rank"))
            tr.candidate_quality_rank = _parse_int(row.get("candidate_quality_rank"))
            tr.source_selection_attempted = str(row.get("source_selection_attempted") or "").strip() in {
                "1",
                "true",
                "yes",
            }
            tr.source_selection_winner = (row.get("source_selection_winner") or "").strip()
            tr.source_selection_reason = (row.get("source_selection_reason") or "").strip()
            tr.tidal_match_method = (row.get("tidal_match_method") or "").strip()
            tr.tidal_track_id = (row.get("tidal_track_id") or "").strip()
            tr.tidal_audio_quality = (row.get("tidal_audio_quality") or "").strip()
            tr.tidal_audio_quality_rank = _parse_int(row.get("tidal_audio_quality_rank"))
            tr.duration_diff_ms = _parse_int(row.get("duration_diff_ms"))
            key = (domain, track_id)
            report.tracks[key] = tr
            report.track_order.append(key)


def _precheck_reason_bucket(reason: str) -> str:
    lowered = (reason or "").strip().lower()
    if not lowered:
        return "unknown"
    if "same or better" in lowered or "equal or better" in lowered:
        return "same_or_better_inventory"
    if "matched by isrc" in lowered:
        return "same_or_better_inventory"
    if "no inventory match" in lowered:
        return "no_inventory_match"
    head = lowered.split(";", 1)[0].strip()
    head = head.split(":", 1)[0].strip()
    if head:
        return head[:80]
    return "unknown"


def _compute_precheck_counts(report: RunReport) -> None:
    total = len(report.track_order)
    if total <= 0:
        return
    keep = 0
    skip = 0
    skip_buckets: dict[str, int] = {}
    keep_keys: list[tuple[str, str]] = []
    selection_attempted = 0
    selection_tidal = 0
    selection_beatport = 0
    selection_ambiguous = 0
    selection_unverified = 0
    selection_not_better = 0
    selection_unavailable = 0
    for key in report.track_order:
        tr = report.tracks.get(key)
        if not tr:
            continue
        if tr.precheck_decision == "keep":
            keep += 1
            keep_keys.append(key)
        elif tr.precheck_decision == "skip":
            skip += 1
            bucket = _precheck_reason_bucket(tr.precheck_reason)
            skip_buckets[bucket] = skip_buckets.get(bucket, 0) + 1
        if tr.source_selection_attempted:
            selection_attempted += 1
            if tr.source_selection_winner == "tidal":
                selection_tidal += 1
            elif tr.source_selection_winner == "beatport":
                selection_beatport += 1
            if tr.source_selection_reason == "tidal_ambiguous_verified_candidates":
                selection_ambiguous += 1
            if tr.source_selection_reason in ("tidal_unverified", "no_tidal_candidates"):
                selection_unverified += 1
            if tr.source_selection_reason == "tidal_not_better_quality":
                selection_not_better += 1
            if tr.source_selection_reason.startswith("tidal_match_unavailable:"):
                selection_unavailable += 1
    report.keep_track_keys = keep_keys
    report.precheck_total = total
    report.requested_total = total
    report.precheck_keep = keep
    report.precheck_skip = skip
    report.precheck_skip_reason_counts = skip_buckets
    if selection_attempted:
        report.source_selection_attempted = selection_attempted
        report.source_selection_tidal = selection_tidal
        report.source_selection_beatport = selection_beatport
        report.source_selection_ambiguous = selection_ambiguous
        report.source_selection_unverified = selection_unverified
        report.source_selection_not_better = selection_not_better
        report.source_selection_unavailable = selection_unavailable
    if report.selected_for_download is None:
        report.selected_for_download = keep


def _extract_tidal_track_id(url: str) -> str | None:
    m = _TIDAL_TRACK_ID_RE.search(url)
    return m.group(1) if m else None


def _parse_downloaded_line(line: str) -> tuple[str, str, str]:
    stripped = line.strip()
    prefix = stripped.split(" /", 1)[0].strip()
    rest = prefix[len("Downloaded ") :].strip()
    title = rest
    quality = ""
    if "  " in rest:
        title, tail = rest.split("  ", 1)
        title = title.strip()
        quality = tail.strip()
    dest = ""
    if " /" in stripped:
        dest = "/" + stripped.split(" /", 1)[1].strip()
    return title, quality, dest


def reconcile_outcomes(report: RunReport) -> None:
    for key, payload in list(report.pending_download_by_key.items()):
        tr = report.tracks.get(key)
        if not tr:
            continue
        tr.outcome = payload.get("outcome", "unknown")  # type: ignore[assignment]
        tr.outcome_reason = payload.get("reason", "")
        tr.quality = payload.get("quality", "") or tr.quality
        tr.dest = payload.get("dest", "") or tr.dest
        tr.inferred_from_log = True

    if not report.pending_download_by_title:
        return
    by_title: dict[str, list[TrackRow]] = {}
    for key in report.track_order:
        tr = report.tracks.get(key)
        if not tr:
            continue
        by_title.setdefault(_norm_text(tr.title), []).append(tr)
    for ev in report.pending_download_by_title:
        norm = ev.get("title_norm", "")
        candidates = [c for c in (by_title.get(norm) or []) if c.outcome == "unknown"]
        if len(candidates) != 1:
            continue
        tr = candidates[0]
        tr.outcome = ev.get("outcome", "unknown")  # type: ignore[assignment]
        tr.outcome_reason = ev.get("reason", "")
        tr.quality = ev.get("quality", "") or tr.quality
        tr.dest = ev.get("dest", "") or tr.dest
        tr.inferred_from_log = True


def apply_precheck_skips(report: RunReport) -> None:
    for tr in report.tracks.values():
        if tr.outcome != "unknown":
            continue
        if tr.precheck_decision == "skip":
            tr.outcome = "skipped"
            tr.outcome_reason = tr.precheck_reason or "skipped by precheck"
            if not tr.dest and tr.db_path:
                tr.dest = tr.db_path
            tr.inferred_from_log = False


def _write_outcomes_csv(*, artifacts: RunArtifacts, report: RunReport) -> Path:
    artifacts_root = get_artifacts_dir().expanduser().resolve()
    out_dir = artifacts_root / "intake" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"outcomes_{_utc_stamp()}.csv"
    fieldnames = [
        "domain",
        "source_link",
        "track_id",
        "track_index",
        "isrc",
        "artist",
        "title",
        "album",
        "confidence",
        "match_method",
        "precheck_decision",
        "precheck_reason",
        "db_path",
        "db_download_source",
        "existing_quality_rank",
        "candidate_quality_rank",
        "source_selection_attempted",
        "source_selection_winner",
        "source_selection_reason",
        "tidal_match_method",
        "tidal_track_id",
        "tidal_audio_quality",
        "tidal_audio_quality_rank",
        "duration_diff_ms",
        "outcome",
        "outcome_reason",
        "dest",
        "quality",
        "inferred_from_log",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        # PROVENANCE STUB: when ProvenanceTracker is wired in, call here:
        #   ProvenanceTracker.flush_to_csv(out_path)
        #   — this is where per-track provider API source + file hash gets persisted.
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for key in report.track_order:
            tr = report.tracks.get(key)
            if not tr:
                continue
            w.writerow(
                {
                    "domain": tr.domain,
                    "source_link": tr.source_link,
                    "track_id": tr.track_id,
                    "track_index": tr.index or "",
                    "isrc": tr.isrc,
                    "artist": tr.artist,
                    "title": tr.title,
                    "album": tr.album,
                    "confidence": tr.confidence,
                    "match_method": tr.match_method,
                    "precheck_decision": tr.precheck_decision,
                    "precheck_reason": tr.precheck_reason,
                    "db_path": tr.db_path,
                    "db_download_source": tr.db_download_source,
                    "existing_quality_rank": tr.existing_quality_rank if tr.existing_quality_rank is not None else "",
                    "candidate_quality_rank": tr.candidate_quality_rank if tr.candidate_quality_rank is not None else "",
                    "source_selection_attempted": "1" if tr.source_selection_attempted else "",
                    "source_selection_winner": tr.source_selection_winner,
                    "source_selection_reason": tr.source_selection_reason,
                    "tidal_match_method": tr.tidal_match_method,
                    "tidal_track_id": tr.tidal_track_id,
                    "tidal_audio_quality": tr.tidal_audio_quality,
                    "tidal_audio_quality_rank": tr.tidal_audio_quality_rank if tr.tidal_audio_quality_rank is not None else "",
                    "duration_diff_ms": tr.duration_diff_ms if tr.duration_diff_ms is not None else "",
                    "outcome": tr.outcome,
                    "outcome_reason": tr.outcome_reason,
                    "dest": tr.dest,
                    "quality": tr.quality,
                    "inferred_from_log": "1" if tr.inferred_from_log else "0",
                }
            )
    artifacts.outcomes_csv = out_path
    return out_path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_plan_summaries(report: RunReport, artifacts: RunArtifacts) -> None:
    if artifacts.plan_summary_json and artifacts.plan_summary_json.exists():
        payload = _read_json(artifacts.plan_summary_json)
        planned = payload.get("planned") or {}
        try:
            report.plan_promote_move = int(planned.get("promote_move")) if planned.get("promote_move") is not None else None
        except Exception:
            report.plan_promote_move = None
        try:
            report.plan_promote_skip = int(planned.get("promote_skip")) if planned.get("promote_skip") is not None else None
        except Exception:
            report.plan_promote_skip = None
        try:
            report.plan_stash_move = int(planned.get("stash_move")) if planned.get("stash_move") is not None else None
        except Exception:
            report.plan_stash_move = None
        try:
            report.plan_quarantine_move = int(planned.get("quarantine_move")) if planned.get("quarantine_move") is not None else None
        except Exception:
            report.plan_quarantine_move = None

    if artifacts.fix_plan_summary_json and artifacts.fix_plan_summary_json.exists():
        payload = _read_json(artifacts.fix_plan_summary_json)
        try:
            report.fix_planned_move = int(payload.get("selected_rows")) if payload.get("selected_rows") is not None else None
        except Exception:
            report.fix_planned_move = None

    if artifacts.discard_plan_summary_json and artifacts.discard_plan_summary_json.exists():
        payload = _read_json(artifacts.discard_plan_summary_json)
        try:
            report.discard_planned_move = int(payload.get("selected_rows")) if payload.get("selected_rows") is not None else None
        except Exception:
            report.discard_planned_move = None


class GetIntakeLogParser:
    def __init__(self) -> None:
        self.report = RunReport()
        self._current_stage: Stage | None = None
        self._run_total_steps: int | None = None
        self._in_config = False
        self._in_run_summary = False
        self._current_download_track_key: tuple[str, str] | None = None
        self._download_seen_titles: set[str] = set()
        self._subctx: str | None = None

    def feed_line(self, raw: str) -> None:
        line = _strip_ansi(raw.rstrip("\n"))
        stripped = line.strip()
        if not stripped:
            return

        if stripped.startswith("WARNING:") or stripped.startswith("DEPRECATION NOTICE:"):
            notice = stripped
            if notice not in self.report.notices:
                self.report.notices.append(notice)
            return

        m = _STEP_RE.match(stripped)
        if m:
            idx = int(m.group(1))
            total = int(m.group(2))
            label = m.group(3).strip()
            if not _URL_RE.match(label):
                if self._run_total_steps is None:
                    self._run_total_steps = total
                if total == self._run_total_steps:
                    if self._current_stage and self._current_stage.status == "running":
                        self._current_stage.status = "ok"
                    st = Stage(idx=idx, total=total, name=label, status="running")
                    self.report.stages.append(st)
                    self._current_stage = st
                    self._subctx = None
                    return
                if self._current_stage:
                    self._current_stage.details.append(stripped)
                return

        if stripped == "Intake Config":
            self._in_config = True
            return
        if self._in_config:
            kv = _CONFIG_KV_RE.match(line)
            if kv:
                key = kv.group(1).strip().lower()
                value = kv.group(2).strip()
                if key == "source":
                    self.report.source = value
                elif key == "url":
                    self.report.url = value
                elif key == "batch root":
                    self.report.batch_root = value
                elif key == "db":
                    self.report.db_path = value
                elif key == "library root":
                    self.report.library_root = value
                else:
                    self.report.toggles[key] = value
                return
            if stripped.startswith("[") and "]" in stripped:
                self._in_config = False

        if stripped.lower() == "run summary":
            self._in_run_summary = True
            return
        if self._in_run_summary:
            kv = _CONFIG_KV_RE.match(line)
            if kv:
                k = kv.group(1).strip().lower()
                v = kv.group(2).strip()
                if k == "precheck":
                    m2 = re.search(r"keep=(\d+)\s+skip=(\d+)\s+total=(\d+)", v)
                    if m2:
                        self.report.precheck_keep = int(m2.group(1))
                        self.report.precheck_skip = int(m2.group(2))
                        self.report.precheck_total = int(m2.group(3))
                elif k == "promoted":
                    try:
                        self.report.run_promoted = int(v)
                    except Exception:
                        self.report.run_promoted = None
                elif k == "stashed":
                    try:
                        self.report.run_stashed = int(v)
                    except Exception:
                        self.report.run_stashed = None
                elif k == "quarantine":
                    try:
                        self.report.run_quarantined = int(v)
                    except Exception:
                        self.report.run_quarantined = None
                elif k == "fix skips":
                    try:
                        self.report.run_fix_skips = int(v)
                    except Exception:
                        self.report.run_fix_skips = None
                elif k == "discard":
                    try:
                        self.report.run_discarded = int(v)
                    except Exception:
                        self.report.run_discarded = None
                elif k == "dj exports":
                    try:
                        self.report.run_dj_exports = int(v)
                    except Exception:
                        self.report.run_dj_exports = None
                elif k == "dj m3u" and v:
                    if v not in self.report.dj_m3u_paths:
                        self.report.dj_m3u_paths.append(v)
                elif k == "roon m3u" and v:
                    if v not in self.report.m3u_paths:
                        self.report.m3u_paths.append(v)
                    if self.report.m3u_count is None:
                        self.report.m3u_count = 1
                return
            self._in_run_summary = False

        if stripped.startswith("→") or stripped.startswith("$ "):
            if self._current_stage:
                self._current_stage.details.append(stripped)
            if "hoard_tags.py" in stripped:
                self._subctx = "hoard_tags"
            elif "normalize_genres.py" in stripped:
                self._subctx = "normalize_genres"
            elif "tag_normalized_genres.py" in stripped:
                self._subctx = "tag_normalized_genres"
            else:
                self._subctx = None
            return

        if stripped.startswith("Precheck summary:"):
            m2 = re.search(r"keep=(\d+)\s+skip=(\d+)\s+total=(\d+)", stripped)
            if m2:
                self.report.precheck_keep = int(m2.group(1))
                self.report.precheck_skip = int(m2.group(2))
                self.report.precheck_total = int(m2.group(3))
            return
        if self._current_stage and "pre-download" in self._current_stage.name.lower():
            kv = _CONFIG_KV_RE.match(line)
            if kv:
                k = kv.group(1).strip().lower()
                v = kv.group(2).strip()
                if k == "total":
                    self.report.precheck_total = int(v)
                elif k == "keep":
                    self.report.precheck_keep = int(v)
                elif k == "skip":
                    self.report.precheck_skip = int(v)
            return

        if stripped.startswith("Selected for download:"):
            m2 = re.search(r"Selected for download:\s*(\d+)\s+track", stripped)
            if m2:
                self.report.selected_for_download = int(m2.group(1))
            return

        if "Generated " in stripped and " M3U file" in stripped:
            m2 = re.search(r"Generated\s+(\d+)\s+M3U file", stripped)
            if m2:
                self.report.m3u_count = int(m2.group(1))
            return
        if stripped.startswith("/") and stripped.endswith(".m3u"):
            if stripped not in self.report.m3u_paths:
                self.report.m3u_paths.append(stripped)
            return

        if stripped.startswith("EXECUTE:"):
            m2 = re.search(r"planned=(\d+)\s+moved=(\d+)\s+skipped_missing=(\d+)\s+skipped_exists=(\d+)\s+failed=(\d+)", stripped)
            if m2:
                planned = int(m2.group(1))
                moved = int(m2.group(2))
                skipped_missing = int(m2.group(3))
                skipped_exists = int(m2.group(4))
                failed = int(m2.group(5))
                self.report.apply_planned = (self.report.apply_planned or 0) + planned
                self.report.apply_moved = (self.report.apply_moved or 0) + moved
                self.report.apply_skipped_missing = (self.report.apply_skipped_missing or 0) + skipped_missing
                self.report.apply_skipped_exists = (self.report.apply_skipped_exists or 0) + skipped_exists
                self.report.apply_failed = (self.report.apply_failed or 0) + failed
            return

        if self._current_stage and "trust scan" in self._current_stage.name.lower():
            m_discovered = re.search(r"\bDiscovered:\s*(\d+)", stripped)
            if m_discovered:
                self.report.scan_discovered = int(m_discovered.group(1))
            m_succeeded = re.search(r"\bSucceeded:\s*(\d+)", stripped)
            if m_succeeded:
                self.report.scan_succeeded = int(m_succeeded.group(1))
            m_failed = re.search(r"\bFailed:\s*(\d+)", stripped)
            if m_failed:
                self.report.scan_failed = int(m_failed.group(1))
            m_inputskipped = re.search(r"\bInputSkipped:\s*(\d+)", stripped)
            if m_inputskipped:
                self.report.scan_failure_breakdown["InputSkipped"] = int(m_inputskipped.group(1))
            return

        m3 = re.match(r"^\[(\d+)/(\d+)\]\s+(https?://\S+)", stripped)
        if m3:
            url = m3.group(3)
            tid = _extract_tidal_track_id(url)
            if tid:
                self._current_download_track_key = ("tidal", tid)
            return

        if stripped.startswith("Downloaded "):
            title, quality, dest = _parse_downloaded_line(stripped)
            self.report.download_downloaded += 1
            self._buffer_download_outcome(title=title, outcome="downloaded", reason="downloaded (inferred from log)", quality=quality, dest=dest)
            return
        if stripped.startswith("Exists "):
            title = stripped[len("Exists ") :].split(" /", 1)[0].strip()
            self.report.download_present += 1
            self._buffer_download_outcome(title=title, outcome="present", reason="already present (inferred from log)")
            return
        if stripped.startswith("Error:"):
            self.report.download_failed += 1
            self._buffer_download_outcome(title="download error", outcome="failed", reason=stripped[len("Error:") :].strip())
            return
        m_bpdl = _BPDL_OK_RE.match(stripped)
        if m_bpdl:
            title = (m_bpdl.group(1) or "").strip()
            quality = (m_bpdl.group(2) or "").strip()
            self.report.download_downloaded += 1
            self._buffer_download_outcome(title=title, outcome="downloaded", reason="downloaded (inferred from log)", quality=quality)
            return

        if stripped.startswith("Tagged:"):
            m2 = re.search(r"Tagged:\s*(\d+)", stripped)
            if m2:
                value = int(m2.group(1))
                self.report.tagged_count = value
                if self._subctx == "tag_normalized_genres":
                    self.report.tag_normalized_genres_tagged = value
            return
        if stripped.startswith("OK: scanned_files=") and self._subctx == "hoard_tags":
            m2 = re.search(r"OK:\s+scanned_files=(\d+)", stripped)
            if m2:
                self.report.hoard_scanned_files = int(m2.group(1))
            return
        if stripped.startswith("Scanned:") and self._subctx == "normalize_genres":
            m2 = re.search(r"Scanned:\s*(\d+)", stripped)
            if m2:
                self.report.normalize_genres_scanned = int(m2.group(1))
            return
        if stripped.startswith("Updated DB rows:") and self._subctx == "normalize_genres":
            m2 = re.search(r"Updated DB rows:\s*(\d+)", stripped)
            if m2:
                self.report.normalize_genres_updated = int(m2.group(1))
            return
        if stripped.startswith("Scanned:") and self._subctx == "tag_normalized_genres":
            m2 = re.search(r"Scanned:\s*(\d+)", stripped)
            if m2:
                self.report.tag_normalized_genres_scanned = int(m2.group(1))
            return
        if stripped.startswith("Resolved ") and " promoted identity ids" in stripped:
            m2 = re.search(r"Resolved\s+(\d+)\s+promoted identity ids", stripped)
            if m2:
                self.report.dj_identity_resolved = int(m2.group(1))
            return

    def finalize(self) -> RunReport:
        if self._current_stage and self._current_stage.status == "running":
            self._current_stage.status = "ok"
        return self.report

    def _buffer_download_outcome(self, *, title: str, outcome: TrackOutcome, reason: str, quality: str = "", dest: str = "") -> None:
        # PROVENANCE STUB: when ProvenanceTracker is wired in, record here:
        #   ProvenanceTracker.record_download(track_key=self._current_download_track_key,
        #       provider="tidal"|"beatport", dest=dest, quality=quality, ts=utcnow())
        if self._current_download_track_key:
            self.report.pending_download_by_key[self._current_download_track_key] = {"title": title, "outcome": outcome, "reason": reason, "quality": quality, "dest": dest}
            return
        nt = _norm_text(title)
        if not nt or nt in self._download_seen_titles:
            return
        self._download_seen_titles.add(nt)
        self.report.pending_download_by_title.append({"title": title, "title_norm": nt, "outcome": outcome, "reason": reason, "quality": quality, "dest": dest})


def _roots_map(report: RunReport) -> dict[str, str]:
    roots: dict[str, str] = {}
    if report.library_root:
        roots["LIB"] = report.library_root
    if report.batch_root:
        roots["BATCH"] = report.batch_root
    for key, label in [("fix root", "FIX"), ("discard", "DISCARD"), ("quarantine", "QUAR")]:
        if key in report.toggles:
            roots[label] = report.toggles[key]
    return roots


def _toggle_val(report: RunReport, key: str) -> str | None:
    value = (report.toggles.get(key) or "").strip()
    return value or None


def _format_toggles(report: RunReport, *, verbose: bool) -> str:
    parts: list[str] = []
    for key, label in [
        ("execute", "exec"),
        ("precheck", "precheck"),
        ("resume", "resume"),
        ("force", "force"),
        ("tagging", "tag"),
        ("roon m3u", "m3u"),
        ("dj", "dj"),
        ("m3u only", "m3u-only"),
    ]:
        val = _toggle_val(report, key)
        if val is not None:
            parts.append(f"{label}={val}")
    if verbose:
        parts.append("verbose=1")
    return " ".join(parts) if parts else ""


def _unknown_keep_count(report: RunReport) -> int:
    count = 0
    for key in report.keep_track_keys:
        tr = report.tracks.get(key)
        if not tr:
            continue
        if tr.outcome == "unknown":
            count += 1
    return count


def _render_clean(
    report: RunReport,
    artifacts: RunArtifacts,
    *,
    verbose: bool,
    out: Any = None,
) -> None:
    """Clean flat-text output formatter. Target: < 50 lines for a typical album intake.

    Format:
      <source> — <N> tracks
      Precheck: <N> available[, <N> skipped (<reason>)]
      Download: <N> downloaded (<N> already present)
      Scan: <N> succeeded[, <N> failed (<type>)]
      Plan: promote <N>[, stash <N>, fix <N>, quarantine <N>]

      ✓ PROMOTED (<N> tracks):
        /full/path/to/track.flac
        ...

      ⚠ FIX QUEUE (<N> tracks):
        /path → reason: <issue>
        ...

      ✗ FAILURES (<N> tracks):
        Artist - Title → reason

      M3U: /path
      DJ: <N> resolved | why not: <reason>

      Log: /path
      Outcomes: /path
      [ATTENTION: <issue>]
    """
    import sys as _sys
    w = (out or _sys.stdout).write
    roots = _roots_map(report)

    # ── Lead line ─────────────────────────────────────────────────────────────
    url = report.url or ""
    total = report.precheck_total or report.requested_total or "?"
    tidal_m = re.search(r"tidal\.com/(?:browse/)?(\w+)/(\d+)", url, re.IGNORECASE)
    if tidal_m:
        lead_id = f"Tidal {tidal_m.group(1)} {tidal_m.group(2)}"
    else:
        lead_id = report.source or url or "?"
    w(f"{lead_id} — {total} tracks\n")

    # ── Precheck ──────────────────────────────────────────────────────────────
    if report.precheck_total is not None:
        keep = report.precheck_keep or 0
        skip = report.precheck_skip or 0
        skip_detail = ""
        if skip and report.precheck_skip_reason_counts:
            top = sorted(report.precheck_skip_reason_counts.items(), key=lambda kv: -kv[1])[:3]
            skip_detail = " (" + ", ".join(f"{k}={v}" for k, v in top) + ")"
        skip_part = f", {skip} skipped{skip_detail}" if skip else ""
        w(f"Precheck: {keep} tracks available{skip_part}\n")

    # ── Download ──────────────────────────────────────────────────────────────
    present = report.download_present
    failed_dl = report.download_failed
    present_part = f" ({present} already present)" if present else ""
    failed_part = f", {failed_dl} failed" if failed_dl else ""
    w(f"Download: {report.download_downloaded} tracks downloaded{present_part}{failed_part}\n")

    # ── Scan ──────────────────────────────────────────────────────────────────
    if report.scan_succeeded is not None or report.scan_failed is not None:
        scan_ok = report.scan_succeeded or 0
        scan_fail = report.scan_failed or 0
        breakdown = ""
        if scan_fail and report.scan_failure_breakdown:
            breakdown = " (" + ", ".join(report.scan_failure_breakdown.keys()) + ")"
        fail_part = f", {scan_fail} failed{breakdown}" if scan_fail else ""
        w(f"Scan: {scan_ok} succeeded{fail_part}\n")

    # ── Plan summary ──────────────────────────────────────────────────────────
    plan_parts = []
    if report.plan_promote_move is not None:
        plan_parts.append(f"promote {report.plan_promote_move}")
    if report.plan_stash_move:
        plan_parts.append(f"stash {report.plan_stash_move}")
    if report.fix_planned_move:
        plan_parts.append(f"fix {report.fix_planned_move}")
    if report.plan_quarantine_move:
        plan_parts.append(f"quarantine {report.plan_quarantine_move}")
    if report.discard_planned_move:
        plan_parts.append(f"discard {report.discard_planned_move}")
    if plan_parts:
        w(f"Plan: {', '.join(plan_parts)}\n")

    # ── Promoted paths ────────────────────────────────────────────────────────
    promoted_paths: list[str] = []
    if artifacts.promoted_txt and artifacts.promoted_txt.exists():
        try:
            promoted_paths = [
                ln.strip()
                for ln in artifacts.promoted_txt.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            ]
        except Exception:
            pass
    if not promoted_paths:
        for key in report.track_order:
            tr = report.tracks.get(key)
            if tr and tr.outcome in {"downloaded", "present"} and tr.dest:
                promoted_paths.append(tr.dest)
    if promoted_paths:
        w(f"\n✓ PROMOTED ({len(promoted_paths)} tracks):\n")
        for p in promoted_paths:
            w(f"  {p}\n")

    # ── Fix queue ─────────────────────────────────────────────────────────────
    fix_rows: list[tuple[str, str]] = []
    if artifacts.fix_plan_summary_json and artifacts.fix_plan_summary_json.exists():
        fix_dir = artifacts.fix_plan_summary_json.parent
        fix_csvs = sorted(
            fix_dir.glob("plan_move_skipped_to_fix_*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if fix_csvs:
            try:
                import csv as _csv
                with fix_csvs[0].open("r", encoding="utf-8", newline="") as fh:
                    for row in _csv.DictReader(fh):
                        src_path = (row.get("src") or row.get("source") or row.get("path") or "").strip()
                        reason = (row.get("reason") or row.get("skip_reason") or "").strip()
                        if src_path:
                            fix_rows.append((src_path, reason))
            except Exception:
                pass
    # fall back to per-track data
    if not fix_rows:
        for key in report.track_order:
            tr = report.tracks.get(key)
            if not tr:
                continue
            if tr.outcome == "failed" or (tr.outcome_reason and "fix" in tr.outcome_reason.lower()):
                dest = tr.dest or tr.db_path or ""
                reason = tr.outcome_reason or tr.precheck_reason or "unknown"
                fix_rows.append((dest, reason))
    if fix_rows:
        w(f"\n⚠ FIX QUEUE ({len(fix_rows)} tracks):\n")
        for path, reason in fix_rows:
            w(f"  {path} → reason: {reason}\n")

    # ── Download failures ─────────────────────────────────────────────────────
    fix_paths = {p for p, _ in fix_rows}
    dl_failures = [
        tr
        for key in report.track_order
        if (tr := report.tracks.get(key))
        and tr.outcome == "failed"
        and (tr.dest or tr.db_path or "") not in fix_paths
    ]
    if dl_failures:
        w(f"\n✗ FAILURES ({len(dl_failures)} tracks):\n")
        for tr in dl_failures:
            detail = tr.outcome_reason or tr.precheck_reason or "unknown"
            ident = f"{tr.artist} - {tr.title}" if tr.artist and tr.title else tr.title or tr.track_id
            w(f"  {ident} → {detail}\n")

    # ── M3U ──────────────────────────────────────────────────────────────────
    if report.m3u_paths:
        w(f"\nM3U: {report.m3u_paths[0]}\n")

    # ── DJ ───────────────────────────────────────────────────────────────────
    dj_requested = _toggle_val(report, "dj") == "1"
    if dj_requested:
        resolved = report.dj_identity_resolved or 0
        if resolved:
            w(f"\nDJ: {resolved} resolved\n")
            for p in report.dj_m3u_paths:
                w(f"  playlist: {p}\n")
            if artifacts.dj_manifest_csv:
                w(f"  manifest: {artifacts.dj_manifest_csv}\n")
        else:
            # Diagnose why DJ resolved 0 rather than silently failing
            all_present = (report.download_present or 0) > 0 and (report.download_downloaded or 0) == 0
            if all_present:
                w("\nDJ: 0 resolved (all files already in library — run dj_backfill for existing tracks)\n")
            elif (report.plan_promote_move or 0) == 0 and (report.apply_moved or 0) == 0:
                w("\nDJ: 0 resolved (no tracks promoted this run)\n")
            else:
                w("\nDJ: 0 resolved (no matching DJ pool identities — check dj_identity_ids artifact)\n")
            if artifacts.dj_identity_ids_txt:
                w(f"  identity ids: {artifacts.dj_identity_ids_txt}\n")

    # ── Key artifacts ─────────────────────────────────────────────────────────
    w(f"\nLog: {artifacts.raw_log}\n")
    if artifacts.outcomes_csv:
        w(f"Outcomes: {artifacts.outcomes_csv}\n")
    if artifacts.precheck_decisions_csv:
        w(f"Precheck CSV: {artifacts.precheck_decisions_csv}\n")

    # ── Attention items (anomalies only) ──────────────────────────────────────
    attention: list[str] = []
    unknown_keep = _unknown_keep_count(report)
    if unknown_keep:
        attention.append(f"unaccounted keep tracks: {unknown_keep} (check outcomes/raw log)")
    if report.download_failed:
        attention.append(f"download failures: {report.download_failed}")
    if report.apply_skipped_missing:
        attention.append(f"moves skipped_missing: {report.apply_skipped_missing}")
    if report.apply_failed:
        attention.append(f"moves failed: {report.apply_failed}")
    if report.tagged_count == 0 and _toggle_val(report, "tagging") == "1":
        attention.append("tagging: applied 0 files")
    for n in report.notices[:3]:
        attention.append(f"notice: {n}")
    if attention:
        w("\n")
        for item in attention:
            w(f"ATTENTION: {item}\n")


def _render_plain(report: RunReport, artifacts: RunArtifacts, *, out: Any, success_limit: int) -> None:
    w = out.write
    roots = _roots_map(report)
    w("tools/get Run\n")
    w(f"  source:      {report.source or '?'}\n")
    w(f"  url:         {report.url or '?'}\n")
    w(f"  batch_root:  {report.batch_root or '?'}\n")
    w(f"  db:          {report.db_path or '?'}\n")
    w(f"  library:     {report.library_root or '?'}\n")
    toggles = _format_toggles(report, verbose=False)
    if toggles:
        w(f"  toggles:     {toggles}\n")
    if report.notices:
        w(f"  notices:     {len(report.notices)}\n")
    w(f"  raw_log:     {artifacts.raw_log}\n")

    w("\nStages:\n")
    for st in report.stages:
        w(f"  [{st.idx}/{st.total}] {st.name}  status={st.status}\n")

    unknown_keep = _unknown_keep_count(report)
    w("\nFinal Summary:\n")
    if report.precheck_total is not None:
        line = f"  precheck:    keep={report.precheck_keep} skip={report.precheck_skip} total={report.precheck_total}"
        if report.source_selection_attempted:
            line += (
                f" source_select=attempted:{report.source_selection_attempted}"
                f"/tidal:{report.source_selection_tidal or 0}"
                f"/beatport:{report.source_selection_beatport or 0}"
            )
        w(line + "\n")
    w(f"  download:    selected={report.selected_for_download} ok={report.download_downloaded} present={report.download_present} failed={report.download_failed}")
    if unknown_keep:
        w(f" unaccounted={unknown_keep}")
    w("\n")
    if report.scan_discovered is not None or report.scan_failed is not None:
        w(f"  scan:        discovered={report.scan_discovered} succeeded={report.scan_succeeded} failed={report.scan_failed}\n")
    if report.plan_promote_move is not None:
        w(f"  plan:        promote={report.plan_promote_move} stash={report.plan_stash_move} quar={report.plan_quarantine_move} fix={report.fix_planned_move} discard={report.discard_planned_move}\n")
    if report.apply_moved is not None:
        moves_bits = [f"moved={report.apply_moved}"]
        if report.apply_skipped_missing is not None:
            moves_bits.append(f"skipped_missing={report.apply_skipped_missing}")
        if report.apply_skipped_exists is not None:
            moves_bits.append(f"skipped_exists={report.apply_skipped_exists}")
        moves_bits.append(f"failed={report.apply_failed if report.apply_failed is not None else '?'}")
        w(f"  moves:       {' '.join(moves_bits)}\n")
    if (
        report.run_promoted is not None
        or report.run_stashed is not None
        or report.run_quarantined is not None
        or report.run_fix_skips is not None
        or report.run_discarded is not None
    ):
        w(
            "  disposition:"
            f" promoted={report.run_promoted}"
            f" stashed={report.run_stashed}"
            f" quar={report.run_quarantined}"
            f" fix={report.run_fix_skips}"
            f" discard={report.run_discarded}\n"
        )
    if report.m3u_paths:
        w(f"  m3u:         {report.m3u_paths[0]}\n")
    if report.dj_identity_resolved is not None:
        w(f"  dj:          resolved_ids={report.dj_identity_resolved}\n")
    if report.run_dj_exports is not None:
        w(f"  dj_exports:  {report.run_dj_exports}\n")

    w("\nDownload Accountability:\n")
    w(f"  requested:   {report.requested_total}\n")
    w(f"  selected:    {report.selected_for_download}\n")
    w(f"  downloaded:  {report.download_downloaded}\n")
    w(f"  present:     {report.download_present}\n")
    w(f"  failed:      {report.download_failed}\n")
    rows = [report.tracks[k] for k in report.track_order if k in report.tracks]
    failures_or_skips = [r for r in rows if r.outcome in {"failed", "skipped"}]
    unknowns = [r for r in rows if r.outcome == "unknown"]
    successes = [r for r in rows if r.outcome in {"downloaded", "present"}]
    render_rows = failures_or_skips + unknowns + successes[:success_limit]
    w("  per-track:\n")
    for r in render_rows:
        if r.source_selection_winner and r.source_selection_winner != r.domain:
            src = f"{r.domain}->{r.source_selection_winner}"
        else:
            src = r.domain
        reason = r.outcome_reason or r.precheck_reason
        if r.outcome in {"downloaded", "present"} and r.precheck_reason:
            if reason.startswith("downloaded") or reason.startswith("already present"):
                reason = r.precheck_reason
        quality = r.quality
        if not quality and r.source_selection_winner == "tidal" and r.tidal_audio_quality:
            quality = r.tidal_audio_quality
        dest = _abbrev_path(r.dest, roots=roots)
        evidence = "log(inferred-from-log)" if r.inferred_from_log else "csv"
        w(
            f"    - [{src}] {r.artist} - {r.title} | {r.outcome} | {reason} | dest={dest} | quality={quality} | evidence={evidence}\n"
        )
    if len(successes) > success_limit:
        w(f"    (success rows truncated: {success_limit}/{len(successes)})\n")
    w("\nKey Artifacts:\n")
    w(f"  raw_log:             {artifacts.raw_log}\n")
    if artifacts.precheck_decisions_csv:
        w(f"  precheck_decisions:  {artifacts.precheck_decisions_csv}\n")
    if artifacts.precheck_tracks_csv:
        w(f"  precheck_tracks:     {artifacts.precheck_tracks_csv}\n")
    if artifacts.keep_urls_txt:
        w(f"  keep_urls:           {artifacts.keep_urls_txt}\n")
    if artifacts.keep_tidal_urls_txt:
        w(f"  keep_tidal_urls:     {artifacts.keep_tidal_urls_txt}\n")
    if artifacts.keep_bpdl_urls_txt:
        w(f"  keep_bpdl_urls:      {artifacts.keep_bpdl_urls_txt}\n")
    if artifacts.precheck_summary_csv:
        w(f"  precheck_summary:    {artifacts.precheck_summary_csv}\n")
    if artifacts.precheck_report_md:
        w(f"  precheck_report:     {artifacts.precheck_report_md}\n")
    if artifacts.outcomes_csv:
        w(f"  outcomes:            {artifacts.outcomes_csv}\n")
    if artifacts.plan_summary_json:
        w(f"  plan_summary:        {artifacts.plan_summary_json}\n")
    if artifacts.plan_promote_csv:
        w(f"  plan_promote:        {artifacts.plan_promote_csv}\n")
    if artifacts.plan_stash_csv:
        w(f"  plan_stash:          {artifacts.plan_stash_csv}\n")
    if artifacts.plan_quarantine_csv:
        w(f"  plan_quarantine:     {artifacts.plan_quarantine_csv}\n")
    if artifacts.moves_jsonl:
        w(f"  moves_log:           {artifacts.moves_jsonl}\n")
    if artifacts.promoted_txt:
        w(f"  promoted_list:       {artifacts.promoted_txt}\n")
    if report.m3u_paths:
        w(f"  m3u:                 {report.m3u_paths[0]}\n")
    if artifacts.fix_plan_summary_json:
        w(f"  plan_fix_summary:    {artifacts.fix_plan_summary_json}\n")
    if artifacts.discard_plan_summary_json:
        w(f"  plan_discard_summary:{' '}{artifacts.discard_plan_summary_json}\n")
    if artifacts.genre_normalization_report:
        w(f"  genre_norm_report:   {artifacts.genre_normalization_report}\n")
    if artifacts.genre_normalization_rows_csv:
        w(f"  genre_norm_rows:     {artifacts.genre_normalization_rows_csv}\n")
    if artifacts.tag_hoard_summary_json:
        w(f"  tag_hoard:           {artifacts.tag_hoard_summary_json}\n")
    if artifacts.tag_hoard_values_csv:
        w(f"  tag_hoard_values:    {artifacts.tag_hoard_values_csv}\n")
    if artifacts.dj_identity_ids_txt:
        w(f"  dj_identity_ids:     {artifacts.dj_identity_ids_txt}\n")
    if artifacts.dj_manifest_csv:
        w(f"  dj_manifest:         {artifacts.dj_manifest_csv}\n")
    if artifacts.dj_receipts_jsonl:
        w(f"  dj_receipts:         {artifacts.dj_receipts_jsonl}\n")
    if artifacts.dj_playlist_inputs_txt:
        w(f"  dj_playlist_inputs:  {artifacts.dj_playlist_inputs_txt}\n")
    if artifacts.roon_m3u_inputs_txt:
        w(f"  roon_m3u_inputs:     {artifacts.roon_m3u_inputs_txt}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="tools/get-intake console wrapper. Outputs clean flat text by default.")
    ap.add_argument("--verbose", action="store_true", help="Show more details in output.")
    ap.add_argument("--plain", action="store_true", help="Use legacy plain/pipe-friendly output (no symbols).")
    ap.add_argument("--success-limit", type=int, default=40, help="Max success rows in --plain mode.")
    ap.add_argument("--", dest="dashdash", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to run (pass after --).")
    ns = ap.parse_args(argv)

    cmd = ns.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("ERROR: missing backend command (use: ... get_intake_console -- <tools/get-intake ...>)", file=sys.stderr)
        return 2

    started = time.time()
    artifacts_root = get_artifacts_dir().expanduser().resolve()
    raw_log_dir = artifacts_root / "intake" / "logs"
    raw_log_dir.mkdir(parents=True, exist_ok=True)
    raw_log = raw_log_dir / f"get_intake_{_utc_stamp()}.log"

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    parser = GetIntakeLogParser()
    with raw_log.open("w", encoding="utf-8") as log_fh:
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path.cwd()),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            log_fh.write(line)
            parser.feed_line(line)
        try:
            proc.stdout.close()
        except Exception:
            pass
        rc = proc.wait()

    report = parser.finalize()
    artifacts = _discover_artifacts(started=started, raw_log=raw_log)
    if artifacts.precheck_decisions_csv and artifacts.precheck_decisions_csv.exists():
        _load_precheck_decisions(report, artifacts.precheck_decisions_csv)
        reconcile_outcomes(report)
        apply_precheck_skips(report)
        _compute_precheck_counts(report)

    _load_plan_summaries(report, artifacts)
    _write_outcomes_csv(artifacts=artifacts, report=report)

    # _render_clean is the canonical output path. --plain uses the legacy formatter.
    if getattr(ns, "plain", False):
        _render_plain(report, artifacts, out=sys.stdout, success_limit=int(ns.success_limit))
    else:
        if _is_tty() and not os.environ.get("NO_COLOR"):
            Console().print(Rule(style="dim"))
        _render_clean(report, artifacts, verbose=bool(ns.verbose))

    if rc != 0:
        tail = raw_log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        sys.stderr.write(f"\nFAILED: backend rc={rc}\nraw log: {raw_log}\n")
        sys.stderr.write("\n".join(tail) + "\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
