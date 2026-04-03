#!/usr/bin/env python3
"""Pre-download DB check for Beatport/Tidal/Spotify links.

Flow:
1) Extract tracklists from links (using scripts/extract_tracklists_from_links.py)
2) Check each track against already-downloaded source records (asset_file/track_identity)
3) Match remaining candidates against the files table (quality-rank comparison)
4) Emit per-track decisions and keep-URL list for download tools

Match strategy (in priority order):
Phase 1 — previously-downloaded source match (skips re-download regardless of quality):
  - provider + track_id match in track_identity (beatport_id / tidal_id / spotify_id)
  - ISRC match in track_identity with an associated asset_file

Phase 2 — canonical/final-library quality-rank match (skips if equal-or-better exists):
  - ISRC match in files (confidence: high)
  - Beatport track ID match in files (confidence: high, Beatport only)
  - Tidal track ID match in files (confidence: high, Tidal only)
  - Spotify track ID match in files (confidence: high, Spotify only)
  - Normalized title + artist + album (confidence: medium)
  - Normalized title + artist (confidence: low)

Usage:
    python tools/review/pre_download_check.py \\
        --input ~/links.txt \\
        --db /path/to/music.db \\
        --out-dir output/precheck

Outputs:
- precheck_decisions_<ts>.csv: Per-track keep/skip with confidence
- precheck_summary_<ts>.csv: Per-link statistics
- precheck_keep_track_urls_<ts>.txt: URLs for downloader feed
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tagslut.core.quality import compute_quality_rank, is_upgrade
from tagslut.metadata.auth import TokenManager
from tagslut.metadata.models.types import ProviderTrack
from tagslut.metadata.providers.tidal import TidalProvider
from tagslut.metadata.source_selection import (
    SourceSelectionDecision,
    select_download_source_for_beatport_track,
    tidal_audio_quality_rank as _tidal_audio_quality_rank,
)
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

# Confidence levels for match methods
CONFIDENCE_LEVELS = {
    "isrc": "high",
    "beatport_id": "high",
    "tidal_id": "high",
    "spotify_id": "high",
    "exact_title_artist_album": "medium",
    "exact_title_artist": "low",
}


def _scan_existing_root_isrc(existing_root: Path) -> dict[str, str]:
    """Best-effort scan of an existing staging root for ISRCs.

    Used for resume workflows when the DB may not yet contain partially-downloaded
    files (interrupted runs). Conservative: only ISRC-based presence is used.
    """
    try:
        import mutagen  # type: ignore
    except Exception:
        return {}

    def _extract_isrc(tags: Any) -> str:
        if tags is None:
            return ""
        try:
            items = tags.items()  # type: ignore[attr-defined]
        except Exception:
            try:
                items = ((k, tags[k]) for k in tags.keys())  # type: ignore
            except Exception:
                return ""

        for k, v in items:
            key = str(k).strip().lower()
            if key in {"isrc", "tsrc"} or key.endswith(":isrc") or key.endswith("/isrc"):
                if isinstance(v, (list, tuple)) and v:
                    val = str(v[0]).strip()
                else:
                    val = str(v).strip()
                if val:
                    return val
        return ""

    out: dict[str, str] = {}
    if not existing_root.exists() or not existing_root.is_dir():
        return out

    exts = {".flac", ".wav", ".aif", ".aiff", ".mp3", ".m4a", ".mp4"}
    for path in existing_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in exts:
            continue
        try:
            audio = mutagen.File(str(path), easy=False)
        except Exception:
            continue
        tags = getattr(audio, "tags", None) if audio is not None else None
        isrc = _extract_isrc(tags).strip()
        if isrc and isrc not in out:
            out[isrc] = str(path)
    return out


@dataclass
class DbRow:
    path: str
    isrc: str
    beatport_id: str
    tidal_id: str
    spotify_id: str
    title: str
    artist: str
    album: str
    download_source: str
    quality_rank: int | None


def norm_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().lower().split())


def parse_json(s: str | None) -> dict[str, Any]:
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        return {}


def first_meta(meta: dict[str, Any], keys: list[str]) -> str:
    for k in keys:
        v = meta.get(k)
        if isinstance(v, list) and v:
            val = str(v[0]).strip()
            if val:
                return val
        elif v is not None:
            val = str(v).strip()
            if val:
                return val
    return ""


def infer_quality_rank(
    *,
    path: str,
    quality_rank: int | None,
    bit_depth: int | None,
    sample_rate: int | None,
    bitrate: int | None,
) -> int | None:
    if quality_rank is not None:
        return int(quality_rank)

    bitrate_value = int(bitrate) if bitrate is not None else None
    suffix = Path(path).suffix.lower()
    if suffix in {".flac", ".wav", ".aif", ".aiff"}:
        bitrate_value = 0

    if bit_depth is not None and sample_rate is not None:
        try:
            return int(
                compute_quality_rank(
                    int(bit_depth),
                    int(sample_rate),
                    int(bitrate_value or 0),
                )
            )
        except (TypeError, ValueError):
            return None

    if bitrate_value is not None:
        return 6 if int(bitrate_value) >= 320000 else 7

    return None


# ---------------------------------------------------------------------------
# Phase 1 — previously-downloaded source lookup
# ---------------------------------------------------------------------------

def load_downloaded_track_ids(
    db_path: Path,
) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    """Return dicts mapping previously-downloaded provider IDs to a representative path.

    Queries track_identity joined with asset_link + asset_file to find every
    identity that has at least one registered asset file in the DB — regardless
    of whether that file was promoted, stashed, or is still in staging.

    Returns:
        by_beatport_id  — beatport_id  → asset_file.path
        by_tidal_id     — tidal_id     → asset_file.path
        by_spotify_id   — spotify_id   → asset_file.path
        by_isrc         — isrc         → asset_file.path
    """
    by_beatport_id: dict[str, str] = {}
    by_tidal_id: dict[str, str] = {}
    by_spotify_id: dict[str, str] = {}
    by_isrc: dict[str, str] = {}

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                ti.beatport_id,
                ti.tidal_id,
                ti.spotify_id,
                ti.isrc,
                af.path
            FROM track_identity ti
            INNER JOIN asset_link al
                    ON al.identity_id = ti.id
                   AND (al.active IS NULL OR al.active = 1)
            INNER JOIN asset_file af ON af.id = al.asset_id
            WHERE (ti.beatport_id IS NOT NULL AND ti.beatport_id != '')
               OR (ti.tidal_id   IS NOT NULL AND ti.tidal_id   != '')
               OR (ti.spotify_id IS NOT NULL AND ti.spotify_id != '')
               OR (ti.isrc       IS NOT NULL AND ti.isrc       != '')
            ORDER BY al.confidence DESC, al.id ASC
            """
        ).fetchall()
        conn.close()
    except sqlite3.OperationalError:
        # track_identity / asset_link / asset_file tables may not exist on old DBs.
        return by_beatport_id, by_tidal_id, by_spotify_id, by_isrc

    for r in rows:
        bp_id = (r["beatport_id"] or "").strip()
        td_id = (r["tidal_id"] or "").strip()
        sp_id = (r["spotify_id"] or "").strip()
        isrc  = (r["isrc"] or "").strip()
        path  = r["path"] or ""
        # First row per identity (highest confidence) wins; subsequent rows ignored.
        if bp_id and bp_id not in by_beatport_id:
            by_beatport_id[bp_id] = path
        if td_id and td_id not in by_tidal_id:
            by_tidal_id[td_id] = path
        if sp_id and sp_id not in by_spotify_id:
            by_spotify_id[sp_id] = path
        if isrc and isrc not in by_isrc:
            by_isrc[isrc] = path

    return by_beatport_id, by_tidal_id, by_spotify_id, by_isrc


