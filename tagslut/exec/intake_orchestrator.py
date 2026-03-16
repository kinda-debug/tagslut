"""Intake orchestrator for `tagslut intake url` command.

Orchestrates:
1. Precheck (binding by default for non-dry-run; owned by tools/get-intake)
2. Download + local tag prep + promote (via tools/get-intake, called via tools/get)
3. MP3 stage (full-tag mp3_asset generation; scoped to promoted cohort with resume fallback)
4. DJ stage  (DJ-copy mp3_asset generation; extends MP3 stage)

Emits structured JSON artifact on every invocation.
"""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
