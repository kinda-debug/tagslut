#!/usr/bin/env python3
"""Health-first rescan workflow.

What it does:
- Rescans audio files already in the DB using `flac -t`.
- Processes in priority order: trusted first, then less-trusted DJ, then the rest.
- Keeps files in place (no moves).
- Writes health results back to DB (`flac_ok`, `integrity_state`, `integrity_checked_at`).
- Optionally emits a healthy-only M3U in the same priority order.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class FileRow:
    path: str
    zone: str
    is_dj_material: int
    canonical_genre: str
    metadata_json: str


@dataclass(frozen=True)
class HealthResult:
    path: str
    state: str  # valid | recoverable | corrupt
    flac_ok: int
    error: str | None


@dataclass(frozen=True)
class ScanResult:
    health: HealthResult
    hoarded_tags: dict[str, list[str]] | None
    hoard_error: str | None


ELECTRONIC_TOKENS = (
    "electronic",
    "electronica",
    "house",
    "techno",
    "indie dance",
    "melodic house",
    "deep house",
    "nu disco",
    "ambient",
    "downtempo",
    "chill",
    "lounge",
    "afro house",
    "progressive house",
    "breakbeat",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_zone(zone: str | None) -> str:
    z = (zone or "").strip().lower()
    return z if z else "unknown"


def looks_dj(row: FileRow) -> bool:
    if int(row.is_dj_material or 0) == 1:
        return True
    g = (row.canonical_genre or "").lower()
    dj_tokens = ("house", "techno", "indie dance", "melodic house", "deep house", "nu disco", "electronica", "electronic", "dj")
    return any(t in g for t in dj_tokens)


def _safe_json_load(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _extract_text_values(payload: Mapping) -> list[str]:
    vals: list[str] = []
    for key in ("genre", "genres", "style", "styles", "musicbrainz_genre"):
        v = payload.get(key)
        if isinstance(v, str):
            vals.append(v)
        elif isinstance(v, list):
            vals.extend(str(x) for x in v if x is not None)
    return vals


def is_electronic_row(row: FileRow) -> bool:
    if int(row.is_dj_material or 0) == 1:
        return True
    genre_blob = " ".join([row.canonical_genre or "", " ".join(_extract_text_values(_safe_json_load(row.metadata_json)))]).lower()
    return any(tok in genre_blob for tok in ELECTRONIC_TOKENS)


def priority(row: FileRow) -> int:
    z = normalize_zone(row.zone)
    dj = looks_dj(row)
    if z == "accepted":
        return 0
    if z == "staging":
        return 1
    if z == "suspect" and dj:
        return 2
    if z == "suspect":
        return 3
    if z == "archive" and dj:
        return 4
    if z == "archive":
        return 5
    if z == "quarantine":
        return 7
    return 6


def classify_flac(path: str) -> HealthResult:
    p = Path(path)
    if not p.exists():
        return HealthResult(path=path, state="corrupt", flac_ok=0, error="File not found")

    try:
        res = subprocess.run(
            ["flac", "-t", "--silent", str(p)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return HealthResult(path=path, state="corrupt", flac_ok=0, error="flac binary missing")
    except Exception as exc:  # pragma: no cover - defensive
        return HealthResult(path=path, state="corrupt", flac_ok=0, error=f"{type(exc).__name__}: {exc}")

    if res.returncode == 0:
        return HealthResult(path=path, state="valid", flac_ok=1, error=None)

    stderr = (res.stderr or "").strip()
    if "MD5" in stderr.upper():
        return HealthResult(path=path, state="recoverable", flac_ok=0, error=(stderr[:400] or "MD5 mismatch"))
    return HealthResult(path=path, state="corrupt", flac_ok=0, error=(stderr[:400] or "Unknown FLAC error"))


def _extract_embedded_tags(path: str) -> dict[str, list[str]]:
    try:
        from mutagen import File as MutagenFile
    except Exception:
        return {}
    audio = MutagenFile(path)
    if not audio or not getattr(audio, "tags", None):
        return {}
    out: dict[str, list[str]] = {}
    for key, value in audio.tags.items():
        k = str(key).strip()
        if not k:
            continue
        if "picture" in k.lower() or "cover" in k.lower():
            continue
        vals: list[str] = []
        if isinstance(value, (list, tuple)):
            vals = [str(x).strip() for x in value if str(x).strip()]
        else:
            s = str(value).strip()
            if s:
                vals = [s]
        if vals:
            out[k] = vals[:20]
    return out


def scan_file(path: str, hoard_metadata: bool) -> ScanResult:
    health = classify_flac(path)
    if not hoard_metadata or health.flac_ok != 1:
        return ScanResult(health=health, hoarded_tags=None, hoard_error=None)
    try:
        tags = _extract_embedded_tags(path)
        return ScanResult(health=health, hoarded_tags=tags or None, hoard_error=None)
    except Exception as exc:  # pragma: no cover - defensive
        return ScanResult(health=health, hoarded_tags=None, hoard_error=f"{type(exc).__name__}: {exc}")


def merge_metadata(existing_json: str, hoarded_tags: dict[str, list[str]] | None) -> tuple[str | None, str | None]:
    if not hoarded_tags:
        return None, None
    payload = _safe_json_load(existing_json)
    for key, vals in hoarded_tags.items():
        if key not in payload:
            payload[key] = vals if len(vals) > 1 else vals[0]
    canonical_genre = None
    for gk in ("genre", "GENRE"):
        gv = payload.get(gk)
        if isinstance(gv, str) and gv.strip():
            canonical_genre = gv.strip()
            break
        if isinstance(gv, list) and gv:
            first = str(gv[0]).strip()
            if first:
                canonical_genre = first
                break
    return json.dumps(payload, ensure_ascii=False, sort_keys=True), canonical_genre


def iter_rows(conn: sqlite3.Connection, root: Path) -> Iterable[FileRow]:
    root_prefix = str(root)
    if not root_prefix.endswith("/"):
        root_prefix += "/"

    q = "SELECT path, zone, COALESCE(is_dj_material,0), COALESCE(canonical_genre,''), COALESCE(metadata_json,'') FROM files WHERE path LIKE ?"
    for r in conn.execute(q, (root_prefix + "%",)):
        yield FileRow(path=r[0], zone=r[1] or "", is_dj_material=int(r[2] or 0), canonical_genre=r[3] or "", metadata_json=r[4] or "")


def write_playlist(conn: sqlite3.Connection, root: Path, out_path: Path, electronic_only: bool) -> int:
    root_prefix = str(root)
    if not root_prefix.endswith("/"):
        root_prefix += "/"

    rows = []
    q = "SELECT path, zone, COALESCE(is_dj_material,0), COALESCE(canonical_genre,''), COALESCE(metadata_json,'') FROM files WHERE path LIKE ? AND flac_ok = 1 AND integrity_state = 'valid'"
    for r in conn.execute(q, (root_prefix + "%",)):
        row = FileRow(path=r[0], zone=r[1] or "", is_dj_material=int(r[2] or 0), canonical_genre=r[3] or "", metadata_json=r[4] or "")
        if electronic_only and not is_electronic_row(row):
            continue
        if Path(row.path).exists():
            rows.append(row)

    rows.sort(key=lambda rr: (priority(rr), normalize_zone(rr.zone), rr.path.lower()))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write("#EXTM3U\n")
        fh.write("#PLAYLIST:Health-Checked Priority Flow (trusted -> less-trusted DJ -> rest)\n")
        for rr in rows:
            fh.write(rr.path + "\n")
    return len(rows)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Rescan health by priority without moving files")
    ap.add_argument("--db", required=True, help="Path to SQLite DB")
    ap.add_argument("--root", default="/Volumes/MUSIC", help="Root prefix to rescan (default: /Volumes/MUSIC)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 1), help="Parallel workers")
    ap.add_argument("--limit", type=int, default=None, help="Limit files (testing)")
    ap.add_argument("--dry-run", action="store_true", help="Do not write DB updates")
    ap.add_argument("--playlist-out", default="/Volumes/MUSIC/LIBRARY/HEALTHY_PRIORITY_WORKFLOW.m3u", help="Healthy-only playlist output path")
    ap.add_argument("--no-playlist", action="store_true", help="Skip playlist output")
    ap.add_argument("--hoard-metadata", action="store_true", help="Hoard embedded file tags into files.metadata_json for health-pass files")
    ap.add_argument("--electronic-only", action="store_true", help="Exclude non-electronic tracks from scan and playlist")
    ap.add_argument("--progress-every", type=int, default=500, help="Progress interval")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).expanduser().resolve()
    root = Path(args.root).expanduser().resolve()

    if not db_path.exists():
        raise SystemExit(f"ERROR: DB not found: {db_path}")

    logs_dir = Path("artifacts/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    jsonl_path = logs_dir / f"health_rescan_{ts}.jsonl"
    summary_path = logs_dir / f"health_rescan_{ts}_summary.json"

    conn = sqlite3.connect(str(db_path))
    try:
        rows = list(iter_rows(conn, root))
    finally:
        conn.close()

    all_discovered = len(rows)
    electronic_filtered_out = 0
    if args.electronic_only:
        filtered = [r for r in rows if is_electronic_row(r)]
        electronic_filtered_out = len(rows) - len(filtered)
        rows = filtered

    rows.sort(key=lambda r: (priority(r), normalize_zone(r.zone), r.path.lower()))
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    total = len(rows)
    if total == 0:
        print("No files matched root filter.")
        return 0

    by_priority = {str(i): 0 for i in range(8)}
    by_zone = {}
    for r in rows:
        by_priority[str(priority(r))] += 1
        z = normalize_zone(r.zone)
        by_zone[z] = by_zone.get(z, 0) + 1

    print(f"DB: {db_path}")
    print(f"Root: {root}")
    print(f"Files discovered: {all_discovered}")
    if args.electronic_only:
        print(f"Excluded as non-electronic: {electronic_filtered_out}")
    print(f"Files queued: {total}")
    print(f"Priority buckets: {by_priority}")

    counts = {"valid": 0, "recoverable": 0, "corrupt": 0}
    updated = 0
    hoarded = 0
    hoard_failures = 0

    conn = sqlite3.connect(str(db_path))
    try:
        if not args.dry_run:
            conn.execute("BEGIN")

        with jsonl_path.open("w", encoding="utf-8") as log_fh:
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futures = {ex.submit(partial(scan_file, hoard_metadata=args.hoard_metadata), row.path): row for row in rows}
                for i, fut in enumerate(as_completed(futures), 1):
                    row = futures[fut]
                    result = fut.result()
                    health = result.health
                    counts[health.state] = counts.get(health.state, 0) + 1
                    if result.hoarded_tags:
                        hoarded += 1
                    if result.hoard_error:
                        hoard_failures += 1

                    rec = {
                        "ts": now_iso(),
                        "path": health.path,
                        "zone": normalize_zone(row.zone),
                        "priority": priority(row),
                        "is_dj_material": int(row.is_dj_material or 0),
                        "state": health.state,
                        "flac_ok": int(health.flac_ok),
                        "error": health.error,
                        "hoarded_tags": 0 if not result.hoarded_tags else len(result.hoarded_tags),
                        "hoard_error": result.hoard_error,
                    }
                    log_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

                    if not args.dry_run:
                        merged_json = None
                        inferred_genre = None
                        if args.hoard_metadata and health.flac_ok == 1:
                            merged_json, inferred_genre = merge_metadata(row.metadata_json, result.hoarded_tags)
                        conn.execute(
                            """
                            UPDATE files
                            SET flac_ok=?,
                                integrity_state=?,
                                integrity_checked_at=?,
                                metadata_json=COALESCE(?, metadata_json),
                                canonical_genre=CASE
                                    WHEN (canonical_genre IS NULL OR TRIM(canonical_genre)='')
                                     AND ? IS NOT NULL AND TRIM(?)<>''
                                    THEN ?
                                    ELSE canonical_genre
                                END
                            WHERE path=?
                            """,
                            (
                                int(health.flac_ok),
                                health.state,
                                now_iso(),
                                merged_json,
                                inferred_genre,
                                inferred_genre,
                                inferred_genre,
                                health.path,
                            ),
                        )
                        updated += 1

                    if i % max(1, args.progress_every) == 0:
                        print(
                            f"progress {i}/{total} "
                            f"valid={counts.get('valid',0)} recoverable={counts.get('recoverable',0)} corrupt={counts.get('corrupt',0)}"
                        )

        if not args.dry_run:
            conn.commit()
    finally:
        conn.close()

    playlist_count = 0
    if not args.no_playlist:
        conn = sqlite3.connect(str(db_path))
        try:
            playlist_count = write_playlist(
                conn,
                root=root,
                out_path=Path(args.playlist_out).expanduser(),
                electronic_only=bool(args.electronic_only),
            )
        finally:
            conn.close()

    summary = {
        "timestamp": now_iso(),
        "db": str(db_path),
        "root": str(root),
        "discovered": all_discovered,
        "excluded_non_electronic": electronic_filtered_out,
        "queued": total,
        "updated": updated,
        "dry_run": bool(args.dry_run),
        "workers": int(args.workers),
        "electronic_only": bool(args.electronic_only),
        "hoard_metadata": bool(args.hoard_metadata),
        "hoarded_files": hoarded,
        "hoard_failures": hoard_failures,
        "by_zone": by_zone,
        "by_priority": by_priority,
        "results": counts,
        "jsonl_log": str(jsonl_path),
        "playlist_out": None if args.no_playlist else str(Path(args.playlist_out).expanduser()),
        "playlist_track_count": playlist_count,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("Done.")
    print(f"Result counts: {counts}")
    if args.hoard_metadata:
        print(f"Hoarded metadata for: {hoarded} file(s), failures: {hoard_failures}")
    if not args.no_playlist:
        print(f"Playlist tracks (health-pass only): {playlist_count}")
        print(f"Playlist: {Path(args.playlist_out).expanduser()}")
    print(f"Log: {jsonl_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