# ---------------------------------------------------------------------------
# Phase 2 — files-table quality-rank lookup
# ---------------------------------------------------------------------------

def load_db_rows(
    db_path: Path,
) -> tuple[
    dict[str, list[DbRow]],
    dict[str, list[DbRow]],
    dict[str, list[DbRow]],
    dict[str, list[DbRow]],
    dict[str, list[DbRow]],
    dict[str, list[DbRow]],
]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    by_isrc: dict[str, list[DbRow]] = defaultdict(list)
    by_beatport: dict[str, list[DbRow]] = defaultdict(list)
    by_tidal: dict[str, list[DbRow]] = defaultdict(list)
    by_spotify: dict[str, list[DbRow]] = defaultdict(list)
    by_exact3: dict[str, list[DbRow]] = defaultdict(list)
    by_exact2: dict[str, list[DbRow]] = defaultdict(list)

    try:
        cur.execute(
            """
            SELECT
                af.path,
                ti.isrc                 AS canonical_isrc,
                ti.beatport_id,
                ti.tidal_id,
                ti.spotify_id,
                ti.canonical_title,
                ti.canonical_artist,
                ti.canonical_album,
                af.bit_depth,
                af.sample_rate,
                af.bitrate,
                af.download_source,
                NULL                    AS metadata_json,
                NULL                    AS quality_rank
            FROM asset_file af
            JOIN asset_link al ON al.asset_id = af.id AND al.active = 1
            JOIN track_identity ti
                ON ti.id = al.identity_id
                AND ti.merged_into_id IS NULL
            """
        )
    except sqlite3.OperationalError:
        try:
            cur.execute(
                """
                SELECT
                    path,
                    canonical_isrc,
                    beatport_id,
                    tidal_id,
                    spotify_id,
                    canonical_title,
                    canonical_artist,
                    canonical_album,
                    bit_depth,
                    sample_rate,
                    bitrate,
                    metadata_json,
                    download_source,
                    quality_rank
                FROM files
                """
            )
        except sqlite3.OperationalError:
            conn.close()
            return by_isrc, by_beatport, by_tidal, by_spotify, by_exact3, by_exact2

    for r in cur.fetchall():
        meta = parse_json(r["metadata_json"])

        isrc = (r["canonical_isrc"] or first_meta(meta, ["isrc", "ISRC", "TSRC"])).strip()
        beatport_id = (str(r["beatport_id"]) if r["beatport_id"] else first_meta(meta, ["beatport_id", "beatport_track_id", "BP_TRACK_ID"]))
        tidal_id = (str(r["tidal_id"]) if r["tidal_id"] else first_meta(meta, ["tidal_id", "tidal_track_id", "TD_TRACK_ID"]))
        spotify_id = (str(r["spotify_id"]) if r["spotify_id"] else first_meta(meta, ["spotify_id", "spotify_track_id", "SPOTIFY_ID"]))
        title = (r["canonical_title"] or first_meta(meta, ["title", "TITLE", "track_title", "name"])).strip()
        artist = (r["canonical_artist"] or first_meta(meta, ["artist", "ARTIST", "albumartist", "ALBUMARTIST"])).strip()
        album = (r["canonical_album"] or first_meta(meta, ["album", "ALBUM", "release"])).strip()

        row = DbRow(
            path=r["path"],
            isrc=isrc,
            beatport_id=str(beatport_id).strip(),
            tidal_id=str(tidal_id).strip(),
            spotify_id=str(spotify_id).strip(),
            title=title,
            artist=artist,
            album=album,
            download_source=(r["download_source"] or "").strip(),
            quality_rank=infer_quality_rank(
                path=r["path"],
                quality_rank=int(r["quality_rank"]) if r["quality_rank"] is not None else None,
                bit_depth=int(r["bit_depth"]) if r["bit_depth"] is not None else None,
                sample_rate=int(r["sample_rate"]) if r["sample_rate"] is not None else None,
                bitrate=int(r["bitrate"]) if r["bitrate"] is not None else None,
            ),
        )

        if row.isrc:
            by_isrc[row.isrc].append(row)
        if row.beatport_id:
            by_beatport[row.beatport_id].append(row)
        if row.tidal_id:
            by_tidal[row.tidal_id].append(row)
        if row.spotify_id:
            by_spotify[row.spotify_id].append(row)

        k3 = "|".join([norm_text(row.title), norm_text(row.artist), norm_text(row.album)])
        if k3.strip("|"):
            by_exact3[k3].append(row)

        k2 = "|".join([norm_text(row.title), norm_text(row.artist)])
        if k2.strip("|"):
            by_exact2[k2].append(row)

    conn.close()
    return by_isrc, by_beatport, by_tidal, by_spotify, by_exact3, by_exact2


