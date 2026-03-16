"""Intake orchestrator for `tagslut intake url` command.

Orchestrates:
1. Precheck (binding by default for non-dry-run; owned by tools/get-intake)
2. Download + local tag prep + promote (via tools/get-intake, called via tools/get)
3. MP3 stage (full-tag mp3_asset generation; scoped to promoted cohort with resume fallback)
4. DJ stage  (DJ-copy mp3_asset generation; extends MP3 stage)

Emits structured JSON artifact on every invocation.
"""
from __future__ import annotations

import os
import json
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import csv
import sqlite3

from tagslut.utils.env_paths import get_artifacts_dir


@dataclass
class IntakeStageResult:
    """Result of a single intake stage."""

    stage: str  # "precheck" | "download" | "promote" | "mp3" | "dj"
    status: str  # "ok" | "skipped" | "blocked" | "failed"
    detail: str | None = None
    artifact_path: Path | None = None


@dataclass
class IntakeResult:
    """Aggregate intake orchestration result."""

    url: str
    stages: list[IntakeStageResult]
    disposition: str  # "completed" | "blocked" | "failed"
    precheck_summary: dict[str, int]  # {"total": N, "new": N, "upgrade": N, "blocked": N}
    precheck_csv: Path | None  # Path to precheck_decisions_<ts>.csv
    artifact_path: Path | None

    def summary(self) -> str:
        """Human-readable summary of intake result."""
        parts = [
            f"url={self.url}",
            f"disposition={self.disposition}",
        ]
        if self.precheck_summary:
            parts.append(
                f"precheck: {self.precheck_summary.get('new', 0)} new, "
                f"{self.precheck_summary.get('upgrade', 0)} upgrade, "
                f"{self.precheck_summary.get('blocked', 0)} blocked"
            )
        return " | ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "url": self.url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "disposition": self.disposition,
            "precheck_summary": self.precheck_summary,
            "precheck_csv": str(self.precheck_csv) if self.precheck_csv else None,
            "stages": [
                {
                    "stage": stage.stage,
                    "status": stage.status,
                    "detail": stage.detail,
                    "artifact_path": str(stage.artifact_path) if stage.artifact_path else None,
                }
                for stage in self.stages
            ],
        }


_GET_INTAKE_STEP_RE = re.compile(r"^\[(\d+)/(\d+)\]\s+(.*)$")
_GET_INTAKE_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _short_list(items: list[str], *, limit: int) -> str:
    if not items:
        return ""
    if len(items) <= limit:
        return ", ".join(items)
    head = ", ".join(items[:limit])
    return f"{head} (+{len(items) - limit} more)"


def _read_text_lines(path: Path) -> list[str]:
    try:
        return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except FileNotFoundError:
        return []
    except Exception:
        return []


