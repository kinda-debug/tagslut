#!/usr/bin/env python3
"""Background post-move enrichment + cover-art embedding for exact file paths."""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.enricher import Enricher
from tagslut.exec.canonical_writeback import write_canonical_tags

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run enrichment and cover-art embedding for exact promoted paths")
    ap.add_argument("--db", required=True, help="SQLite DB path")
    ap.add_argument("--paths-file", required=True, help="Text file with one absolute promoted path per line")
    ap.add_argument("--intake-context", default=None, help="Optional intake acquisition manifest")
    ap.add_argument("--providers", default="beatport,tidal,deezer,traxsource,musicbrainz")
    ap.add_argument("--force", action="store_true", help="Force re-enrichment")
    ap.add_argument("--retry-no-match", action="store_true", help="Retry files previously marked no_match")
    ap.add_argument("--art-force", action="store_true", help="Force replace embedded cover art")
    ap.add_argument("--skip-art", action="store_true", help="Skip cover-art embedding after enrichment")
    ap.add_argument("--writeback-force", action="store_true", help="Force overwrite canonical FLAC tags")
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


def load_intake_context(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    records = payload.get("records")
    if not isinstance(records, list):
        overrides = payload.get("provenance_overrides")
        if isinstance(overrides, dict):
            return payload
        return {}

    by_spotify_id: dict[str, dict[str, object]] = {}
    by_isrc: dict[str, dict[str, object]] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").strip().lower() != "downloaded":
            continue
        spotify_id = str(item.get("spotify_id") or "").strip()
        isrc = str(item.get("isrc") or "").strip()
        if spotify_id and spotify_id not in by_spotify_id:
            by_spotify_id[spotify_id] = item
        if isrc and isrc not in by_isrc:
            by_isrc[isrc] = item
    payload["records_by_spotify_id"] = by_spotify_id
    payload["records_by_isrc"] = by_isrc
    return payload


def _normalize_tag_map(tags: object) -> dict[str, object]:
    items = getattr(tags, "items", None)
    if not callable(items):
        return {}
    return {str(key).lower(): value for key, value in items()}


def _first_tag(tag_map: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = tag_map.get(key.lower())
        if isinstance(value, list):
            for item in value:
                text = str(item).strip()
                if text:
                    return text
        elif value is not None:
            text = str(value).strip()
            if text:
                return text
    return None


def _lookup_spotify_record(
    intake_context: dict[str, object],
    *,
    spotify_id: str | None,
    isrc: str | None,
) -> dict[str, object] | None:
    by_spotify_id = intake_context.get("records_by_spotify_id")
    if spotify_id and isinstance(by_spotify_id, dict):
        record = by_spotify_id.get(spotify_id)
        if isinstance(record, dict):
            return record
    by_isrc = intake_context.get("records_by_isrc")
    if isrc and isinstance(by_isrc, dict):
        record = by_isrc.get(isrc)
        if isinstance(record, dict):
            return record
    return None


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).expanduser().resolve()
    paths_file = Path(args.paths_file).expanduser().resolve()
    intake_context_path = Path(args.intake_context).expanduser().resolve() if args.intake_context else None
    providers = [item.strip() for item in args.providers.split(",") if item.strip()]

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    if not paths_file.exists():
        raise SystemExit(f"Paths file not found: {paths_file}")

    file_paths = load_paths(paths_file)
    intake_context = load_intake_context(intake_context_path)
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
    try:
        with sqlite3.connect(str(db_path)) as writeback_conn:
            stats = write_canonical_tags(
                writeback_conn,
                file_paths,
                force=bool(args.writeback_force),
                execute=True,
                echo=print,
            )
        print(
            "Post-move canonical tag writeback complete: "
            f"updated={stats.updated} skipped={stats.skipped} missing={stats.missing}"
        )
    except Exception as exc:  # pragma: no cover - defensive for background worker
        print(f"WARNING: canonical tag writeback failed: {exc}")
        exit_code = 1

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

    # Register promoted files into v3 schema (asset_file + track_identity) via dual_write.
    # Reads embedded FLAC tags (ISRC, artist, title, BPM) and calls dual_write_registered_file()
    # per file. No-op for files already registered. Safe to run on every intake.
    try:
        from tagslut.storage.v3.dual_write import dual_write_enabled, dual_write_registered_file
        if dual_write_enabled():
            try:
                from mutagen.flac import FLAC as MutagenFLAC
            except ImportError:
                MutagenFLAC = None
            if MutagenFLAC is None:
                print("WARNING: mutagen not available; skipping v3 dual-write register")
            else:
                registered = 0
                with sqlite3.connect(str(db_path)) as dw_conn:
                    dw_conn.row_factory = sqlite3.Row
                    dw_conn.execute("PRAGMA foreign_keys=ON")
                    for path in file_paths:
                        if not path.exists() or path.suffix.lower() != ".flac":
                            continue
                        try:
                            tags = MutagenFLAC(str(path))
                            tag_map = _normalize_tag_map(tags)
                            metadata = {
                                "isrc": _first_tag(tag_map, "isrc", "tsrc"),
                                "artist": _first_tag(tag_map, "artist", "albumartist"),
                                "title": _first_tag(tag_map, "title"),
                                "album": _first_tag(tag_map, "album"),
                                "bpm": _first_tag(tag_map, "bpm", "tempo"),
                                "spotify_id": _first_tag(tag_map, "spotify_id"),
                            }
                            spotify_record = _lookup_spotify_record(
                                intake_context,
                                spotify_id=metadata["spotify_id"],
                                isrc=metadata["isrc"],
                            )
                            download_source_override = None
                            ingestion_method_override = None
                            ingestion_source_override = None
                            ingestion_confidence_override = None
                            provider_id_hints = None
                            duration_ref_source = "tidal"
                            provenance_overrides = intake_context.get("provenance_overrides")
                            if isinstance(provenance_overrides, dict):
                                method = str(provenance_overrides.get("ingestion_method") or "").strip()
                                source = str(provenance_overrides.get("ingestion_source") or "").strip()
                                confidence = str(provenance_overrides.get("ingestion_confidence") or "").strip()
                                if method:
                                    ingestion_method_override = method
                                if source:
                                    ingestion_source_override = source
                                if confidence:
                                    ingestion_confidence_override = confidence
                            if spotify_record is not None:
                                service = str(spotify_record.get("service") or "").strip().lower()
                                spotify_url = str(
                                    spotify_record.get("spotify_url")
                                    or intake_context.get("source_url")
                                    or ""
                                ).strip()
                                provider_track_id = str(spotify_record.get("provider_track_id") or "").strip()
                                download_source_override = f"spotiflac_{service}" if service else "spotiflac"
                                ingestion_method_override = "spotify_intake"
                                if spotify_url:
                                    ingestion_source_override = (
                                        f"spotiflac:{spotify_url}|service:{service}"
                                        if service
                                        else f"spotiflac:{spotify_url}"
                                    )
                                ingestion_confidence_override = "high"
                                duration_ref_source = "spotify"
                                provider_id_hints = {
                                    "spotify_id": metadata["spotify_id"] or spotify_record.get("spotify_id"),
                                    "isrc": metadata["isrc"] or spotify_record.get("isrc"),
                                }
                                if service == "tidal" and provider_track_id:
                                    provider_id_hints["tidal_id"] = provider_track_id
                                elif service == "qobuz" and provider_track_id:
                                    provider_id_hints["qobuz_id"] = provider_track_id
                            stat = path.stat()
                            dual_write_registered_file(
                                dw_conn,
                                path=str(path),
                                content_sha256=None, streaminfo_md5=None, checksum=None,
                                size_bytes=stat.st_size, mtime=stat.st_mtime,
                                duration_s=tags.info.length if tags.info else None,
                                sample_rate=tags.info.sample_rate if tags.info else None,
                                bit_depth=tags.info.bits_per_sample if tags.info else None,
                                bitrate=int(tags.info.bitrate) if tags.info else None,
                                library="MASTER_LIBRARY", zone="accepted",
                                download_source="tidal", download_date=None,
                                mgmt_status="promoted_to_final_library",
                                metadata=metadata,
                                duration_ref_ms=int(tags.info.length*1000) if tags.info else None,
                                duration_ref_source=duration_ref_source,
                                download_source_override=download_source_override,
                                ingestion_method_override=ingestion_method_override,
                                ingestion_source_override=ingestion_source_override,
                                ingestion_confidence_override=ingestion_confidence_override,
                                provider_id_hints=provider_id_hints,
                            )
                            registered += 1
                        except Exception as e:
                            print(f"WARNING: dual_write failed for {path}: {e}")
                    dw_conn.commit()
                print(f"V3 dual-write register: {registered}/{len(file_paths)} file(s)")
        else:
            print("V3 dual-write disabled (set dual_write=true in ~/.config/tagslut/config.toml)")
    except Exception as exc:
        print(f"WARNING: v3 dual-write register failed: {exc}")

    # Refresh v3 identity status and preferred assets so DJ views stay current.
    try:
        from tagslut.storage.v3.identity_status import compute_identity_statuses, upsert_identity_statuses
        from tagslut.storage.v3.preferred_asset import compute_preferred_assets, upsert_preferred_assets
        with sqlite3.connect(str(db_path)) as v3_conn:
            v3_conn.row_factory = sqlite3.Row
            v3_conn.execute("PRAGMA foreign_keys=ON")
            statuses = compute_identity_statuses(v3_conn)
            upsert_identity_statuses(v3_conn, statuses, version=1)
            preferred = compute_preferred_assets(v3_conn)
            upsert_preferred_assets(v3_conn, preferred, version=1)
            active = v3_conn.execute("SELECT COUNT(*) FROM identity_status WHERE status='active'").fetchone()[0]
            pref = v3_conn.execute("SELECT COUNT(*) FROM preferred_asset").fetchone()[0]
            print(f"V3 status refresh: {active} active identities, {pref} preferred assets")
    except Exception as exc:
        print(f"WARNING: v3 status/preferred refresh failed: {exc}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
