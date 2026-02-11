#!/usr/bin/env python3
"""
Reassess duration false-fails caused by ISRC/version mismatch.

This targets cases where:
1) Local file title/path indicates a versioned cut (extended/remix/edit/etc.),
2) The duration reference came from a local bootstrap source via ISRC,
3) Provider rows for that ISRC consistently describe a non-versioned title,
4) The measured duration differs strongly from the referenced duration.

For matched candidates, this script can set a manual duration reference equal to
the measured file duration, moving the file to duration_status=ok.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ISRC_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$")
VARIANT_WORDS = (
    "extended",
    "remix",
    "radio edit",
    "club mix",
    "dub",
    "edit",
    "instrumental",
    "rework",
    "version",
)


@dataclass
class Candidate:
    path: str
    status: str
    delta_ms: int
    measured_ms: int
    ref_ms: int
    ref_id: str
    ref_source: str
    provider_titles: list[str]
    local_title: str
    manual_ref_id: str


def _has_variant_marker(text: str) -> bool:
    lowered = (text or "").lower()
    return any(token in lowered for token in VARIANT_WORDS)


def _safe_json_load(payload: str | None) -> dict:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _extract_local_title(path: str, metadata_json: str | None) -> str:
    metadata = _safe_json_load(metadata_json)
    title = metadata.get("title") or metadata.get("TITLE")
    if isinstance(title, list):
        title = " ".join(str(item) for item in title if item is not None)
    return f"{title or ''} {path}".strip()


def _extract_provider_title(metadata_json: str | None) -> str:
    metadata = _safe_json_load(metadata_json)
    for key in ("title", "name", "track_name", "mix_name"):
        value = metadata.get(key)
        if value:
            return str(value).strip()
    return ""


def _manual_ref_id(path: str, sha256_hex: str | None) -> str:
    if sha256_hex:
        return f"manual_auto:{sha256_hex}"
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()
    return f"manual_auto_path:{digest}"


def find_candidates(
    conn: sqlite3.Connection,
    path_like: str,
    min_abs_delta_ms: int,
    require_local_bootstrap_source: bool,
) -> list[Candidate]:
    rows = conn.execute(
        """
        SELECT
            path,
            duration_status,
            duration_delta_ms,
            duration_measured_ms,
            duration_ref_ms,
            duration_ref_source,
            duration_ref_track_id,
            metadata_json,
            sha256
        FROM files
        WHERE path LIKE ?
          AND duration_status IN ('warn', 'fail')
          AND duration_delta_ms IS NOT NULL
          AND duration_measured_ms IS NOT NULL
          AND duration_ref_ms IS NOT NULL
          AND duration_ref_track_id IS NOT NULL
        ORDER BY path
        """,
        (path_like,),
    ).fetchall()

    candidates: list[Candidate] = []
    for row in rows:
        delta_ms = int(row["duration_delta_ms"])
        if abs(delta_ms) < min_abs_delta_ms:
            continue

        ref_source = str(row["duration_ref_source"] or "")
        if require_local_bootstrap_source and not ref_source.startswith("local_bootstrap"):
            continue

        ref_id = str(row["duration_ref_track_id"] or "").strip().upper()
        if not ISRC_RE.match(ref_id):
            continue

        local_title = _extract_local_title(row["path"], row["metadata_json"])
        if not _has_variant_marker(local_title):
            continue

        provider_rows = conn.execute(
            """
            SELECT service, duration_ms, metadata_json
            FROM library_track_sources
            WHERE isrc = ?
              AND duration_ms IS NOT NULL
            ORDER BY service
            """,
            (ref_id,),
        ).fetchall()
        if not provider_rows:
            continue

        ref_ms = int(row["duration_ref_ms"])
        # Ensure provider data actually supports the current reference.
        agreeing_provider_rows = [
            p for p in provider_rows if abs(int(p["duration_ms"]) - ref_ms) <= 10_000
        ]
        if not agreeing_provider_rows:
            continue

        provider_titles = []
        for provider_row in provider_rows:
            title = _extract_provider_title(provider_row["metadata_json"])
            if title:
                provider_titles.append(title)
        if not provider_titles:
            continue

        # If provider titles already contain variant markers, do not auto-correct.
        if any(_has_variant_marker(title) for title in provider_titles):
            continue

        candidates.append(
            Candidate(
                path=row["path"],
                status=str(row["duration_status"]),
                delta_ms=delta_ms,
                measured_ms=int(row["duration_measured_ms"]),
                ref_ms=ref_ms,
                ref_id=ref_id,
                ref_source=ref_source,
                provider_titles=provider_titles[:5],
                local_title=local_title,
                manual_ref_id=_manual_ref_id(row["path"], row["sha256"]),
            )
        )

    return candidates


def write_report(report_path: Path, candidates: list[Candidate]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "path",
                "status_before",
                "delta_ms_before",
                "measured_ms",
                "ref_ms_before",
                "ref_source_before",
                "ref_id_before",
                "local_title",
                "provider_titles",
                "manual_ref_id",
            ]
        )
        for candidate in candidates:
            writer.writerow(
                [
                    candidate.path,
                    candidate.status,
                    candidate.delta_ms,
                    candidate.measured_ms,
                    candidate.ref_ms,
                    candidate.ref_source,
                    candidate.ref_id,
                    candidate.local_title,
                    " | ".join(candidate.provider_titles),
                    candidate.manual_ref_id,
                ]
            )


def apply_candidates(
    conn: sqlite3.Connection,
    candidates: list[Candidate],
    source_label: str,
) -> tuple[int, int]:
    now_iso = datetime.now(timezone.utc).isoformat()
    inserted_refs = 0
    updated_files = 0

    for candidate in candidates:
        existing_ref = conn.execute(
            "SELECT ref_id FROM track_duration_refs WHERE ref_id = ?",
            (candidate.manual_ref_id,),
        ).fetchone()

        conn.execute(
            """
            INSERT OR REPLACE INTO track_duration_refs
                (ref_id, ref_type, duration_ref_ms, ref_source, ref_updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                candidate.manual_ref_id,
                "manual",
                candidate.measured_ms,
                source_label,
                now_iso,
            ),
        )
        if existing_ref is None:
            inserted_refs += 1

        conn.execute(
            """
            UPDATE files
            SET
                duration_ref_ms = ?,
                duration_ref_source = ?,
                duration_ref_track_id = ?,
                duration_ref_updated_at = ?,
                duration_delta_ms = 0,
                duration_status = 'ok',
                duration_check_version = 'duration_variant_guard_v1',
                is_dj_material = 1
            WHERE path = ?
            """,
            (
                candidate.measured_ms,
                source_label,
                candidate.manual_ref_id,
                now_iso,
                candidate.path,
            ),
        )
        updated_files += 1

    return inserted_refs, updated_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reassess and correct likely ISRC/version duration mismatches."
    )
    parser.add_argument("--db", type=Path, required=True, help="Path to SQLite DB.")
    parser.add_argument(
        "--path-like",
        default="/Volumes/MUSIC/LIBRARY/%",
        help="LIKE pattern for target files (default: /Volumes/MUSIC/LIBRARY/%%).",
    )
    parser.add_argument(
        "--min-abs-delta-ms",
        type=int,
        default=90_000,
        help="Minimum absolute delta in ms required to consider a mismatch (default: 90000).",
    )
    parser.add_argument(
        "--allow-non-bootstrap-source",
        action="store_true",
        help="Do not require duration_ref_source to start with local_bootstrap.",
    )
    parser.add_argument(
        "--source-label",
        default="manual_auto_variant_guard",
        help="duration_ref_source label for applied corrections.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional CSV report path. Default: <db_dir>/duration_variant_guard_candidates.csv",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply corrections (default is dry-run).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = args.db.expanduser().resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    report_path = args.report
    if report_path is None:
        report_path = db_path.parent / "duration_variant_guard_candidates.csv"
    report_path = report_path.expanduser().resolve()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        candidates = find_candidates(
            conn=conn,
            path_like=args.path_like,
            min_abs_delta_ms=int(args.min_abs_delta_ms),
            require_local_bootstrap_source=not args.allow_non_bootstrap_source,
        )
        write_report(report_path, candidates)

        print(f"DB: {db_path}")
        print(f"Scope: {args.path_like}")
        print(f"Candidate count: {len(candidates)}")
        print(f"Report: {report_path}")
        if candidates:
            print("Sample candidates:")
            for candidate in candidates[:10]:
                print(
                    f"  {candidate.status:>4} | delta={candidate.delta_ms:+7d} ms | "
                    f"ref={candidate.ref_id} -> {candidate.path}"
                )

        if not args.execute:
            print("Dry-run complete. Use --execute to apply corrections.")
            return 0

        inserted_refs, updated_files = apply_candidates(
            conn=conn,
            candidates=candidates,
            source_label=args.source_label,
        )
        conn.commit()
        print("Applied corrections:")
        print(f"  New manual refs: {inserted_refs}")
        print(f"  Updated files:   {updated_files}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
