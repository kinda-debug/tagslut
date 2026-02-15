#!/usr/bin/env python3
"""
enrich_library_from_hoard_fingerprint.py

Enrich healthy target FLAC files with missing tags from donor files that have
identical audio fingerprints in the tagslut DB.

Safety defaults:
- Dry-run by default (no file writes).
- Never overwrites existing non-empty target tags.
- Applies only to healthy DB rows (flac_ok=1 and integrity_state='valid').
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mutagen.flac import FLAC


TARGET_EXTENSIONS = {".flac"}

# Conservative allowlist for enrichment. We keep it wide enough for useful
# catalog metadata, but skip noisy/transient technical keys.
ALLOWED_KEYS = {
    "artist",
    "albumartist",
    "title",
    "album",
    "tracknumber",
    "tracktotal",
    "totaltracks",
    "discnumber",
    "disctotal",
    "totaldiscs",
    "date",
    "originaldate",
    "genre",
    "style",
    "bpm",
    "initialkey",
    "key",
    "label",
    "publisher",
    "organization",
    "catalognumber",
    "catalognumber",
    "isrc",
    "composer",
    "lyrics",
    "language",
    "comment",
    "comments",
    "albumsort",
    "artistsort",
    "albumartistsort",
    "titlesort",
    "musicbrainz_releasegroupid",
    "musicbrainz_albumid",
    "musicbrainz_artistid",
    "musicbrainz_trackid",
    "musicbrainz_recordingid",
    "beatport_track_id",
    "beatport_release_id",
    "spotify_track_id",
    "spotify_album_id",
    "itunestrackid",
    "itunesalbumid",
    "qobuz_track_id",
    "qobuz_album_id",
    "tidal_track_id",
    "tidal_album_id",
}

BLOCKED_PREFIXES = ("replaygain_", "_", "metadata_block_picture", "cover")

KEY_ALIASES = {
    "album artist": "albumartist",
    "catalog": "catalognumber",
    "catalog no": "catalognumber",
    "catalog number": "catalognumber",
    "catalog_number": "catalognumber",
    "catno": "catalognumber",
    "comments": "comment",
    "disc": "discnumber",
    "track": "tracknumber",
}

SCORE_KEYS = {
    "artist",
    "albumartist",
    "title",
    "album",
    "genre",
    "style",
    "label",
    "catalognumber",
    "isrc",
    "date",
    "originaldate",
    "bpm",
    "initialkey",
    "key",
}


@dataclass(frozen=True)
class DbRow:
    path: str
    fingerprint: str
    metadata_json: str | None


@dataclass(frozen=True)
class DonorChoice:
    path: str
    score: int
    tags: dict[str, list[str]]


@dataclass
class PlanRow:
    target_path: str
    donor_path: str
    fingerprint_sha1: str
    keys_to_add: list[str]
    tags_to_add: dict[str, list[str]]


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _safe_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _normalize_key(key: str) -> str:
    normalized = str(key).strip().lower()
    normalized = normalized.replace("-", "_")
    normalized = normalized.replace("\u0000", "")
    if normalized in KEY_ALIASES:
        normalized = KEY_ALIASES[normalized]
    return normalized


def _is_allowed_key(key: str) -> bool:
    if not key:
        return False
    if any(key.startswith(prefix) for prefix in BLOCKED_PREFIXES):
        return False
    if key not in ALLOWED_KEYS:
        return False
    return True


def _normalize_tag_map(raw_tags: dict[str, Any]) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for raw_key, raw_value in raw_tags.items():
        key = _normalize_key(raw_key)
        if not _is_allowed_key(key):
            continue
        values = _safe_list(raw_value)
        if not values:
            continue
        if key not in normalized:
            normalized[key] = []
        for value in values:
            if value not in normalized[key]:
                normalized[key].append(value)
    return normalized


def _fingerprint_where(prefixes: list[Path]) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    for prefix in prefixes:
        resolved = str(prefix.expanduser().resolve())
        if not resolved.endswith("/"):
            resolved += "/"
        clauses.append("path LIKE ?")
        params.append(resolved + "%")
    if not clauses:
        return "1=0", []
    return "(" + " OR ".join(clauses) + ")", params


def _load_rows(conn: sqlite3.Connection, roots: list[Path], require_exists: bool = False) -> list[DbRow]:
    where, params = _fingerprint_where(roots)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"""
        SELECT path, fingerprint, metadata_json
        FROM files
        WHERE {where}
          AND fingerprint IS NOT NULL
          AND fingerprint != ''
          AND flac_ok = 1
          AND lower(coalesce(integrity_state, '')) = 'valid'
        ORDER BY path
        """,
        params,
    ).fetchall()
    out: list[DbRow] = []
    for row in rows:
        path = str(row["path"])
        if require_exists and not Path(path).exists():
            continue
        out.append(
            DbRow(
                path=path,
                fingerprint=str(row["fingerprint"]).strip(),
                metadata_json=row["metadata_json"],
            )
        )
    return out


def _load_hoard_tags(hoard_jsonl: Path) -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {}
    with hoard_jsonl.open("r", encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            path = str(record.get("path") or "").strip()
            tags = record.get("tags")
            if not path or not isinstance(tags, dict):
                continue
            normalized = _normalize_tag_map(tags)
            if normalized:
                out[path] = normalized
    return out


def _metadata_tags(metadata_json: str | None) -> dict[str, list[str]]:
    if not metadata_json:
        return {}
    try:
        payload = json.loads(metadata_json)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return _normalize_tag_map(payload)


def _tag_score(tags: dict[str, list[str]]) -> int:
    score = 0
    for key in SCORE_KEYS:
        values = tags.get(key) or []
        if values:
            score += 1
    return score


def _choose_best_donor_by_fingerprint(
    donor_rows: list[DbRow],
    donor_tags: dict[str, dict[str, list[str]]],
) -> dict[str, DonorChoice]:
    best_by_fingerprint: dict[str, DonorChoice] = {}
    for donor_row in donor_rows:
        tags = donor_tags.get(donor_row.path) or _metadata_tags(donor_row.metadata_json)
        if not tags:
            continue
        score = _tag_score(tags)
        current = best_by_fingerprint.get(donor_row.fingerprint)
        candidate = DonorChoice(path=donor_row.path, score=score, tags=tags)
        if current is None:
            best_by_fingerprint[donor_row.fingerprint] = candidate
            continue
        if candidate.score > current.score:
            best_by_fingerprint[donor_row.fingerprint] = candidate
            continue
        if candidate.score == current.score and candidate.path < current.path:
            best_by_fingerprint[donor_row.fingerprint] = candidate
    return best_by_fingerprint


def _build_plan(
    target_rows: list[DbRow],
    donor_by_fingerprint: dict[str, DonorChoice],
    limit: int | None,
) -> list[PlanRow]:
    plan_rows: list[PlanRow] = []
    for target_row in target_rows:
        if Path(target_row.path).suffix.lower() not in TARGET_EXTENSIONS:
            continue
        donor = donor_by_fingerprint.get(target_row.fingerprint)
        if donor is None:
            continue
        if donor.path == target_row.path:
            continue

        target_tags = _metadata_tags(target_row.metadata_json)
        tags_to_add: dict[str, list[str]] = {}
        for key, donor_values in donor.tags.items():
            target_values = target_tags.get(key) or []
            if target_values:
                continue
            if donor_values:
                tags_to_add[key] = donor_values
        if not tags_to_add:
            continue

        plan_rows.append(
            PlanRow(
                target_path=target_row.path,
                donor_path=donor.path,
                fingerprint_sha1=hashlib.sha1(target_row.fingerprint.encode("utf-8", "ignore")).hexdigest(),
                keys_to_add=sorted(tags_to_add.keys()),
                tags_to_add=tags_to_add,
            )
        )
        if limit and len(plan_rows) >= limit:
            break
    return plan_rows


def _flac_tags_for_db(path: Path) -> dict[str, list[str]]:
    audio = FLAC(path)
    out: dict[str, list[str]] = {}
    for key, value in audio.tags.items():
        norm_key = _normalize_key(str(key))
        values = _safe_list(value)
        if not norm_key or not values:
            continue
        out[norm_key] = values
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich healthy library FLAC tags from hoarded donor metadata by fingerprint")
    parser.add_argument("--db", type=Path, default=None, help="SQLite DB path (default: $TAGSLUT_DB)")
    parser.add_argument("--donor-root", type=Path, action="append", required=True, help="Donor root (repeatable)")
    parser.add_argument("--target-root", type=Path, action="append", required=True, help="Target root (repeatable)")
    parser.add_argument("--hoard-jsonl", type=Path, required=True, help="files_tags.jsonl from hoard_tags.py --dump-files")
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/compare"), help="Output directory")
    parser.add_argument("--limit", type=int, help="Limit plan rows (testing)")
    parser.add_argument("--execute", action="store_true", help="Write tags to target files and update DB")
    parser.add_argument("--progress-interval", type=int, default=250, help="Progress interval for execute mode")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = (args.db or Path(os.environ.get("TAGSLUT_DB", ""))).expanduser().resolve()
    if not str(db_path):
        raise SystemExit("ERROR: --db not provided and $TAGSLUT_DB is not set")
    if not db_path.exists():
        raise SystemExit(f"ERROR: DB not found: {db_path}")

    donor_roots = [path.expanduser().resolve() for path in args.donor_root]
    target_roots = [path.expanduser().resolve() for path in args.target_root]
    hoard_jsonl = args.hoard_jsonl.expanduser().resolve()
    if not hoard_jsonl.exists():
        raise SystemExit(f"ERROR: hoard jsonl not found: {hoard_jsonl}")

    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    plan_csv = out_dir / f"plan_enrich_library_from_hoard_{stamp}.csv"
    summary_json = out_dir / f"enrich_library_from_hoard_summary_{stamp}.json"
    log_jsonl = out_dir / f"enrich_library_from_hoard_log_{stamp}.jsonl"

    conn = sqlite3.connect(str(db_path))
    try:
        donor_rows = _load_rows(conn, donor_roots)
        target_rows = _load_rows(conn, target_roots, require_exists=True)
    finally:
        conn.close()

    donor_tags = _load_hoard_tags(hoard_jsonl)
    donor_by_fingerprint = _choose_best_donor_by_fingerprint(donor_rows, donor_tags)
    plan_rows = _build_plan(target_rows, donor_by_fingerprint, args.limit)

    with plan_csv.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(
            file_obj,
            fieldnames=["target_path", "donor_path", "fingerprint_sha1", "keys_to_add", "tags_to_add_json"],
        )
        writer.writeheader()
        for row in plan_rows:
            writer.writerow(
                {
                    "target_path": row.target_path,
                    "donor_path": row.donor_path,
                    "fingerprint_sha1": row.fingerprint_sha1,
                    "keys_to_add": "|".join(row.keys_to_add),
                    "tags_to_add_json": json.dumps(row.tags_to_add, ensure_ascii=False, sort_keys=True),
                }
            )

    executed_files = 0
    executed_keys = 0
    skipped_missing = 0
    skipped_nonflac = 0
    failed = 0

    if args.execute:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("BEGIN")
            with log_jsonl.open("w", encoding="utf-8") as log_file:
                for index, row in enumerate(plan_rows, start=1):
                    target_path = Path(row.target_path)
                    event: dict[str, Any] = {
                        "event": "enrich_from_hoard",
                        "target_path": row.target_path,
                        "donor_path": row.donor_path,
                        "keys_to_add": row.keys_to_add,
                        "execute": True,
                    }

                    if not target_path.exists():
                        skipped_missing += 1
                        event["result"] = "skip_missing"
                        log_file.write(json.dumps(event, ensure_ascii=False) + "\n")
                        continue
                    if target_path.suffix.lower() not in TARGET_EXTENSIONS:
                        skipped_nonflac += 1
                        event["result"] = "skip_nonflac"
                        log_file.write(json.dumps(event, ensure_ascii=False) + "\n")
                        continue

                    try:
                        target_audio = FLAC(target_path)
                        file_keys_added = 0
                        for key, donor_values in row.tags_to_add.items():
                            existing_values = _safe_list(target_audio.tags.get(key))
                            if existing_values:
                                continue
                            target_audio.tags[key] = donor_values
                            file_keys_added += 1

                        if file_keys_added == 0:
                            event["result"] = "no_change"
                            log_file.write(json.dumps(event, ensure_ascii=False) + "\n")
                            continue

                        target_audio.save()
                        refreshed_tags = _flac_tags_for_db(target_path)
                        conn.execute(
                            "UPDATE files SET metadata_json=? WHERE path=?",
                            (json.dumps(refreshed_tags, ensure_ascii=False, sort_keys=True), row.target_path),
                        )

                        executed_files += 1
                        executed_keys += file_keys_added
                        event["result"] = "enriched"
                        event["file_keys_added"] = file_keys_added
                        log_file.write(json.dumps(event, ensure_ascii=False) + "\n")
                    except Exception as error:
                        failed += 1
                        event["result"] = "error"
                        event["error"] = f"{type(error).__name__}: {error}"
                        log_file.write(json.dumps(event, ensure_ascii=False) + "\n")

                    if index % max(1, int(args.progress_interval)) == 0:
                        print(f"Progress: {index}/{len(plan_rows)}")

            conn.commit()
        finally:
            conn.close()
    else:
        with log_jsonl.open("w", encoding="utf-8") as log_file:
            for row in plan_rows:
                log_file.write(
                    json.dumps(
                        {
                            "event": "enrich_from_hoard",
                            "target_path": row.target_path,
                            "donor_path": row.donor_path,
                            "keys_to_add": row.keys_to_add,
                            "execute": False,
                            "result": "dry_run",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    summary = {
        "db": str(db_path),
        "donor_roots": [str(path) for path in donor_roots],
        "target_roots": [str(path) for path in target_roots],
        "hoard_jsonl": str(hoard_jsonl),
        "donor_rows": len(donor_rows),
        "target_rows": len(target_rows),
        "donor_fingerprints_with_tags": len(donor_by_fingerprint),
        "plan_rows": len(plan_rows),
        "execute": bool(args.execute),
        "executed_files": executed_files,
        "executed_keys": executed_keys,
        "skipped_missing": skipped_missing,
        "skipped_nonflac": skipped_nonflac,
        "failed": failed,
        "outputs": {
            "plan_csv": str(plan_csv),
            "summary_json": str(summary_json),
            "log_jsonl": str(log_jsonl),
        },
    }
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"{mode}: donor_rows={len(donor_rows)} target_rows={len(target_rows)}")
    print(f"{mode}: donor_fps={len(donor_by_fingerprint)} planned={len(plan_rows)}")
    if args.execute:
        print(
            f"{mode}: enriched_files={executed_files} enriched_keys={executed_keys} "
            f"skipped_missing={skipped_missing} skipped_nonflac={skipped_nonflac} failed={failed}"
        )
    print(f"Wrote: {plan_csv}")
    print(f"Wrote: {summary_json}")
    print(f"Wrote: {log_jsonl}")
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
