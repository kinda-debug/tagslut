#!/usr/bin/env python3
"""Background post-move enrichment + cover-art embedding for exact file paths."""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.enricher import Enricher
from tagslut.exec.transcoder import sync_dj_mp3_from_flac


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run enrichment and cover-art embedding for exact promoted paths")
    ap.add_argument("--db", required=True, help="SQLite DB path")
    ap.add_argument("--paths-file", required=True, help="Text file with one absolute promoted path per line")
    ap.add_argument("--providers", default="beatport,tidal,deezer,traxsource,musicbrainz")
    ap.add_argument("--force", action="store_true", help="Force re-enrichment")
    ap.add_argument("--retry-no-match", action="store_true", help="Retry files previously marked no_match")
    ap.add_argument("--art-force", action="store_true", help="Force replace embedded cover art")
    ap.add_argument("--skip-art", action="store_true", help="Skip cover-art embedding after enrichment")
    ap.add_argument("--dj-map-file", help="Optional TSV map of promoted FLAC path to DJ MP3 path")
    return ap.parse_args()


def load_paths(paths_file: Path) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for raw_line in paths_file.read_text(encoding="utf-8").splitlines():
        raw = raw_line.strip()
        if not raw:
            continue
        path = Path(raw).expanduser().resolve()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            out.append(path)
    return out


def load_dj_pairs(dj_map_file: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    seen: set[tuple[str, str]] = set()
    for raw_line in dj_map_file.read_text(encoding="utf-8").splitlines():
        raw = raw_line.strip()
        if not raw:
            continue
        parts = raw.split("\t", 1)
        if len(parts) != 2:
            continue
        flac_path = Path(parts[0]).expanduser().resolve()
        mp3_path = Path(parts[1]).expanduser().resolve()
        key = (str(flac_path), str(mp3_path))
        if key in seen:
            continue
        seen.add(key)
        pairs.append((flac_path, mp3_path))
    return pairs


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).expanduser().resolve()
    paths_file = Path(args.paths_file).expanduser().resolve()
    dj_map_file = Path(args.dj_map_file).expanduser().resolve() if args.dj_map_file else None
    providers = [item.strip() for item in args.providers.split(",") if item.strip()]

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    if not paths_file.exists():
        raise SystemExit(f"Paths file not found: {paths_file}")

    file_paths = load_paths(paths_file)
    total = len(file_paths)
    print(f"Post-move enrichment start: files={total} db={db_path}")
    if not file_paths:
        print("No promoted files found in paths file; nothing to do.")
        return 0

    stats = {
        "total": total,
        "enriched": 0,
        "no_match": 0,
        "failed": 0,
        "not_found": 0,
        "not_eligible": 0,
        "not_flac_ok": 0,
    }

    token_manager = TokenManager()
    with Enricher(
        db_path=db_path,
        token_manager=token_manager,
        providers=providers,
        dry_run=False,
        mode="hoarding",
    ) as enricher:
        for idx, path in enumerate(file_paths, start=1):
            print(f"[{idx}/{total}] enrich {path}")
            try:
                _result, status = enricher.enrich_file(
                    str(path),
                    force=bool(args.force),
                    retry_no_match=bool(args.retry_no_match),
                )
            except Exception as exc:  # pragma: no cover - defensive for background worker
                stats["failed"] += 1
                print(f"ERROR: enrich failed for {path}: {exc}")
                continue

            if status in stats:
                stats[status] += 1
            elif status == "enriched":
                stats["enriched"] += 1
            else:
                print(f"WARNING: unexpected enrich status for {path}: {status}")

    print("Post-move enrichment summary:")
    for key in ("total", "enriched", "no_match", "not_eligible", "not_flac_ok", "not_found", "failed"):
        print(f"  {key}: {stats[key]}")

    exit_code = 0
    writeback_script = Path(__file__).resolve().with_name("write_canonical_tags_to_files.py")
    writeback_cmd = [
        sys.executable,
        str(writeback_script),
        "--db",
        str(db_path),
        "--m3u",
        str(paths_file),
        "--force",
        "--execute",
    ]
    print("$ " + " ".join(writeback_cmd))
    writeback_result = subprocess.run(writeback_cmd, check=False)
    if writeback_result.returncode != 0:
        print(f"WARNING: canonical tag writeback exited with code {writeback_result.returncode}")
        exit_code = writeback_result.returncode
    else:
        print("Post-move canonical tag writeback complete.")

    if args.skip_art:
        print("Skipping cover-art embedding by request.")
    else:
        embed_script = Path(__file__).resolve().with_name("embed_cover_art.py")
        embed_cmd = [
            sys.executable,
            str(embed_script),
            "--db",
            str(db_path),
            "--paths",
            str(paths_file),
            "--execute",
        ]
        if args.art_force:
            embed_cmd.append("--force")

        print("$ " + " ".join(embed_cmd))
        result = subprocess.run(embed_cmd, check=False)
        if result.returncode != 0:
            print(f"WARNING: cover-art embedding exited with code {result.returncode}")
            exit_code = result.returncode
        else:
            print("Post-move cover-art embedding complete.")

    if dj_map_file and dj_map_file.exists():
        pairs = load_dj_pairs(dj_map_file)
        print(f"Post-move DJ tag sync start: files={len(pairs)}")
        dj_stats = {"updated": 0, "missing": 0, "failed": 0}
        for idx, (flac_path, mp3_path) in enumerate(pairs, start=1):
            print(f"[{idx}/{len(pairs)}] dj-sync {mp3_path}")
            if not flac_path.is_file() or not mp3_path.is_file():
                dj_stats["missing"] += 1
                print(f"WARNING: missing DJ sync input: flac={flac_path} mp3={mp3_path}")
                continue
            try:
                sync_dj_mp3_from_flac(mp3_path, flac_path)
                dj_stats["updated"] += 1
            except Exception as exc:  # pragma: no cover - defensive for background worker
                dj_stats["failed"] += 1
                print(f"ERROR: dj-sync failed for {mp3_path}: {exc}")
        print("Post-move DJ tag sync summary:")
        for key in ("updated", "missing", "failed"):
            print(f"  {key}: {dj_stats[key]}")
        if dj_stats["failed"] and exit_code == 0:
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
