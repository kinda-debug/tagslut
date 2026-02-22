#!/usr/bin/env python3
"""
Build track_duration_refs for unknown files using provider ISRC lookup.

Primary source: Spotify ISRC search (exact ISRC match).
Optional fallback: Tidal text search filtered by exact ISRC.

Safety guards:
- Skip ambiguous provider durations (spread too high).
- Skip likely version mismatch cases (extended/remix local title vs plain provider title
  with large duration delta), similar to known Jimi Jules false-fail pattern.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.providers.beatport import BeatportProvider
from tagslut.metadata.providers.spotify import SpotifyProvider
from tagslut.metadata.providers.tidal import TidalProvider


ISRC_SPLIT_RE = re.compile(r"[;,/\\]|\s+")
ISRC_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$")
VARIANT_WORDS = (
    "extended",
    "ext",
    "remix",
    "radio edit",
    "club mix",
    "dub",
    "edit",
    "version",
    "instrumental",
    "rework",
)


@dataclass
class LocalSample:
    path: str
    title: str
    measured_ms: int | None


@dataclass
class Resolution:
    isrc: str
    outcome: str
    source: str
    duration_ms: int | None
    providers_checked: str
    provider_titles: str
    local_paths: str
    notes: str


def _has_variant_marker(text: str) -> bool:
    lowered = (text or "").lower()
    return any(token in lowered for token in VARIANT_WORDS)


def _normalize_isrc_tokens(value) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in values:
        for token in ISRC_SPLIT_RE.split(str(item).strip().upper()):
            token = token.strip()
            if ISRC_RE.match(token):
                out.append(token)
    # stable dedup
    seen = set()
    unique = []
    for token in out:
        if token in seen:
            continue
        seen.add(token)
        unique.append(token)
    return unique


def _safe_json_load(payload: str | None) -> dict:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def collect_unknown_isrc_samples(conn: sqlite3.Connection, path_like: str) -> dict[str, list[LocalSample]]:
    rows = conn.execute(
        """
        SELECT path, metadata_json, duration_measured_ms
        FROM files
        WHERE path LIKE ?
          AND duration_status = 'unknown'
          AND duration_ref_ms IS NULL
        ORDER BY path
        """,
        (path_like,),
    ).fetchall()

    samples: dict[str, list[LocalSample]] = {}
    for row in rows:
        meta = _safe_json_load(row["metadata_json"])
        title = meta.get("title") or meta.get("TITLE")
        if isinstance(title, list):
            title = " ".join(str(x) for x in title if x is not None)
        title = str(title or "").strip()

        raw_isrc = meta.get("isrc") or meta.get("ISRC") or meta.get("tsrc") or meta.get("TSRC")
        tokens = _normalize_isrc_tokens(raw_isrc)
        if not tokens:
            continue

        for token in tokens:
            samples.setdefault(token, []).append(
                LocalSample(
                    path=row["path"],
                    title=title,
                    measured_ms=int(row["duration_measured_ms"]) if row["duration_measured_ms"] is not None else None,
                )
            )
    return samples


def query_spotify_isrc(provider: SpotifyProvider, isrc: str) -> tuple[list[int], list[str]]:
    tracks = provider.search_by_isrc(isrc)
    durations = []
    titles = []
    for track in tracks:
        if track.isrc and track.isrc.upper() != isrc.upper():
            continue
        if track.duration_ms is not None:
            durations.append(int(track.duration_ms))
        if track.title:
            titles.append(str(track.title))
    return durations, titles


def query_tidal_isrc(provider: TidalProvider, isrc: str) -> tuple[list[int], list[str]]:
    # Tidal has no native ISRC endpoint in this provider; use search + exact ISRC filter.
    tracks = provider.search(isrc, limit=20)
    durations = []
    titles = []
    for track in tracks:
        if not track.isrc or track.isrc.upper() != isrc.upper():
            continue
        if track.duration_ms is not None:
            durations.append(int(track.duration_ms))
        if track.title:
            titles.append(str(track.title))
    return durations, titles


def query_beatport_isrc(provider: BeatportProvider, isrc: str) -> tuple[list[int], list[str]]:
    tracks = provider.search_by_isrc(isrc)
    durations = []
    titles = []
    for track in tracks:
        if track.isrc and track.isrc.upper() != isrc.upper():
            continue
        if track.duration_ms is not None:
            durations.append(int(track.duration_ms))
        if track.title:
            titles.append(str(track.title))
    return durations, titles


def choose_duration(durations: list[int], max_spread_ms: int) -> tuple[int | None, str]:
    if not durations:
        return None, "no_duration"
    ordered = sorted(durations)
    spread = ordered[-1] - ordered[0]
    if spread > max_spread_ms:
        return None, f"ambiguous_spread_{spread}"
    return ordered[len(ordered) // 2], "ok"


def variant_mismatch_guard(
    samples: Iterable[LocalSample],
    provider_titles: list[str],
    provider_duration_ms: int,
    min_delta_ms: int,
) -> tuple[bool, str]:
    provider_has_variant = any(_has_variant_marker(title) for title in provider_titles)
    if provider_has_variant:
        return False, ""

    for sample in samples:
        local_text = f"{sample.title} {sample.path}"
        if not _has_variant_marker(local_text):
            continue
        if sample.measured_ms is None:
            continue
        if abs(sample.measured_ms - provider_duration_ms) >= min_delta_ms:
            return True, "variant_mismatch_guard"
    return False, ""


def write_report(path: Path, rows: list[Resolution]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "isrc",
                "outcome",
                "source",
                "duration_ms",
                "providers_checked",
                "provider_titles",
                "local_paths",
                "notes",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.isrc,
                    row.outcome,
                    row.source,
                    row.duration_ms if row.duration_ms is not None else "",
                    row.providers_checked,
                    row.provider_titles,
                    row.local_paths,
                    row.notes,
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build duration refs for unknown files from provider ISRC lookups.")
    parser.add_argument("--db", type=Path, required=True, help="SQLite DB path.")
    parser.add_argument(
        "--path-like",
        default="/Volumes/MUSIC/LIBRARY/%",
        help="LIKE pattern of target files (default: /Volumes/MUSIC/LIBRARY/%%).",
    )
    parser.add_argument(
        "--providers",
        default="beatport,spotify,tidal",
        help="Provider order (comma-separated). Default: beatport,spotify,tidal",
    )
    parser.add_argument(
        "--max-isrc",
        type=int,
        default=0,
        help="Limit number of ISRCs processed (0 = all).",
    )
    parser.add_argument(
        "--max-spread-ms",
        type=int,
        default=10000,
        help="Max allowed spread among provider durations for one ISRC (default: 10000).",
    )
    parser.add_argument(
        "--variant-guard-delta-ms",
        type=int,
        default=90000,
        help="Min measured-vs-provider delta to trigger variant mismatch guard (default: 90000).",
    )
    parser.add_argument(
        "--source-label",
        default="isrc_provider_guarded",
        help="ref_source to write for accepted refs.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="CSV report path. Default: <db_dir>/isrc_provider_resolution_report.csv",
    )
    parser.add_argument("--execute", action="store_true", help="Write refs to DB (default: dry-run).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = args.db.expanduser().resolve()
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    report_path = args.report.expanduser().resolve() if args.report else db_path.parent / "isrc_provider_resolution_report.csv"
    providers_order = [p.strip().lower() for p in args.providers.split(",") if p.strip()]
    if not providers_order:
        raise SystemExit("No providers configured.")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    tm = TokenManager()
    beatport = BeatportProvider(tm)
    spotify = SpotifyProvider(tm)
    tidal = TidalProvider(tm)

    try:
        samples_by_isrc = collect_unknown_isrc_samples(conn, args.path_like)
        existing_refs = {
            row["ref_id"].strip().upper()
            for row in conn.execute("SELECT ref_id FROM track_duration_refs WHERE ref_type = 'isrc'")
            if row["ref_id"]
        }

        isrcs = [isrc for isrc in sorted(samples_by_isrc.keys()) if isrc not in existing_refs]
        if args.max_isrc and args.max_isrc > 0:
            isrcs = isrcs[: int(args.max_isrc)]

        print(f"DB: {db_path}")
        print(f"Scope: {args.path_like}")
        print(f"Unknown ISRC candidates (not already referenced): {len(isrcs)}")
        print(f"Providers: {', '.join(providers_order)}")

        report_rows: list[Resolution] = []
        inserts = 0
        skipped = 0
        now_iso = datetime.now(timezone.utc).isoformat()

        for idx, isrc in enumerate(isrcs, start=1):
            durations: list[int] = []
            titles: list[str] = []
            checked = []

            for provider_name in providers_order:
                if provider_name == "beatport":
                    d, t = query_beatport_isrc(beatport, isrc)
                elif provider_name == "spotify":
                    d, t = query_spotify_isrc(spotify, isrc)
                elif provider_name == "tidal":
                    d, t = query_tidal_isrc(tidal, isrc)
                else:
                    continue

                checked.append(provider_name)
                durations.extend(d)
                titles.extend(t)
                if d:
                    # provider order is priority; stop at first provider with usable results
                    break

            local_samples = samples_by_isrc.get(isrc, [])
            local_paths = " | ".join(sample.path for sample in local_samples[:5])
            provider_titles = " | ".join(titles[:5])

            duration_ms, duration_state = choose_duration(durations, int(args.max_spread_ms))
            if duration_ms is None:
                report_rows.append(
                    Resolution(
                        isrc=isrc,
                        outcome="skip",
                        source="",
                        duration_ms=None,
                        providers_checked=",".join(checked),
                        provider_titles=provider_titles,
                        local_paths=local_paths,
                        notes=duration_state,
                    )
                )
                skipped += 1
                if idx % 100 == 0 or idx == len(isrcs):
                    print(f"[{idx}/{len(isrcs)}] inserted={inserts} skipped={skipped}")
                continue

            blocked, reason = variant_mismatch_guard(
                local_samples,
                titles,
                duration_ms,
                int(args.variant_guard_delta_ms),
            )
            if blocked:
                report_rows.append(
                    Resolution(
                        isrc=isrc,
                        outcome="skip",
                        source="",
                        duration_ms=duration_ms,
                        providers_checked=",".join(checked),
                        provider_titles=provider_titles,
                        local_paths=local_paths,
                        notes=reason,
                    )
                )
                skipped += 1
                if idx % 100 == 0 or idx == len(isrcs):
                    print(f"[{idx}/{len(isrcs)}] inserted={inserts} skipped={skipped}")
                continue

            report_rows.append(
                Resolution(
                    isrc=isrc,
                    outcome="insert",
                    source=args.source_label,
                    duration_ms=duration_ms,
                    providers_checked=",".join(checked),
                    provider_titles=provider_titles,
                    local_paths=local_paths,
                    notes="",
                )
            )

            if args.execute:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO track_duration_refs
                        (ref_id, ref_type, duration_ref_ms, ref_source, ref_updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (isrc, "isrc", duration_ms, args.source_label, now_iso),
                )
            inserts += 1

            if idx % 100 == 0 or idx == len(isrcs):
                print(f"[{idx}/{len(isrcs)}] inserted={inserts} skipped={skipped}")

        write_report(Path(report_path), report_rows)
        if args.execute:
            conn.commit()

        print("Done.")
        print(f"  Insert candidates: {inserts}")
        print(f"  Skipped:           {skipped}")
        print(f"  Report:            {report_path}")
        print(f"  Mode:              {'execute' if args.execute else 'dry-run'}")
        return 0
    finally:
        beatport.close()
        spotify.close()
        tidal.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