def build_keep_track_url(domain: str, track_id: str) -> str:
    tid = (track_id or "").strip()
    if not tid:
        return ""
    if domain == "beatport":
        return f"https://www.beatport.com/track/-/{tid}"
    if domain == "tidal":
        return f"https://tidal.com/browse/track/{tid}"
    if domain == "spotify":
        return f"https://open.spotify.com/track/{tid}"
    return ""


def choose_best_match(matches: list[DbRow]) -> DbRow:
    return sorted(
        matches,
        key=lambda row: (
            row.quality_rank is None,
            row.quality_rank if row.quality_rank is not None else 999,
            row.path,
        ),
    )[0]


def decide_match_action(
    matched: DbRow | None,
    *,
    match_method: str,
    candidate_quality_rank: int,
    force_keep_matched: bool,
) -> tuple[str, str]:
    if matched is None:
        return "keep", "no inventory match"
    if force_keep_matched:
        return "keep", f"forced download despite {match_method} match"
    if matched.quality_rank is None:
        return "keep", f"matched by {match_method}; existing quality rank missing"
    if is_upgrade(current_rank=matched.quality_rank, candidate_rank=candidate_quality_rank):
        return (
            "keep",
            f"matched by {match_method}; candidate rank {candidate_quality_rank} improves existing rank {matched.quality_rank}",
        )
    return (
        "skip",
        f"matched by {match_method}; existing rank {matched.quality_rank} is equal or better than candidate rank {candidate_quality_rank}",
    )


