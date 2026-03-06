#!/usr/bin/env python3
"""Plan/apply deterministic merges for duplicate beatport_id identities in v3."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

# Allow direct script execution from repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tagslut.storage.v3.merge_identities import (  # noqa: E402
    Group,
    WinnerSelection,
    choose_winner_identity,
    find_duplicate_beatport_groups,
    merge_group_by_repointing_assets,
    record_identity_merge_provenance,
)
from tagslut.storage.v3.schema import create_schema_v3  # noqa: E402

DEFAULT_OUT = Path("output/merge_plan_beatport_v3.csv")
PLAN_COLUMNS = [
    "beatport_id",
    "group_size",
    "winner_id",
    "loser_ids_json",
    "winner_score",
    "loser_scores_json",
    "assets_moved",
    "fields_to_copy_json",
    "action",
]


def _connect_ro(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"v3 DB not found: {resolved}")
    uri = f"file:{quote(str(resolved))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA query_only=ON")
    return conn


def _connect_rw(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"v3 DB not found: {resolved}")
    conn = sqlite3.connect(str(resolved))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _winner_score(selection: WinnerSelection) -> int:
    winner_id = int(selection.winner_id)
    for candidate in selection.candidate_scores:
        if int(candidate.identity_id) == winner_id:
            return int(candidate.score)
    raise RuntimeError(f"winner score missing for identity {winner_id}")


def _loser_scores_json(selection: WinnerSelection) -> str:
    payload = {
        str(candidate.identity_id): int(candidate.score)
        for candidate in selection.candidate_scores
        if int(candidate.identity_id) != int(selection.winner_id)
    }
    return json.dumps(payload, sort_keys=True)


def _write_plan_csv(out_path: Path, rows: list[dict[str, str]]) -> Path:
    resolved = out_path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAN_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan/apply merges for duplicate beatport_id identities in v3"
    )
    parser.add_argument("--db", required=True, type=Path, help="Path to music_v3.db")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Plan CSV output path (default: {DEFAULT_OUT})",
    )
    parser.add_argument("--limit", type=int, help="Optional plan row limit (plan mode only)")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply merges to DB (default is plan-only).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if groups exist in plan mode; fail on any merge failure in execute mode.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing remaining groups when one group fails.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Alias for plan-only mode (same as omitting --execute).",
    )
    return parser.parse_args(argv)


def _build_plan_row(
    group: Group,
    selection: WinnerSelection,
    loser_ids: tuple[int, ...],
    assets_moved: int,
    fields_to_copy: dict[str, object],
) -> dict[str, str]:
    return {
        "beatport_id": group.beatport_id,
        "group_size": str(len(group.identity_ids)),
        "winner_id": str(selection.winner_id),
        "loser_ids_json": json.dumps(list(loser_ids), sort_keys=True),
        "winner_score": str(_winner_score(selection)),
        "loser_scores_json": _loser_scores_json(selection),
        "assets_moved": str(int(assets_moved)),
        "fields_to_copy_json": json.dumps(fields_to_copy, sort_keys=True),
        "action": "merge",
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.execute and args.dry_run:
        print("cannot pass both --execute and --dry-run")
        return 2

    execute_mode = bool(args.execute)
    plan_mode = not execute_mode

    if args.limit is not None and int(args.limit) <= 0:
        print("--limit must be > 0")
        return 2

    db_path = args.db.expanduser().resolve()
    try:
        conn = _connect_rw(db_path) if execute_mode else _connect_ro(db_path)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    groups_found = 0
    groups_planned = 0
    groups_merged = 0
    assets_moved_total = 0
    failures: list[str] = []
    plan_rows: list[dict[str, str]] = []

    try:
        if execute_mode:
            # Applies additive, idempotent schema migrations for identity merge support.
            create_schema_v3(conn)

        groups = find_duplicate_beatport_groups(conn)
        groups_found = len(groups)

        if execute_mode and args.limit is not None:
            print("note: --limit is ignored in execute mode")

        groups_to_process = groups
        if plan_mode and args.limit is not None:
            groups_to_process = groups[: int(args.limit)]

        for group in groups_to_process:
            try:
                selection = choose_winner_identity(conn, group.identity_ids)
                loser_ids = tuple(
                    identity_id
                    for identity_id in group.identity_ids
                    if int(identity_id) != int(selection.winner_id)
                )

                preview = merge_group_by_repointing_assets(
                    conn,
                    selection.winner_id,
                    loser_ids,
                    dry_run=True,
                )
                plan_rows.append(
                    _build_plan_row(
                        group=group,
                        selection=selection,
                        loser_ids=loser_ids,
                        assets_moved=preview.assets_moved,
                        fields_to_copy=preview.fields_copied,
                    )
                )
                groups_planned += 1

                if execute_mode:
                    conn.execute("BEGIN")
                    applied = merge_group_by_repointing_assets(
                        conn,
                        selection.winner_id,
                        loser_ids,
                        dry_run=False,
                    )
                    record_identity_merge_provenance(conn, applied)
                    conn.commit()
                    groups_merged += 1
                    assets_moved_total += int(applied.assets_moved)
                else:
                    assets_moved_total += int(preview.assets_moved)
            except Exception as exc:  # noqa: BLE001
                if execute_mode:
                    conn.rollback()
                failures.append(f"beatport_id={group.beatport_id}: {exc}")
                if not args.continue_on_error:
                    break
    finally:
        conn.close()

    csv_out = _write_plan_csv(args.out, plan_rows)

    print(f"v3 db: {db_path}")
    print(f"mode: {'execute' if execute_mode else 'plan'}")
    print(f"groups_found: {groups_found}")
    print(f"groups_planned: {groups_planned}")
    print(f"groups_merged: {groups_merged}")
    print(f"assets_moved_total: {assets_moved_total}")
    print(f"failures: {len(failures)}")
    for failure in failures:
        print(f"- {failure}")
    print(f"plan_csv: {csv_out}")

    if args.strict and plan_mode and groups_found > 0:
        return 1
    if args.strict and execute_mode and failures:
        return 1
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