class _GetIntakeHumanSummarizer:
    """Parse tools/get-intake output and emit path-free, operator-friendly summaries."""

    def __init__(
        self,
        *,
        verbose: bool,
        run_started: float,
        emit: Callable[[str], None],
    ) -> None:
        self.verbose = verbose
        self.run_started = run_started
        self._emit = emit

        self._have_printed_header = False
        self._step_idx: int | None = None
        self._step_total: int | None = None
        self._step_label: str | None = None

        # Precheck
        self._precheck_keep: int | None = None
        self._precheck_skip: int | None = None
        self._precheck_total: int | None = None

        # Download
        self._selected_for_download: int | None = None
        self._downloaded_titles: list[str] = []
        self._downloaded_qualities: list[str] = []
        self._exists_titles: list[str] = []
        self._download_errors: list[str] = []

        # Index check
        self._index_total: int | None = None
        self._index_duplicates: int | None = None
        self._index_errors: int | None = None

        # Trust scan
        self._scan_discovered: int | None = None
        self._scan_succeeded: int | None = None
        self._scan_failed: int | None = None
        self._scan_failure_inputs_skipped: int | None = None

        # Tag hoard / tag prep
        self._hoard_scanned_files: int | None = None
        self._normalize_scanned: int | None = None
        self._normalize_updated: int | None = None
        self._genres_tagged: int | None = None
        self._tag_keys_path: Path | None = None
        self._tag_keys: list[str] = []

        # Fingerprint audit
        self._fpcalc_ok: int | None = None
        self._fpcalc_to_compute: int | None = None
        self._fp_dupe_groups: int | None = None
        self._fp_files_in_groups: int | None = None

        # Plan/apply
        self._planned_promote: int | None = None
        self._planned_stash: int | None = None
        self._planned_quarantine: int | None = None
        self._planned_discard: int | None = None
        self._moved_promote: int | None = None
        self._moved_stash: int | None = None
        self._moved_failed: int | None = None

        # M3U / background
        self._named_playlist: str | None = None
        self._background_pid: int | None = None

        # Final run summary (counts only)
        self._run_summary_promoted: int | None = None
        self._run_summary_stashed: int | None = None
        self._run_summary_quarantined: int | None = None
        self._run_summary_discarded: int | None = None
        self._in_run_summary = False

    def feed_line(self, raw: str) -> None:
        line = raw.rstrip("\n")
        stripped = line.strip()

        # Detect numbered step headers: "[1/10] Pre-download check"
        m = _GET_INTAKE_STEP_RE.match(stripped)
        if m:
            idx = int(m.group(1))
            total = int(m.group(2))
            label = m.group(3).strip()
            if not _GET_INTAKE_URL_RE.match(label):
                self._start_step(idx=idx, total=total, label=label)
                return

        if stripped == "Run summary":
            self._in_run_summary = True
            return

        if self._in_run_summary:
            self._parse_run_summary_line(stripped)
            return

        if not self._step_label:
            return

        # Parse step-local signals.
        if stripped.startswith("Precheck summary:"):
            # "Precheck summary: keep=23 skip=1 total=24"
            m2 = re.search(r"keep=(\d+)\s+skip=(\d+)\s+total=(\d+)", stripped)
            if m2:
                self._precheck_keep = int(m2.group(1))
                self._precheck_skip = int(m2.group(2))
                self._precheck_total = int(m2.group(3))
            return

        if stripped.startswith("Selected for download:"):
            m2 = re.search(r"Selected for download:\s*(\d+)\s+track", stripped)
            if m2:
                self._selected_for_download = int(m2.group(1))
            return

        if stripped.startswith("Downloaded "):
            # Path-free prefix: cut any trailing " /Volumes/..." etc.
            prefix = stripped.split(" /", 1)[0].strip()
            rest = prefix[len("Downloaded ") :].strip()
            title = rest
            quality = None
            if "  " in rest:
                title, tail = rest.split("  ", 1)
                title = title.strip()
                quality = tail.strip() or None
            if title:
                self._downloaded_titles.append(title)
            if quality:
                self._downloaded_qualities.append(f"{title} ({quality})")
            return

        if stripped.startswith("Exists "):
            prefix = stripped.split(" /", 1)[0].strip()
            title = prefix[len("Exists ") :].strip()
            if title:
                self._exists_titles.append(title)
            return

        if stripped.startswith("Error:"):
            # Keep the message but avoid leaking any path-y wrap lines.
            self._download_errors.append(stripped)
            return

        if stripped.startswith("Total:") and "RESULTS" not in stripped:
            m2 = re.search(r"Total:\s*(\d+)", stripped)
            if m2:
                self._index_total = int(m2.group(1))
            return

        if stripped.startswith("Duplicates:"):
            m2 = re.search(r"Duplicates:\s*(\d+)", stripped)
            if m2:
                self._index_duplicates = int(m2.group(1))
            return

        if stripped.startswith("Errors:"):
            m2 = re.search(r"Errors:\s*(\d+)", stripped)
            if m2:
                self._index_errors = int(m2.group(1))
            return

        if stripped.startswith("Discovered:"):
            m2 = re.search(r"Discovered:\s*(\d+)", stripped)
            if m2:
                self._scan_discovered = int(m2.group(1))
            return

        if stripped.startswith("Succeeded:"):
            m2 = re.search(r"Succeeded:\s*(\d+)", stripped)
            if m2:
                self._scan_succeeded = int(m2.group(1))
            return

        if stripped.startswith("Failed:"):
            m2 = re.search(r"Failed:\s*(\d+)", stripped)
            if m2:
                self._scan_failed = int(m2.group(1))
            return

        if stripped.startswith("* InputSkipped:"):
            m2 = re.search(r"InputSkipped:\s*(\d+)", stripped)
            if m2:
                self._scan_failure_inputs_skipped = int(m2.group(1))
            return

        if stripped.startswith("OK: scanned_files="):
            m2 = re.search(r"OK:\s*scanned_files=(\d+)", stripped)
            if m2:
                self._hoard_scanned_files = int(m2.group(1))
            return

        if stripped.startswith("OK: wrote ") and "tags_keys.txt" in stripped:
            # "OK: wrote /.../tag_hoard_out/tags_keys.txt"
            m2 = re.search(r"OK:\s*wrote\s+(.+tags_keys\.txt)", stripped)
            if m2:
                self._tag_keys_path = Path(m2.group(1)).expanduser()
            return

        if stripped.startswith("Scanned:"):
            m2 = re.search(r"Scanned:\s*(\d+)", stripped)
            if m2:
                # normalize_genres.py uses "Scanned: N"
                self._normalize_scanned = int(m2.group(1))
            return

        if stripped.startswith("Updated DB rows:"):
            m2 = re.search(r"Updated DB rows:\s*(\d+)", stripped)
            if m2:
                self._normalize_updated = int(m2.group(1))
            return

        if stripped.startswith("Tagged:"):
            m2 = re.search(r"Tagged:\s*(\d+)", stripped)
            if m2:
                self._genres_tagged = int(m2.group(1))
            return

        if stripped.startswith("Fingerprints in DB:"):
            m2 = re.search(r"To compute:\s*(\d+)", stripped)
            if m2:
                self._fpcalc_to_compute = int(m2.group(1))
            return

        if stripped.startswith("fpcalc computed:"):
            m2 = re.search(r"fpcalc computed:\s*ok=(\d+)", stripped)
            if m2:
                self._fpcalc_ok = int(m2.group(1))
            return

        if stripped.startswith("Fingerprint dupe groups:"):
            m2 = re.search(r"Fingerprint dupe groups:\s*(\d+)\s*\\(files_in_groups=(\d+)\\)", stripped)
            if m2:
                self._fp_dupe_groups = int(m2.group(1))
                self._fp_files_in_groups = int(m2.group(2))
            return

        if stripped.startswith("Planned promote:"):
            m2 = re.search(r"MOVE=(\d+)", stripped)
            if m2:
                self._planned_promote = int(m2.group(1))
            return

        if stripped.startswith("Planned stash MOVE rows:"):
            m2 = re.search(r"rows:\s*(\d+)", stripped)
            if m2:
                self._planned_stash = int(m2.group(1))
            return

        if stripped.startswith("Planned quarantine MOVE rows:"):
            m2 = re.search(r"rows:\s*(\d+)", stripped)
            if m2:
                self._planned_quarantine = int(m2.group(1))
            return

        if stripped.startswith("discard:"):
            # In the plan summary block, "discard: 0"
            m2 = re.search(r"discard:\s*(\d+)", stripped)
            if m2:
                self._planned_discard = int(m2.group(1))
            return

        if stripped.startswith("EXECUTE: planned="):
            # Example: "EXECUTE: planned=22 moved=22 skipped_missing=0 skipped_exists=0 failed=0"
            planned_m = re.search(r"planned=(\d+)", stripped)
            moved_m = re.search(r"moved=(\d+)", stripped)
            failed_m = re.search(r"failed=(\d+)", stripped)
            if planned_m and moved_m:
                planned = int(planned_m.group(1))
                moved = int(moved_m.group(1))
                # Heuristic: first EXECUTE block is promote, second is stash
                if self._moved_promote is None and (self._planned_promote == planned or self._planned_promote is None):
                    self._moved_promote = moved
                else:
                    self._moved_stash = moved
            if failed_m:
                self._moved_failed = int(failed_m.group(1))
            return

        if stripped.startswith("Named playlist:"):
            # "Named playlist: /Volumes/.../roon-foo.m3u"
            m2 = re.search(r"Named playlist:\s*(.+)$", stripped)
            if m2:
                self._named_playlist = Path(m2.group(1)).name
            return

        if stripped.startswith("Background enrich/art started: pid="):
            m2 = re.search(r"pid=(\d+)", stripped)
            if m2:
                self._background_pid = int(m2.group(1))
            return

    def finalize(self) -> None:
        self._finish_step()
        self._emit_final_run_summary()

    def _start_step(self, *, idx: int, total: int, label: str) -> None:
        self._finish_step()
        self._step_idx = idx
        self._step_total = total
        self._step_label = label
        if self._have_printed_header:
            self._emit("")
        self._emit(f"[{idx}/{total}] {label}")
        self._have_printed_header = True

    def _finish_step(self) -> None:
        if not self._step_label:
            return

        label = self._step_label.lower()
        if "pre-download check" in label:
            keep = self._precheck_keep
            skip = self._precheck_skip
            total = self._precheck_total
            if keep is not None and skip is not None and total is not None:
                self._emit(f"Precheck: {keep} keep, {skip} blocked (total {total}).")
        elif "download from" in label:
            downloaded = len(self._downloaded_titles)
            existed = len(self._exists_titles)
            failed = len(self._download_errors)
            selected = self._selected_for_download
            selected_txt = f"{selected} selected; " if selected is not None else ""
            self._emit(f"Download: {selected_txt}{downloaded} downloaded, {existed} already present, {failed} failed.")
            if self._download_errors:
                self._emit(
                    f"Errors: {_short_list(self._download_errors, limit=(9999 if self.verbose else 3))}"
                )
            if self._downloaded_titles:
                if self.verbose and self._downloaded_qualities:
                    self._emit(f"Downloaded: {_short_list(self._downloaded_qualities, limit=50)}")
                else:
                    self._emit(
                        f"Downloaded: {_short_list(self._downloaded_titles, limit=(50 if self.verbose else 12))}"
                    )
        elif "quick duplicate check" in label:
            if self._index_total is not None:
                dups = self._index_duplicates or 0
                errs = self._index_errors or 0
                self._emit(f"Index check: {self._index_total} files; {dups} duplicates; {errs} errors.")
        elif "trust scan" in label:
            if self._scan_discovered is not None:
                succ = self._scan_succeeded if self._scan_succeeded is not None else "?"
                fail = self._scan_failed if self._scan_failed is not None else "?"
                extra = ""
                if self._scan_failure_inputs_skipped:
                    extra = f" (InputSkipped={self._scan_failure_inputs_skipped})"
                self._emit(f"Scan/register: discovered {self._scan_discovered}; succeeded {succ}; failed {fail}{extra}.")
        elif "local identify" in label:
            if self._hoard_scanned_files is not None:
                self._emit(f"Tag hoard: scanned {self._hoard_scanned_files} files.")
            if self._tag_keys_path:
                # Only read keys if file looks fresh for this run.
                try:
                    if self._tag_keys_path.exists() and self._tag_keys_path.stat().st_mtime >= self.run_started - 1.0:
                        self._tag_keys = _read_text_lines(self._tag_keys_path)
                except Exception:
                    self._tag_keys = []
            if self._tag_keys:
                self._emit(
                    f"Tag keys: {len(self._tag_keys)} ({_short_list(self._tag_keys, limit=(60 if self.verbose else 18))})."
                )
            if self._normalize_updated is not None:
                scanned = self._normalize_scanned if self._normalize_scanned is not None else "?"
                self._emit(f"Genre normalization: scanned {scanned}; updated {self._normalize_updated}; tagged {self._genres_tagged or 0}.")
        elif "cross-root fingerprint audit" in label:
            pieces: list[str] = []
            if self._fpcalc_to_compute is not None:
                pieces.append(f"to_compute={self._fpcalc_to_compute}")
            if self._fpcalc_ok is not None:
                pieces.append(f"computed={self._fpcalc_ok}")
            if self._fp_dupe_groups is not None:
                extra = ""
                if self._fp_files_in_groups is not None:
                    extra = f" (files_in_groups={self._fp_files_in_groups})"
                pieces.append(f"dupe_groups={self._fp_dupe_groups}{extra}")
            if pieces:
                self._emit(f"Fingerprint audit: {', '.join(pieces)}.")
        elif "plan promote" in label:
            promote = self._planned_promote if self._planned_promote is not None else "?"
            stash = self._planned_stash if self._planned_stash is not None else "?"
            quarantine = self._planned_quarantine if self._planned_quarantine is not None else "?"
            discard = self._planned_discard if self._planned_discard is not None else "?"
            self._emit(f"Plan: promote {promote}, stash {stash}, quarantine {quarantine}, discard {discard}.")
        elif "apply plans" in label:
            promote = self._moved_promote if self._moved_promote is not None else "?"
            stash = self._moved_stash if self._moved_stash is not None else "?"
            failed = self._moved_failed if self._moved_failed is not None else 0
            self._emit(f"Apply: promoted {promote}; stashed {stash}; move failures {failed}.")
        elif "generate roon m3u" in label:
            if self._named_playlist:
                self._emit(f"M3U: wrote {self._named_playlist}.")
        elif "launch background enrich" in label:
            if self._background_pid is not None:
                self._emit(f"Enrich/art: started in background (pid {self._background_pid}).")

        self._step_idx = None
        self._step_total = None
        self._step_label = None

    def _parse_run_summary_line(self, stripped: str) -> None:
        # indented key/value lines only; ignore anything else.
        if not stripped.startswith("promoted:") and not stripped.startswith("stashed:") and not stripped.startswith(
            "quarantined:"
        ) and not stripped.startswith("discarded:"):
            return
        m = re.search(r"^(promoted|stashed|quarantined|discarded):\s*(\d+)\s*$", stripped)
        if not m:
            return
        key = m.group(1)
        value = int(m.group(2))
        if key == "promoted":
            self._run_summary_promoted = value
        elif key == "stashed":
            self._run_summary_stashed = value
        elif key == "quarantined":
            self._run_summary_quarantined = value
        elif key == "discarded":
            self._run_summary_discarded = value

    def _emit_final_run_summary(self) -> None:
        if (
            self._run_summary_promoted is None
            and self._run_summary_stashed is None
            and self._run_summary_quarantined is None
            and self._run_summary_discarded is None
        ):
            return
        self._emit("")
        self._emit(
            "Run result: "
            f"promoted={self._run_summary_promoted or 0}, "
            f"stashed={self._run_summary_stashed or 0}, "
            f"quarantined={self._run_summary_quarantined or 0}, "
            f"discarded={self._run_summary_discarded or 0}."
        )