def get_repo_root() -> Path:
    """Get repository root by finding the directory containing pyproject.toml."""
    current = Path(__file__).resolve().parent
    for _ in range(10):  # Max 10 levels up
        if (current / "pyproject.toml").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    # Fallback to environment variable if set
    env_root = os.environ.get("TAGSLUT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    raise SystemExit("Could not find repository root (pyproject.toml)")


def main() -> int:
    repo_root = get_repo_root()
    default_extract_script = repo_root / "scripts" / "extract_tracklists_from_links.py"

    ap = argparse.ArgumentParser(
        description="Check Beatport/Tidal/Spotify links against DB before download",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/review/pre_download_check.py --input ~/links.txt --db ~/db/music.db
  python tools/review/pre_download_check.py --input ~/links.txt --db ~/db/music.db --out-dir output/precheck

Match Methods (in priority order):
  Phase 1 — previously-downloaded source check (short-circuits Phase 2):
    1. beatport_id / tidal_id in track_identity + asset_file
    2. ISRC in track_identity + asset_file

  Phase 2 — canonical/quality-rank check against files table:
    3. ISRC match (confidence: high)
    4. Beatport track ID match (confidence: high, Beatport links only)
    5. Title + Artist + Album exact match (confidence: medium)
    6. Title + Artist exact match (confidence: low)
""",
    )
    ap.add_argument("input_arg", nargs="?", help="Text file or single URL (positional)")
    ap.add_argument("--input", help="Text file with links (one URL per line)")
    ap.add_argument(
        "--db",
        help="Path to music.db (or set TAGSLUT_DB env var)",
    )
    ap.add_argument(
        "--candidate-quality-rank",
        type=int,
        default=3,
        help="Incoming file quality rank (default: 3 = fresh hi-res FLAC)",
    )
    ap.add_argument(
        "--force-keep-matched",
        action="store_true",
        help="Keep matched URLs instead of skipping them (bypasses both Phase 1 and Phase 2 skip decisions)",
    )
    ap.add_argument("--out-dir", default="output/precheck", help="Output directory (default: output/precheck)")
    ap.add_argument("--quiet", action="store_true", help="Suppress progress/output details; emit files only")
    ap.add_argument(
        "--existing-root",
        help="Resume hint: scan an existing staging root for ISRCs to avoid re-downownloading partial runs",
    )
    ap.add_argument(
        "--extract-script",
        default=str(default_extract_script),
        help="Path to extract_tracklists_from_links.py (auto-detected from repo root)",
    )
    args = ap.parse_args()

    input_val = args.input or args.input_arg
    if not input_val:
        raise SystemExit("--input is required (file path or single URL)")

    if input_val.startswith("http://") or input_val.startswith("https://"):
        tmp = Path("artifacts/precheck_urls.txt")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(input_val + "\n", encoding="utf-8")
        input_path = tmp
    else:
        input_path = Path(input_val).expanduser().resolve()
    try:
        db_resolution = resolve_cli_env_db_path(args.db, purpose="read", source_label="--db")
    except DbResolutionError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    db_path = db_resolution.path
    if not args.quiet:
        print(f"Resolved DB path: {db_path}")
    out_dir = Path(args.out_dir).expanduser().resolve()
    extract_script = Path(args.extract_script).expanduser().resolve()
    existing_root = Path(args.existing_root).expanduser().resolve() if args.existing_root else None

    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")
    if not extract_script.exists():
        raise SystemExit(f"Extract script not found: {extract_script}\n(Tip: Run from repository root or set --extract-script)")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    tracks_csv = out_dir / f"precheck_tracks_extracted_{ts}.csv"
    summary_csv = out_dir / f"precheck_links_extracted_{ts}.csv"
    report_md = out_dir / f"precheck_extracted_report_{ts}.md"

    cmd = [
        "python3",
        str(extract_script),
        "--input",
        str(input_path),
        "--tracks-csv",
        str(tracks_csv),
        "--summary-csv",
        str(summary_csv),
        "--report-md",
        str(report_md),
    ]
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    pythonpath_parts = [str(repo_root)]
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    try:
        if args.quiet:
            subprocess.run(cmd, check=True, env=env, capture_output=True, text=True)
        else:
            subprocess.run(cmd, check=True, env=env)
    except subprocess.CalledProcessError as exc:
        if args.quiet:
            output = "\n".join(part for part in [(exc.stdout or "").strip(), (exc.stderr or "").strip()] if part)
            if output:
                raise SystemExit(output) from exc
        raise

    # ── Phase 1: load previously-downloaded source IDs from track_identity ──
    # These are tracks the DB already knows about via the new-schema tables
    # (asset_file / asset_link / track_identity), regardless of whether the
    # downloaded file was later promoted, stashed, or is still in staging.
    ti_by_beatport, ti_by_tidal, ti_by_spotify, ti_by_isrc = load_downloaded_track_ids(db_path)

    # ── Phase 2: load files-table rows for quality-rank comparison ───────────
    by_isrc, by_beatport, by_tidal, by_spotify, by_exact3, by_exact2 = load_db_rows(db_path)

    existing_isrc_to_path: dict[str, str] = {}
    if existing_root is not None and not args.force_keep_matched:
        existing_isrc_to_path = _scan_existing_root_isrc(existing_root)

    decision_csv = out_dir / f"precheck_decisions_{ts}.csv"
    decision_summary_csv = out_dir / f"precheck_summary_{ts}.csv"
    keep_urls_txt = out_dir / f"precheck_keep_track_urls_{ts}.txt"

    link_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"keep": 0, "skip": 0})
    keep_urls: list[str] = []
    selection_stats = {
        "attempted": 0,
        "selected_tidal": 0,
        "retained_beatport": 0,
        "ambiguous": 0,
        "unverified": 0,
        "not_better": 0,
        "unavailable": 0,
    }

    token_manager: TokenManager | None = None
    tidal_provider: TidalProvider | None = None

    def _parse_int(value: str | None) -> int | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(text)
        except Exception:
            return None

    with tracks_csv.open("r", encoding="utf-8", newline="") as fin, decision_csv.open("w", encoding="utf-8", newline="") as fout:
        reader = csv.DictReader(fin)
        fields = list(reader.fieldnames or []) + [
            "decision",
            "confidence",
            "match_method",
            "reason",
            "db_path",
            "db_download_source",
            "existing_quality_rank",
            "candidate_quality_rank",
            "source_selection_attempted",
            "source_selection_winner",
            "source_selection_reason",
            "tidal_match_method",
            "tidal_track_id",
            "tidal_audio_quality",
            "tidal_audio_quality_rank",
            "duration_diff_ms",
        ]
        writer = csv.DictWriter(fout, fieldnames=fields)
        writer.writeheader()

        for row in reader:
            domain = (row.get("domain") or "").strip()
            source_link = (row.get("source_link") or "").strip()
            isrc = (row.get("isrc") or "").strip()
            track_id = (row.get("track_id") or "").strip()
            title = (row.get("title") or "").strip()
            artist = (row.get("artist") or "").strip()
            album = (row.get("album") or "").strip()

            source_selection_attempted = ""
            source_selection_winner = ""
            source_selection_reason = ""
            tidal_match_method = ""
            tidal_track_id = ""
            tidal_audio_quality = ""
            tidal_audio_quality_rank_str = ""
            duration_diff_ms = ""

            decision: str
            reason: str
            confidence: str
            db_path_val: str
            db_source: str
            existing_quality_rank: int | str
            method: str

            # ── Phase 1: previously-downloaded source match ───────────────
            #
            # Short-circuits Phase 2.  Checks whether a prior run already
            # fetched this exact upstream item and registered it in the DB
            # via asset_file/asset_link/track_identity — even if that run
            # later stashed the file instead of promoting it.
            #
            # Priority: provider track_id (beatport/tidal) > ISRC
            # Bypassed when --force-keep-matched is set.

            phase1_asset_path: str | None = None
            phase1_match_kind: str | None = None

            if not args.force_keep_matched:
                if isrc and isrc in existing_isrc_to_path:
                    phase1_asset_path = existing_isrc_to_path[isrc]
                    phase1_match_kind = "existing_root_isrc"
                if domain == "beatport" and track_id and track_id in ti_by_beatport:
                    phase1_asset_path = ti_by_beatport[track_id]
                    phase1_match_kind = "beatport_id"
                elif domain == "tidal" and track_id and track_id in ti_by_tidal:
                    phase1_asset_path = ti_by_tidal[track_id]
                    phase1_match_kind = "tidal_id"
                elif domain == "spotify" and track_id and track_id in ti_by_spotify:
                    phase1_asset_path = ti_by_spotify[track_id]
                    phase1_match_kind = "spotify_id"
                elif isrc and isrc in ti_by_isrc:
                    phase1_asset_path = ti_by_isrc[isrc]
                    phase1_match_kind = "isrc"

            if phase1_match_kind is not None:
                decision = "skip"
                if phase1_match_kind == "existing_root_isrc":
                    reason = "resume_root_isrc_match"
                    confidence = "high"
                    method = "isrc"
                    db_source = "existing_root"
                else:
                    reason = f"already_downloaded_source_match:{phase1_match_kind}"
                    confidence = "high"
                    method = phase1_match_kind
                    db_source = "asset_file"
                db_path_val = phase1_asset_path or ""
                existing_quality_rank = ""

            else:
                # ── Phase 2: canonical/files-table quality-rank match ─────────
                matched: DbRow | None = None
                method = ""

                if isrc and isrc in by_isrc:
                    matched = choose_best_match(by_isrc[isrc])
                    method = "isrc"
                elif domain == "beatport" and track_id and track_id in by_beatport:
                    matched = choose_best_match(by_beatport[track_id])
                    method = "beatport_id"
                elif domain == "tidal" and track_id and track_id in by_tidal:
                    matched = choose_best_match(by_tidal[track_id])
                    method = "tidal_id"
                elif domain == "spotify" and track_id and track_id in by_spotify:
                    matched = choose_best_match(by_spotify[track_id])
                    method = "spotify_id"
                else:
                    k3 = "|".join([norm_text(title), norm_text(artist), norm_text(album)])
                    if k3 in by_exact3:
                        matched = choose_best_match(by_exact3[k3])
                        method = "exact_title_artist_album"
                    else:
                        k2 = "|".join([norm_text(title), norm_text(artist)])
                        if k2 in by_exact2:
                            matched = choose_best_match(by_exact2[k2])
                            method = "exact_title_artist"

                decision, reason = decide_match_action(
                    matched,
                    match_method=method or "unknown",
                    candidate_quality_rank=int(args.candidate_quality_rank),
                    force_keep_matched=bool(args.force_keep_matched),
                )
                if matched:
                    confidence = CONFIDENCE_LEVELS.get(method, "unknown")
                    db_path_val = matched.path
                    db_source = matched.download_source
                    existing_quality_rank = matched.quality_rank if matched.quality_rank is not None else ""
                else:
                    confidence = ""
                    db_path_val = ""
                    db_source = ""
                    existing_quality_rank = ""

            if decision == "keep":
                keep_url = build_keep_track_url(domain, track_id)

                # Beatport-origin upgrade: attempt strict TIDAL verification and
                # switch download source only for verified better-quality matches.
                if domain == "beatport" and track_id:
                    selection_stats["attempted"] += 1
                    source_selection_attempted = "1"

                    beatport_duration_ms = _parse_int(row.get("duration_ms"))
                    tidal_candidates: list[ProviderTrack] = []

                    try:
                        if token_manager is None:
                            token_manager = TokenManager()
                        if tidal_provider is None:
                            tidal_provider = TidalProvider(token_manager)

                        if isrc:
                            tidal_candidates = tidal_provider.search_by_isrc(isrc, limit=5)
                        else:
                            tidal_candidates = tidal_provider.search(f"{artist} {title}", limit=10)

                        decision_obj: SourceSelectionDecision = select_download_source_for_beatport_track(
                            beatport_track_id=track_id,
                            beatport_isrc=isrc or None,
                            beatport_title=title,
                            beatport_artist=artist,
                            beatport_album=album or None,
                            beatport_duration_ms=beatport_duration_ms,
                            tidal_candidates=tidal_candidates,
                        )

                        source_selection_winner = decision_obj.winner
                        source_selection_reason = decision_obj.winner_reason
                        if decision_obj.ambiguous:
                            selection_stats["ambiguous"] += 1
                        if decision_obj.winner == "tidal":
                            selection_stats["selected_tidal"] += 1
                        else:
                            selection_stats["retained_beatport"] += 1

                        if decision_obj.winner_reason in (
                            "tidal_unverified",
                            "no_tidal_candidates",
                        ):
                            selection_stats["unverified"] += 1
                        if decision_obj.winner_reason == "tidal_not_better_quality":
                            selection_stats["not_better"] += 1

                        if decision_obj.tidal_match is not None:
                            tidal_match_method = decision_obj.tidal_match.match_method
                            tidal_track_id = decision_obj.tidal_match.tidal_track.service_track_id
                            tidal_audio_quality = decision_obj.tidal_match.tidal_track.audio_quality or ""
                            tidal_audio_quality_rank_str = str(_tidal_audio_quality_rank(tidal_audio_quality))
                            if decision_obj.tidal_match.duration_diff_ms is not None:
                                duration_diff_ms = str(int(decision_obj.tidal_match.duration_diff_ms))

                        keep_url = decision_obj.selected_download_url(beatport_track_id=track_id)

                    except Exception as exc:
                        selection_stats["unavailable"] += 1
                        source_selection_winner = "beatport"
                        source_selection_reason = f"tidal_match_unavailable:{type(exc).__name__}"
                        keep_url = build_keep_track_url("beatport", track_id)

                if keep_url:
                    keep_urls.append(keep_url)

            row.update(
                {
                    "decision": decision,
                    "confidence": confidence,
                    "match_method": method,
                    "reason": reason,
                    "db_path": db_path_val,
                    "db_download_source": db_source,
                    "existing_quality_rank": existing_quality_rank,
                    "candidate_quality_rank": int(args.candidate_quality_rank),
                    "source_selection_attempted": source_selection_attempted,
                    "source_selection_winner": source_selection_winner,
                    "source_selection_reason": source_selection_reason,
                    "tidal_match_method": tidal_match_method,
                    "tidal_track_id": tidal_track_id,
                    "tidal_audio_quality": tidal_audio_quality,
                    "tidal_audio_quality_rank": tidal_audio_quality_rank_str,
                    "duration_diff_ms": duration_diff_ms,
                }
            )
            writer.writerow(row)
            link_stats[source_link][decision] += 1

    with decision_summary_csv.open("w", encoding="utf-8", newline="") as fsum:
        writer = csv.DictWriter(fsum, fieldnames=["source_link", "keep", "skip"])
        writer.writeheader()
        for source_link, stats in sorted(link_stats.items()):
            writer.writerow({"source_link": source_link, "keep": stats["keep"], "skip": stats["skip"]})

    keep_urls_unique = list(dict.fromkeys(u for u in keep_urls if u))
    keep_urls_txt.write_text("\n".join(keep_urls_unique) + ("\n" if keep_urls_unique else ""), encoding="utf-8")

    total_keep = sum(s["keep"] for s in link_stats.values())
    total_skip = sum(s["skip"] for s in link_stats.values())

    # Generate summary report
    report_txt = out_dir / f"precheck_report_{ts}.md"
    with report_txt.open("w", encoding="utf-8") as f:
        f.write("# Pre-Download Check Report\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Input:** `{input_path}`\n")
        f.write(f"**Database:** `{db_path}`\n\n")
        f.write("## Summary\n\n")
        f.write(f"| Metric | Count |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Tracks to download (keep) | {total_keep} |\n")
        f.write(f"| Tracks skipped (same or better already exists) | {total_skip} |\n")
        f.write(f"| Total tracks checked | {total_keep + total_skip} |\n")
        f.write(f"| Links processed | {len(link_stats)} |\n\n")
        f.write("## Outputs\n\n")
        f.write(f"- **Decisions CSV:** `{decision_csv}`\n")
        f.write(f"- **Summary CSV:** `{decision_summary_csv}`\n")
        f.write(f"- **Keep URLs (for downloader):** `{keep_urls_txt}`\n\n")
        f.write(f"- **Candidate quality rank:** `{int(args.candidate_quality_rank)}`\n\n")
        f.write("## Match Methods\n\n")
        f.write("| Method | Confidence | Phase | Description |\n")
        f.write("|--------|------------|-------|-------------|\n")
        f.write("| already_downloaded_source_match:beatport_id | high | 1 | Provider track ID found in track_identity + asset_file |\n")
        f.write("| already_downloaded_source_match:tidal_id    | high | 1 | Provider track ID found in track_identity + asset_file |\n")
        f.write("| already_downloaded_source_match:isrc        | high | 1 | ISRC found in track_identity + asset_file |\n")
        f.write("| isrc | high | 2 | Exact ISRC match in files table |\n")
        f.write("| beatport_id | high | 2 | Exact Beatport track ID match in files table |\n")
        f.write("| exact_title_artist_album | medium | 2 | Normalized title+artist+album match in files table |\n")
        f.write("| exact_title_artist | low | 2 | Normalized title+artist match in files table (no album) |\n")

    if not args.quiet:
        print("Pre-download check complete")
        print(f"  decisions_csv: {decision_csv}")
        print(f"  summary_csv:   {decision_summary_csv}")
        print(f"  keep_urls:     {keep_urls_txt}")
        print(f"  report:        {report_txt}")
        print(f"  keep={total_keep} skip={total_skip}")
        if selection_stats["attempted"] > 0:
            print(
                "  source_selection:"
                f" attempted={selection_stats['attempted']}"
                f" selected_tidal={selection_stats['selected_tidal']}"
                f" retained_beatport={selection_stats['retained_beatport']}"
                f" ambiguous={selection_stats['ambiguous']}"
                f" unverified={selection_stats['unverified']}"
                f" not_better={selection_stats['not_better']}"
                f" unavailable={selection_stats['unavailable']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
