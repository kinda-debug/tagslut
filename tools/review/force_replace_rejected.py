#!/usr/bin/env python3
"""
Force-promote previously rejected files into the master library.

Workflow:
- resolve duplicate pairs from an audit CSV
- merge non-destructive metadata from the current library copy into the incoming file
- move the current library copy into a work/quarantine root
- move the incoming file into its canonical library destination
- record receipts in v3 tables and update legacy files.path rows
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mutagen.flac import FLAC

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tagslut.exec import execute_move, record_move_receipt, update_legacy_path_with_receipt
from tagslut.storage.schema import init_db
from tagslut.utils.final_library_layout import FinalLibraryLayoutError, build_final_library_destination


CORE_TAGS = {
    "title",
    "artist",
    "album",
    "albumartist",
    "tracknumber",
    "discnumber",
    "date",
    "year",
    "originaldate",
    "isrc",
    "label",
    "genre",
    "bpm",
    "key",
    "musicbrainz_recordingid",
    "musicbrainz_albumid",
    "musicbrainz_artistid",
    "musicbrainz_albumartistid",
    "musicbrainz_trackid",
    "musicbrainz_releasegroupid",
}


@dataclass(frozen=True)
class PairPlan:
    group_id: str
    incoming_src: Path
    existing_library: Path
    incoming_dest: Path
    existing_quarantine_dest: Path
    existing_quality: tuple[int, int, int, int]
    incoming_quality: tuple[int, int, int, int]


def is_interesting(key: str) -> bool:
    return key.lower().strip() not in CORE_TAGS


def file_quality(path: Path) -> tuple[int, int, int, int]:
    audio = FLAC(path)
    info = audio.info
    try:
        size = int(path.stat().st_size)
    except Exception:
        size = 0
    return (
        int(getattr(info, "sample_rate", 0) or 0),
        int(getattr(info, "bits_per_sample", 0) or 0),
        int(getattr(info, "bitrate", 0) or 0),
        size,
    )


def merge_old_metadata_into_new(dest_existing: Path, src_new: Path, *, save: bool) -> tuple[int, int]:
    old = FLAC(dest_existing)
    new = FLAC(src_new)

    added_tags = 0
    added_pictures = 0

    for key, value in old.tags.items():
        if not is_interesting(key):
            continue
        if key not in new.tags:
            if isinstance(value, list):
                new.tags[key] = [str(v) for v in value]
            else:
                new.tags[key] = str(value)
            added_tags += 1

    if len(new.pictures) == 0 and len(old.pictures) > 0:
        for pic in old.pictures:
            new.add_picture(pic)
            added_pictures += 1

    if save and (added_tags or added_pictures):
        new.save()

    return added_tags, added_pictures


def canonical_library_dest(src: Path, library_root: Path) -> Path:
    audio = FLAC(src)
    raw_tags: dict[str, Any] = {k: list(v) if isinstance(v, list) else v for k, v in audio.tags.items()}
    try:
        return build_final_library_destination(raw_tags, library_root).dest_path
    except FinalLibraryLayoutError as exc:
        raise RuntimeError(f"Could not build library destination for {src}: {exc}") from exc


def _relative_under(path: Path, root: Path) -> Path:
    return path.resolve().relative_to(root.resolve())


def _group_rows(audit_csv: Path) -> dict[str, list[dict[str, str]]]:
    with audit_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("group_id") or "").strip()].append(row)
    return grouped


def resolve_pair_plans(
    *,
    audit_csv: Path,
    original_root: Path,
    incoming_root: Path,
    library_root: Path,
    quarantine_root: Path,
) -> tuple[list[PairPlan], list[str]]:
    grouped = _group_rows(audit_csv)
    plans: list[PairPlan] = []
    skipped: list[str] = []
    artist_root = original_root.name

    for group_id, rows in sorted(grouped.items(), key=lambda item: int(item[0] or 0)):
        incoming_match: tuple[Path, Path] | None = None
        library_match: tuple[Path, Path] | None = None

        for row in rows:
            raw_path = Path(str(row.get("path") or "").strip()).expanduser()
            try:
                rel = _relative_under(raw_path, original_root)
            except Exception:
                continue

            candidate_incoming = incoming_root / rel
            candidate_library = library_root / artist_root / rel

            if candidate_incoming.exists():
                incoming_match = (candidate_incoming, rel)
            if candidate_library.exists():
                library_match = (candidate_library, rel)

        if incoming_match is None or library_match is None:
            skipped.append(f"group {group_id}: unresolved incoming/library pair")
            continue

        incoming_src, _ = incoming_match
        existing_library, existing_rel = library_match
        incoming_dest = canonical_library_dest(incoming_src, library_root)
        existing_quarantine_dest = quarantine_root / "force_replaced_existing" / artist_root / existing_rel
        existing_quality = file_quality(existing_library)
        incoming_quality = file_quality(incoming_src)

        plans.append(
            PairPlan(
                group_id=group_id,
                incoming_src=incoming_src,
                existing_library=existing_library,
                incoming_dest=incoming_dest,
                existing_quarantine_dest=existing_quarantine_dest,
                existing_quality=existing_quality,
                incoming_quality=incoming_quality,
            )
        )

    return plans, skipped


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _record_move(
    conn: sqlite3.Connection,
    *,
    receipt,
    action: str,
    zone: str,
    mgmt_status: str,
    details: dict[str, Any],
    db_where_path: Path | None = None,
) -> int:
    write_result = record_move_receipt(
        conn,
        receipt=receipt,
        plan_id=None,
        action=action,
        zone=zone,
        mgmt_status=mgmt_status,
        script_name="tools/review/force_replace_rejected.py",
        details=details,
    )
    if receipt.status == "moved":
        update_legacy_path_with_receipt(
            conn,
            move_execution_id=write_result.move_execution_id,
            receipt=receipt,
            zone=zone,
            mgmt_status=mgmt_status,
            where_path=db_where_path,
        )
    return write_result.move_execution_id


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Force replace library files using rejected/quarantined inputs")
    ap.add_argument("--audit-csv", type=Path, required=True, help="audio_dupe_audit members CSV")
    ap.add_argument("--original-root", type=Path, required=True, help="Original batch root used in the audit CSV")
    ap.add_argument("--incoming-root", type=Path, required=True, help="Current root holding the rejected files")
    ap.add_argument("--library-root", type=Path, required=True, help="Master library root")
    ap.add_argument("--quarantine-root", type=Path, required=True, help="Work/quarantine root for replaced library files")
    ap.add_argument("--db", type=Path, required=True, help="tagslut SQLite DB")
    ap.add_argument("--log", type=Path, default=_REPO_ROOT / "artifacts" / "logs" / "force_replace_rejected.jsonl")
    ap.add_argument(
        "--replace-even-if-worse",
        action="store_true",
        help="Allow replacement even when the existing library file is equal or higher quality",
    )
    ap.add_argument("--execute", action="store_true", help="Perform moves (default: dry-run)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    audit_csv = args.audit_csv.expanduser().resolve()
    original_root = args.original_root.expanduser().resolve()
    incoming_root = args.incoming_root.expanduser().resolve()
    library_root = args.library_root.expanduser().resolve()
    quarantine_root = args.quarantine_root.expanduser().resolve()
    db_path = args.db.expanduser().resolve()
    log_path = args.log.expanduser().resolve()

    plans, skipped = resolve_pair_plans(
        audit_csv=audit_csv,
        original_root=original_root,
        incoming_root=incoming_root,
        library_root=library_root,
        quarantine_root=quarantine_root,
    )

    print(f"Resolved pairs: {len(plans)}")
    for msg in skipped:
        print(f"SKIP {msg}")
    if not plans:
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        merged_tags = 0
        merged_pictures = 0
        moved_existing = 0
        moved_incoming = 0

        for idx, plan in enumerate(plans, 1):
            print(f"[{idx}/{len(plans)}] group={plan.group_id}")
            print(f"  incoming: {plan.incoming_src}")
            print(f"  existing: {plan.existing_library}")
            print(f"  dest:     {plan.incoming_dest}")
            print(f"  stash:    {plan.existing_quarantine_dest}")
            print(
                f"  quality:  incoming={plan.incoming_quality[1]}bit/{plan.incoming_quality[0]} "
                f"existing={plan.existing_quality[1]}bit/{plan.existing_quality[0]}"
            )

            if not args.replace_even_if_worse and plan.existing_quality >= plan.incoming_quality:
                print("  decision: keep existing (equal or better quality)")
                continue

            tags_added, pics_added = merge_old_metadata_into_new(
                plan.existing_library,
                plan.incoming_src,
                save=bool(args.execute),
            )
            merged_tags += tags_added
            merged_pictures += pics_added

            quarantine_receipt = execute_move(
                plan.existing_library,
                plan.existing_quarantine_dest,
                execute=bool(args.execute),
                collision_policy="abort",
            )
            _append_jsonl(
                log_path,
                {
                    "kind": "quarantine_existing",
                    "group_id": plan.group_id,
                    **quarantine_receipt.to_dict(),
                },
            )
            if quarantine_receipt.status != "moved" and args.execute:
                raise RuntimeError(
                    f"Failed to move existing library file for group {plan.group_id}: "
                    f"{quarantine_receipt.status} {quarantine_receipt.error or ''}".strip()
                )
            if quarantine_receipt.status == "moved":
                _record_move(
                    conn,
                    receipt=quarantine_receipt,
                    action="FORCE_REPLACE_EXISTING",
                    zone="quarantine",
                    mgmt_status="force_replaced_existing",
                    details={"group_id": plan.group_id, "incoming_dest": str(plan.incoming_dest)},
                    db_where_path=plan.existing_library,
                )
                moved_existing += 1

            promote_receipt = execute_move(
                plan.incoming_src,
                plan.incoming_dest,
                execute=bool(args.execute),
                collision_policy="abort",
            )
            _append_jsonl(
                log_path,
                {
                    "kind": "promote_incoming",
                    "group_id": plan.group_id,
                    **promote_receipt.to_dict(),
                },
            )
            if promote_receipt.status != "moved" and args.execute:
                raise RuntimeError(
                    f"Failed to move incoming file for group {plan.group_id}: "
                    f"{promote_receipt.status} {promote_receipt.error or ''}".strip()
                )
            if promote_receipt.status == "moved":
                _record_move(
                    conn,
                    receipt=promote_receipt,
                    action="FORCE_PROMOTE_REJECTED",
                    zone="accepted",
                    mgmt_status="force_promoted_replacement",
                    details={"group_id": plan.group_id, "replaced_library_path": str(plan.existing_library)},
                    db_where_path=plan.incoming_src,
                )
                moved_incoming += 1

        if args.execute:
            conn.commit()

        print("RESULTS")
        print(f"pairs={len(plans)}")
        print(f"moved_existing={moved_existing}")
        print(f"moved_incoming={moved_incoming}")
        print(f"merged_tags={merged_tags}")
        print(f"merged_pictures={merged_pictures}")
        print(f"log={log_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
