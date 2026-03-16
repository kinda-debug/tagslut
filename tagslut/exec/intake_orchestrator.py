"""Intake orchestrator for `tagslut intake url` command.

Orchestrates:
1. Precheck (binding by default for non-dry-run; owned by tools/get-intake)
2. Download + local tag prep + promote (via tools/get-intake, called via tools/get)
3. MP3 transcode (scoped to this intake's promoted cohort if --mp3 passed)

Emits structured JSON artifact on every invocation.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import csv
import sqlite3

from tagslut.exec.mp3_build import build_mp3_from_identity
from tagslut.utils.env_paths import get_artifacts_dir


@dataclass
class IntakeStageResult:
    """Result of a single intake stage."""

    stage: str  # "precheck" | "download" | "promote" | "mp3"
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


def run_intake(
    url: str,
    *,
    db_path: Path,
    mp3: bool = False,
    dry_run: bool = False,
    dj_root: Path | None = None,
    artifact_dir: Path | None = None,
    verbose: bool = False,
    no_precheck: bool = False,
    force_download: bool = False,
) -> IntakeResult:
    """Run intake orchestration: precheck → download → promote → [mp3].

    Args:
        url: Provider URL (Beatport, Tidal, Deezer)
        db_path: Path to tagslut database
        mp3: If True, transcode to MP3 after promote
        dry_run: If True, precheck only (no download, no writes)
        dj_root: DJ MP3 output root (required if mp3=True)
        artifact_dir: Directory for JSON artifact output
        no_precheck: If True, explicitly waive precheck gating for the download pipeline.
        force_download: If True, keep matched tracks anyway during precheck (cohort expansion).

    Returns:
        IntakeResult with disposition, stages, and artifact paths
    """
    stages: list[IntakeStageResult] = []
    disposition = "completed"
    precheck_summary: dict[str, int] = {}
    precheck_csv_path: Path | None = None

    # Resolve artifact directory
    if artifact_dir is None:
        artifact_dir = get_artifacts_dir() / "intake"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    repo_root = Path(__file__).resolve().parents[2]
    precheck_script = repo_root / "tools" / "review" / "pre_download_check.py"
    get_script = repo_root / "tools" / "get"

    # ────────────────────────────────────────────────────────────────────
    # Stage 1: Precheck
    # ────────────────────────────────────────────────────────────────────
    run_started = time.time()
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
                precheck_out_dir = get_artifacts_dir() / "compare"
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
                )

                precheck_csv_path = _find_latest_precheck_csv(get_artifacts_dir(), url)
                if precheck_csv_path and precheck_csv_path.exists():
                    precheck_summary = _parse_precheck_csv(precheck_csv_path)
                else:
                    precheck_summary = {"total": 0, "new": 0, "upgrade": 0, "blocked": 0}

                total_keep = precheck_summary.get("new", 0) + precheck_summary.get("upgrade", 0)
                if total_keep == 0 and precheck_summary.get("blocked", 0) > 0:
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
    # Stage 2: Download (only if precheck has tracks to download)
    # ────────────────────────────────────────────────────────────────────
    if disposition == "completed" and not dry_run:
        try:
            download_cmd = [str(get_script), url]
            if no_precheck:
                download_cmd.append("--no-precheck")
            if force_download:
                download_cmd.append("--force-download")
            if verbose:
                download_cmd.append("--verbose")

            subprocess.run(
                download_cmd,
                check=True,
                capture_output=not verbose,
                text=True if not verbose else None,
                cwd=str(repo_root),
            )

            stages.append(
                IntakeStageResult(
                    stage="download",
                    status="ok",
                    detail=None,
                )
            )

            if not no_precheck:
                precheck_csv_path = _find_latest_precheck_csv(get_artifacts_dir(), url)
                if precheck_csv_path and precheck_csv_path.exists():
                    if precheck_csv_path.stat().st_mtime < (run_started - 1.0):
                        precheck_csv_path = None

                if precheck_csv_path and precheck_csv_path.exists():
                    precheck_summary = _parse_precheck_csv(precheck_csv_path)
                else:
                    precheck_summary = {"total": 0, "new": 0, "upgrade": 0, "blocked": 0}

                total_keep = precheck_summary.get("new", 0) + precheck_summary.get("upgrade", 0)
                if total_keep == 0 and precheck_summary.get("blocked", 0) > 0:
                    precheck_stage = IntakeStageResult(
                        stage="precheck",
                        status="blocked",
                        detail=f"{precheck_summary.get('blocked', 0)} tracks blocked, 0 to download",
                        artifact_path=precheck_csv_path,
                    )
                    disposition = "blocked"
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

    elif dry_run and disposition == "completed":
        stages.append(
            IntakeStageResult(
                stage="download",
                status="skipped",
                detail="--dry-run passed",
            )
        )

    # ────────────────────────────────────────────────────────────────────
    # Stage 3: MP3 (only if --mp3 passed and download succeeded)
    # ────────────────────────────────────────────────────────────────────
    if mp3 and disposition == "completed" and not dry_run:
        if dj_root is None:
            stages.append(
                IntakeStageResult(
                    stage="mp3",
                    status="failed",
                    detail="--mp3 requires --dj-root",
                )
            )
            disposition = "failed"
        else:
            try:
                artifacts_dir = get_artifacts_dir()
                promoted_txt = _find_latest_promoted_flacs_txt(artifacts_dir)
                if (
                    promoted_txt is None
                    or not promoted_txt.exists()
                    or promoted_txt.stat().st_mtime < (run_started - 1.0)
                ):
                    stages.append(
                        IntakeStageResult(
                            stage="mp3",
                            status="skipped",
                            detail="No promoted cohort file found for this run; MP3 build not run.",
                        )
                    )
                else:
                    promoted_paths = _load_promoted_flac_paths(promoted_txt)
                    if not promoted_paths:
                        stages.append(
                            IntakeStageResult(
                                stage="mp3",
                                status="skipped",
                                detail="Promoted cohort file was empty; MP3 build not run.",
                            )
                        )
                    else:
                        conn = sqlite3.connect(str(db_path))
                        try:
                            identity_ids = _resolve_identity_ids_for_paths(conn, promoted_paths)
                            if not identity_ids:
                                stages.append(
                                    IntakeStageResult(
                                        stage="mp3",
                                        status="skipped",
                                        detail="Promoted cohort did not resolve to any track_identity rows; MP3 build not run.",
                                    )
                                )
                            else:
                                mp3_result = build_mp3_from_identity(
                                    conn,
                                    identity_ids=identity_ids,
                                    dj_root=dj_root,
                                    dry_run=False,
                                )

                                if mp3_result.failed > 0:
                                    stages.append(
                                        IntakeStageResult(
                                            stage="mp3",
                                            status="ok",
                                            detail=f"{mp3_result.built} built, {mp3_result.skipped} skipped, {mp3_result.failed} failed",
                                        )
                                    )
                                else:
                                    stages.append(
                                        IntakeStageResult(
                                            stage="mp3",
                                            status="ok",
                                            detail=f"{mp3_result.built} built, {mp3_result.skipped} skipped",
                                        )
                                    )
                        finally:
                            conn.close()

            except Exception as exc:
                stages.append(
                    IntakeStageResult(
                        stage="mp3",
                        status="failed",
                        detail=f"MP3 build error: {exc}",
                    )
                )
                disposition = "failed"

    elif not mp3:
        stages.append(
            IntakeStageResult(
                stage="mp3",
                status="skipped",
                detail="--mp3 not passed",
            )
        )

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

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact_path = artifact_dir / f"intake_url_{ts}.json"
    artifact_data = result.to_dict()
    artifact_data["dry_run"] = dry_run

    artifact_path.write_text(
        json.dumps(artifact_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    result.artifact_path = artifact_path

    return result
