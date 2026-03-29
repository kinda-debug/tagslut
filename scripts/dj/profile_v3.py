#!/usr/bin/env python3
"""Manage DJ profile rows for v3 identities."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tagslut.storage.v3.dj_profile import ensure_schema, get_profile, upsert_profile  # noqa: E402


def _connect_rw(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"v3 DB not found: {resolved}")
    conn = sqlite3.connect(str(resolved))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _cmd_get(args: argparse.Namespace) -> int:
    try:
        conn = _connect_rw(args.db)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2
    try:
        ensure_schema(conn)
        profile = get_profile(conn, int(args.identity))
    finally:
        conn.close()

    if profile is None:
        print(f"identity_id={int(args.identity)} has no dj profile")
        return 0
    print(json.dumps(profile, indent=2, sort_keys=True))
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    try:
        conn = _connect_rw(args.db)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2
    try:
        ensure_schema(conn)
        if (
            args.rating is None
            and args.energy is None
            and args.set_role is None
            and args.notes is None
            and args.last_played_at is None
            and not args.add_tag
            and not args.remove_tag
        ):
            print("no changes requested")
            return 2
        upsert_profile(
            conn,
            int(args.identity),
            rating=args.rating,
            energy=args.energy,
            set_role=args.set_role,
            notes=args.notes,
            add_tags=list(args.add_tag),
            remove_tags=list(args.remove_tag),
            last_played_at=args.last_played_at,
            allow_archived=bool(args.allow_archived),
        )
        updated = get_profile(conn, int(args.identity))
    except (RuntimeError, ValueError) as exc:
        print(str(exc))
        return 2
    finally:
        conn.close()

    print(json.dumps(updated, indent=2, sort_keys=True))
    return 0


def _cmd_bulk_set(args: argparse.Namespace) -> int:
    csv_path = args.csv.expanduser().resolve()
    if not csv_path.exists():
        print(f"csv not found: {csv_path}")
        return 2

    try:
        conn = _connect_rw(args.db)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    applied = 0
    failed = 0
    try:
        ensure_schema(conn)
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        for row in rows:
            identity_raw = (row.get("identity_id") or "").strip()
            if not identity_raw:
                failed += 1
                continue
            try:
                identity_id = int(identity_raw)
            except ValueError:
                failed += 1
                continue

            fields: dict[str, object] = {}
            if (row.get("rating") or "").strip() != "":
                fields["rating"] = int(str(row["rating"]).strip())
            if (row.get("energy") or "").strip() != "":
                fields["energy"] = int(str(row["energy"]).strip())
            if (row.get("set_role") or "").strip() != "":
                fields["set_role"] = str(row["set_role"]).strip()
            if (row.get("notes") or "").strip() != "":
                fields["notes"] = str(row["notes"])
            if (row.get("last_played_at") or "").strip() != "":
                fields["last_played_at"] = str(row["last_played_at"]).strip()
            tags_raw = (row.get("tags") or "").strip()
            if tags_raw:
                tags = [tag.strip() for tag in tags_raw.split(",") if tag.strip()]
                fields["dj_tags_json"] = json.dumps(sorted(set(tags)), separators=(",", ":"))

            if not fields:
                continue

            if args.dry_run:
                applied += 1
                continue

            try:
                upsert_profile(
                    conn,
                    identity_id,
                    rating=fields.get("rating"),
                    energy=fields.get("energy"),
                    set_role=fields.get("set_role"),
                    notes=fields.get("notes"),
                    last_played_at=fields.get("last_played_at"),
                    fields_dict={"dj_tags_json": fields["dj_tags_json"]} if "dj_tags_json" in fields else {},
                    allow_archived=bool(args.allow_archived),
                )
                applied += 1
            except (RuntimeError, ValueError):
                failed += 1

    finally:
        conn.close()

    print(f"rows_seen: {len(rows)}")
    print(f"rows_applied: {applied}")
    print(f"rows_failed: {failed}")
    print(f"dry_run: {1 if args.dry_run else 0}")
    return 0 if failed == 0 else 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage v3 DJ track profiles")
    sub = parser.add_subparsers(dest="command", required=True)

    get_cmd = sub.add_parser("get", help="Get profile by identity id")
    get_cmd.add_argument("--db", required=True, type=Path)
    get_cmd.add_argument("--identity", required=True, type=int)

    set_cmd = sub.add_parser("set", help="Set profile fields for one identity")
    set_cmd.add_argument("--db", required=True, type=Path)
    set_cmd.add_argument("--identity", required=True, type=int)
    set_cmd.add_argument("--rating", type=int)
    set_cmd.add_argument("--energy", type=int)
    set_cmd.add_argument("--set-role")
    set_cmd.add_argument("--notes")
    set_cmd.add_argument("--add-tag", action="append", default=[])
    set_cmd.add_argument("--remove-tag", action="append", default=[])
    set_cmd.add_argument("--last-played-at")
    set_cmd.add_argument("--allow-archived", action="store_true")

    bulk_cmd = sub.add_parser("bulk-set", help="Bulk set profile fields from CSV")
    bulk_cmd.add_argument("--db", required=True, type=Path)
    bulk_cmd.add_argument("--csv", required=True, type=Path)
    bulk_cmd.add_argument("--dry-run", action="store_true")
    bulk_cmd.add_argument("--allow-archived", action="store_true")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "get":
        return _cmd_get(args)
    if args.command == "set":
        return _cmd_set(args)
    if args.command == "bulk-set":
        return _cmd_bulk_set(args)
    print(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