def _parse_precheck_csv(csv_path: Path) -> dict[str, int]:
    """Parse precheck CSV to extract summary counts.

    Returns dict with keys: total, new, upgrade, blocked
    """
    if not csv_path.exists():
        return {"total": 0, "new": 0, "upgrade": 0, "blocked": 0}

    total = 0
    new = 0
    upgrade = 0
    blocked = 0

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            decision = row.get("decision", "").strip()
            reason = row.get("reason", "").strip()

            if decision == "skip":
                blocked += 1
            elif decision == "keep":
                # Distinguish new vs upgrade based on reason
                if "no inventory match" in reason:
                    new += 1
                elif "improves existing" in reason or "upgrade" in reason.lower():
                    upgrade += 1
                else:
                    # Default to new if reason unclear
                    new += 1

    return {"total": total, "new": new, "upgrade": upgrade, "blocked": blocked}


def _find_latest_precheck_csv(artifacts_dir: Path, url: str) -> Path | None:
    """Find most recent precheck_decisions_*.csv in artifacts/compare.

    Returns None if not found.
    """
    compare_dir = artifacts_dir / "compare"
    if not compare_dir.exists():
        return None

    # Find all precheck_decisions_*.csv files
    decision_files = sorted(
        compare_dir.glob("precheck_decisions_*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if decision_files:
        return decision_files[0]

    return None


def _find_latest_promoted_flacs_txt(artifacts_dir: Path) -> Path | None:
    """Find most recent promoted_flacs_*.txt in artifacts/compare."""
    compare_dir = artifacts_dir / "compare"
    if not compare_dir.exists():
        return None
    files = sorted(
        compare_dir.glob("promoted_flacs_*.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files[0] if files else None


def _load_promoted_flac_paths(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_precheck_skip_db_paths(decisions_csv: Path) -> list[str]:
    """Load existing inventory paths (db_path) from precheck skip rows.

    Used as a resume/fallback cohort when nothing was promoted in this run.
    """
    if not decisions_csv.exists():
        return []

    seen: set[str] = set()
    out: list[str] = []
    with decisions_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            decision = (raw.get("decision") or raw.get("action") or "").strip().lower()
            if decision != "skip":
                continue
            db_path = (raw.get("db_path") or "").strip()
            if not db_path:
                continue
            # Derivative stages operate over FLAC inputs.
            if Path(db_path).suffix.lower() != ".flac":
                continue
            if db_path in seen:
                continue
            seen.add(db_path)
            out.append(db_path)
    return out


def _resolve_identity_ids_for_paths(conn: sqlite3.Connection, paths: list[str]) -> list[int]:
    if not paths:
        return []
    placeholders = ", ".join("?" * len(paths))
    rows = conn.execute(
        f"""
        SELECT DISTINCT al.identity_id
        FROM asset_file af
        JOIN asset_link al ON al.asset_id = af.id
        WHERE af.path IN ({placeholders})
          AND (al.active IS NULL OR al.active = 1)
          AND al.identity_id IS NOT NULL
        """,
        paths,
    ).fetchall()
    return sorted({int(r[0]) for r in rows if r and r[0] is not None})


def _write_stage_cohort_artifact(
    *,
    artifact_dir: Path,
    stamp: str,
    stage: str,
    paths: list[str],
    identity_ids: list[int],
) -> Path:
    artifact_path = artifact_dir / f"intake_{stamp}_{stage}_cohort.json"
    payload = {
        "stage": stage,
        "paths": paths,
        "identity_ids": identity_ids,
    }
    artifact_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return artifact_path


def _run_tools_get(
    cmd: list[str],
    *,
    cwd: Path,
    verbose: bool,
    debug_raw: bool,
    run_started: float,
) -> None:
    """Run tools/get.

    - debug_raw=True streams raw output (paths).
    - Otherwise, parse tools/get-intake output and emit human-friendly summaries without paths.
    """

    if debug_raw:
        subprocess.run(
            cmd,
            check=True,
            cwd=str(cwd),
        )
        return

    def _emit(line: str) -> None:
        print(line, flush=True)

    summarizer = _GetIntakeHumanSummarizer(verbose=verbose, run_started=run_started, emit=_emit)
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            summarizer.feed_line(line)
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
    rc = proc.wait()
    summarizer.finalize()
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd)


def run_intake(
    url: str,
    *,
    db_path: Path,
    mp3: bool = False,
    dj: bool = False,
    dry_run: bool = False,
    mp3_root: Path | None = None,
    dj_root: Path | None = None,
    artifact_dir: Path | None = None,
    verbose: bool = False,
    debug_raw: bool = False,
    no_precheck: bool = False,
    force_download: bool = False,
) -> IntakeResult:
    """Run intake orchestration: precheck → download → promote → [mp3] → [dj].

    Args:
        url: Provider URL (Beatport, Tidal, Deezer)
        db_path: Path to tagslut database
        mp3: If True, run MP3 stage after promote
        dj: If True, run DJ stage after MP3 stage (implies mp3)
        dry_run: If True, precheck only (no download, no writes)
        mp3_root: MP3 asset output root (required if mp3=True; contract enforced by CLI)
        dj_root: DJ output root (required if dj=True; contract enforced by CLI)
        artifact_dir: Directory for JSON artifact output
        no_precheck: If True, explicitly waive precheck gating for the download pipeline.
        force_download: If True, keep matched tracks anyway during precheck (cohort expansion).

    Returns:
        IntakeResult with disposition, stages, and artifact paths
    """
    if dj:
        mp3 = True

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stages: list[IntakeStageResult] = []
    disposition = "completed"
    precheck_blocked = False
    precheck_summary: dict[str, int] = {}
    precheck_csv_path: Path | None = None

    # Resolve artifact directory
    if artifact_dir is None:
        artifact_dir = get_artifacts_dir() / "intake"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifacts_root = get_artifacts_dir()

    repo_root = Path(__file__).resolve().parents[2]
    precheck_script = repo_root / "tools" / "review" / "pre_download_check.py"
    get_script = repo_root / "tools" / "get"

    run_started = time.time()

    # ────────────────────────────────────────────────────────────────────
    # Stage 1: Precheck
    # ────────────────────────────────────────────────────────────────────
    if dry_run:
        if no_precheck:
            stages.append(
                IntakeStageResult(
                    stage="precheck",
                    status="skipped",
                    detail="waived by --no-precheck (dry-run)",
                )
            )
        else:
            try:
                precheck_out_dir = artifacts_root / "compare"
                precheck_out_dir.mkdir(parents=True, exist_ok=True)

                precheck_cmd = [
                    "python3",
                    str(precheck_script),
                    url,
                    "--db",
                    str(db_path),
                    "--out-dir",
                    str(precheck_out_dir),
                ]
                if not verbose:
                    precheck_cmd.append("--quiet")
                if force_download:
                    precheck_cmd.append("--force-keep-matched")

                subprocess.run(
                    precheck_cmd,
                    check=True,
                    capture_output=not verbose,
                    text=True if not verbose else None,
                    cwd=str(repo_root),
                )

                precheck_csv_path = _find_latest_precheck_csv(artifacts_root, url)
                if precheck_csv_path and precheck_csv_path.exists():
                    precheck_summary = _parse_precheck_csv(precheck_csv_path)
                else:
                    precheck_summary = {"total": 0, "new": 0, "upgrade": 0, "blocked": 0}

                total_keep = precheck_summary.get("new", 0) + precheck_summary.get("upgrade", 0)
                precheck_blocked = total_keep == 0 and precheck_summary.get("blocked", 0) > 0

                if precheck_blocked:
                    stages.append(
                        IntakeStageResult(
                            stage="precheck",
                            status="blocked",
                            detail=f"{precheck_summary.get('blocked', 0)} tracks blocked, 0 to download",
                            artifact_path=precheck_csv_path,
                        )
                    )
                    disposition = "blocked"
                else:
                    stages.append(
                        IntakeStageResult(
                            stage="precheck",
                            status="ok",
                            detail=(
                                f"{precheck_summary.get('new', 0)} new, "
                                f"{precheck_summary.get('upgrade', 0)} upgrade, "
                                f"{precheck_summary.get('blocked', 0)} blocked"
                            ),
                            artifact_path=precheck_csv_path,
                        )
                    )

            except subprocess.CalledProcessError as exc:
                stages.append(
                    IntakeStageResult(
                        stage="precheck",
                        status="failed",
                        detail=f"Precheck subprocess failed: {exc}",
                    )
                )
                disposition = "failed"
    else:
        # Non-dry-run: tools/get-intake owns the binding precheck unless explicitly waived.
        if no_precheck:
            stages.append(
                IntakeStageResult(
                    stage="precheck",
                    status="skipped",
                    detail="waived by --no-precheck",
                )
            )

    # ────────────────────────────────────────────────────────────────────
    # Stage 2: Download
    # ────────────────────────────────────────────────────────────────────
    if not dry_run and disposition == "completed":
        try:
            download_cmd = [str(get_script), url]
            if no_precheck:
                download_cmd.append("--no-precheck")
            if force_download:
                download_cmd.append("--force-download")
            if debug_raw:
                # Use tools/get-intake verbose mode when we explicitly request raw logs.
                download_cmd.append("--verbose")

            _run_tools_get(
                download_cmd,
                cwd=repo_root,
                verbose=verbose,
                debug_raw=debug_raw,
                run_started=run_started,
            )

            stages.append(
                IntakeStageResult(
                    stage="download",
                    status="ok",
                )
            )

            if not no_precheck:
                precheck_csv_path = _find_latest_precheck_csv(artifacts_root, url)
                if precheck_csv_path and precheck_csv_path.exists():
                    if precheck_csv_path.stat().st_mtime < (run_started - 1.0):
                        precheck_csv_path = None

                if precheck_csv_path and precheck_csv_path.exists():
                    precheck_summary = _parse_precheck_csv(precheck_csv_path)
                else:
                    precheck_summary = {"total": 0, "new": 0, "upgrade": 0, "blocked": 0}

                total_keep = precheck_summary.get("new", 0) + precheck_summary.get("upgrade", 0)
                precheck_blocked = total_keep == 0 and precheck_summary.get("blocked", 0) > 0
                if precheck_blocked:
                    precheck_stage = IntakeStageResult(
                        stage="precheck",
                        status="blocked",
                        detail=f"{precheck_summary.get('blocked', 0)} tracks blocked, 0 to download",
                        artifact_path=precheck_csv_path,
                    )
                else:
                    precheck_stage = IntakeStageResult(
                        stage="precheck",
                        status="ok",
                        detail=(
                            f"{precheck_summary.get('new', 0)} new, "
                            f"{precheck_summary.get('upgrade', 0)} upgrade, "
                            f"{precheck_summary.get('blocked', 0)} blocked"
                        ),
                        artifact_path=precheck_csv_path,
                    )

                if not stages or stages[0].stage != "precheck":
                    stages.insert(0, precheck_stage)

        except subprocess.CalledProcessError as exc:
            stages.append(
                IntakeStageResult(
                    stage="download",
                    status="failed",
                    detail=f"Download subprocess failed: exit {exc.returncode}",
                )
            )
            disposition = "failed"
    elif dry_run:
        stages.append(
            IntakeStageResult(
                stage="download",
                status="skipped",
                detail="--dry-run passed",
            )
        )

    # ────────────────────────────────────────────────────────────────────
    # Stage 3: Promote (observe promoted cohort file for this run)
    # ────────────────────────────────────────────────────────────────────
    promoted_txt: Path | None = None
    promoted_paths: list[str] = []
    if dry_run:
        stages.append(
            IntakeStageResult(
                stage="promote",
                status="skipped",
                detail="--dry-run passed",
            )
        )
    elif disposition == "failed":
        stages.append(
            IntakeStageResult(
                stage="promote",
                status="skipped",
                detail="blocked by earlier failure",
            )
        )
    else:
        promoted_txt = _find_latest_promoted_flacs_txt(artifacts_root)
        if promoted_txt and promoted_txt.exists() and promoted_txt.stat().st_mtime >= (run_started - 1.0):
            promoted_paths = _load_promoted_flac_paths(promoted_txt)

        if promoted_txt is None or not promoted_txt.exists() or promoted_txt.stat().st_mtime < (run_started - 1.0):
            stages.append(
                IntakeStageResult(
                    stage="promote",
                    status="skipped",
                    detail="No promoted cohort file found for this run.",
                )
            )
        elif not promoted_paths:
            stages.append(
                IntakeStageResult(
                    stage="promote",
                    status="skipped",
                    detail="Promoted cohort file was empty.",
                    artifact_path=promoted_txt,
                )
            )
        else:
            stages.append(
                IntakeStageResult(
                    stage="promote",
                    status="ok",
                    detail=f"{len(promoted_paths)} promoted",
                    artifact_path=promoted_txt,
                )
            )

    # ────────────────────────────────────────────────────────────────────
    # Stage 4: MP3 (full-tag mp3_asset)
    # ────────────────────────────────────────────────────────────────────
    mp3_inputs: list[str] = []
    mp3_inputs_source: str | None = None
    if dry_run:
        stages.append(
            IntakeStageResult(
                stage="mp3",
                status="skipped",
                detail="--dry-run passed" if mp3 else "--mp3 not passed",
            )
        )
    elif not mp3:
        stages.append(
            IntakeStageResult(
                stage="mp3",
                status="skipped",
                detail="--mp3 not passed",
            )
        )
    elif disposition == "failed":
        stages.append(
            IntakeStageResult(
                stage="mp3",
                status="skipped",
                detail="blocked by earlier failure",
            )
        )
    else:
        if mp3_root is None:
            stages.append(
                IntakeStageResult(
                    stage="mp3",
                    status="failed",
                    detail="--mp3 requires --mp3-root",
                )
            )
            disposition = "failed"
            mp3_inputs = []
        else:
            if promoted_paths:
                mp3_inputs = list(promoted_paths)
                mp3_inputs_source = "promoted_flacs"
            elif precheck_csv_path is not None:
                mp3_inputs = _load_precheck_skip_db_paths(precheck_csv_path)
                mp3_inputs_source = "precheck_skip_db_paths"

            if mp3_inputs:
                from tagslut.exec.mp3_build import build_full_tag_mp3_assets_from_flac_paths

                conn = sqlite3.connect(str(db_path))
                try:
                    identity_ids = _resolve_identity_ids_for_paths(conn, mp3_inputs)
                    artifact_path = _write_stage_cohort_artifact(
                        artifact_dir=artifact_dir,
                        stamp=stamp,
                        stage="mp3",
                        paths=mp3_inputs,
                        identity_ids=identity_ids,
                    )
                    build_result = build_full_tag_mp3_assets_from_flac_paths(
                        conn,
                        flac_paths=[Path(p) for p in mp3_inputs],
                        mp3_root=mp3_root,
                        dry_run=False,
                    )
                finally:
                    conn.close()

                status = "ok" if build_result.failed == 0 else "failed"
                stages.append(
                    IntakeStageResult(
                        stage="mp3",
                        status=status,
                        detail=f"{build_result.summary()} (inputs={len(mp3_inputs)} from {mp3_inputs_source})",
                        artifact_path=artifact_path,
                    )
                )
                if build_result.failed > 0:
                    disposition = "failed"
            else:
                stages.append(
                    IntakeStageResult(
                        stage="mp3",
                        status="skipped",
                        detail="no FLAC inputs selected",
                    )
                )

    # ────────────────────────────────────────────────────────────────────
    # Stage 5: DJ (DJ-copy mp3_asset; extends MP3 stage)
    # ────────────────────────────────────────────────────────────────────
    if dry_run:
        stages.append(
            IntakeStageResult(
                stage="dj",
                status="skipped",
                detail="--dry-run passed" if dj else "--dj not passed",
            )
        )
    elif not dj:
        stages.append(
            IntakeStageResult(
                stage="dj",
                status="skipped",
                detail="--dj not passed",
            )
        )
    elif disposition == "failed":
        stages.append(
            IntakeStageResult(
                stage="dj",
                status="skipped",
                detail="blocked by earlier failure",
            )
        )
    else:
        if dj_root is None:
            stages.append(
                IntakeStageResult(
                    stage="dj",
                    status="failed",
                    detail="--dj requires --dj-root",
                )
            )
            disposition = "failed"
        elif mp3_inputs:
            from tagslut.exec.mp3_build import build_dj_copies_from_full_tag_mp3_assets

            conn = sqlite3.connect(str(db_path))
            try:
                identity_ids = _resolve_identity_ids_for_paths(conn, mp3_inputs)
                artifact_path = _write_stage_cohort_artifact(
                    artifact_dir=artifact_dir,
                    stamp=stamp,
                    stage="dj",
                    paths=mp3_inputs,
                    identity_ids=identity_ids,
                )
                build_result = build_dj_copies_from_full_tag_mp3_assets(
                    conn,
                    flac_paths=[Path(p) for p in mp3_inputs],
                    dj_root=dj_root,
                    dry_run=False,
                )
            finally:
                conn.close()

            status = "ok" if build_result.failed == 0 else "failed"
            stages.append(
                IntakeStageResult(
                    stage="dj",
                    status=status,
                    detail=build_result.summary(),
                    artifact_path=artifact_path,
                )
            )
            if build_result.failed > 0:
                disposition = "failed"
        else:
            stages.append(
                IntakeStageResult(
                    stage="dj",
                    status="skipped",
                    detail="no FLAC inputs selected",
                )
            )

    # ────────────────────────────────────────────────────────────────────
    # Final disposition (resume semantics)
    # ────────────────────────────────────────────────────────────────────
    if disposition != "failed" and not dry_run and precheck_blocked:
        if not mp3 and not dj:
            disposition = "blocked"
        elif not mp3_inputs:
            disposition = "blocked"

    # ────────────────────────────────────────────────────────────────────
    # Write JSON artifact
    # ────────────────────────────────────────────────────────────────────
    result = IntakeResult(
        url=url,
        stages=stages,
        disposition=disposition,
        precheck_summary=precheck_summary,
        precheck_csv=precheck_csv_path,
        artifact_path=None,
    )

    artifact_path = artifact_dir / f"intake_url_{stamp}.json"
    artifact_data = result.to_dict()
    artifact_data["dry_run"] = dry_run
    artifact_data["mp3"] = mp3
    artifact_data["dj"] = dj
    artifact_data["mp3_root"] = str(mp3_root) if mp3_root is not None else None
    artifact_data["dj_root"] = str(dj_root) if dj_root is not None else None

    artifact_path.write_text(
        json.dumps(artifact_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    result.artifact_path = artifact_path

    return result
