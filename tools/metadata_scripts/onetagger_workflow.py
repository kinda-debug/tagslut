#!/usr/bin/env python3
"""OneTagger workflow helpers for tagslut operations.

Modes:
  - build: create an M3U of library FLAC files missing canonical ISRC in DB
  - run: run OneTagger on an M3U via symlink batch directory
  - sync: build + run in one command
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import subprocess
import sys
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from mutagen import File as MutagenFile
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3, TXXX
    from mutagen.mp3 import MP3
    from mutagen.mp4 import MP4, MP4FreeForm
    from mutagen.oggvorbis import OggVorbis
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"mutagen is required: {exc}") from exc


_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

DEFAULT_LIBRARY_ROOT = Path(os.environ.get("MASTER_LIBRARY") or os.environ.get("LIBRARY_ROOT", "./library"))
DEFAULT_WORK_ROOT = Path(os.environ.get("ONETAGGER_WORK_ROOT", "./work"))
DEFAULT_OUT_DIR = _REPO / "artifacts/compare"
DEFAULT_ONETAGGER_BIN = Path(
    os.environ.get(
        "ONETAGGER_BIN",
        "./tools/onetagger/onetagger-cli",
    )
)
DEFAULT_CONFIG_PATH = Path.home() / ".config/onetagger/config.tagslut-missing-isrc.json"
DEFAULT_BASE_CONFIG_PATH = Path.home() / ".config/onetagger/config.json"
DEFAULT_RUNS_DIR = Path.home() / "Library/Preferences/com.OneTagger.OneTagger/runs"
DEFAULT_AUDIOFEATURES_PATH = Path(os.environ.get("DJ_LIBRARY") or os.environ.get("DJ_MP3_ROOT", "./dj_library_mp3"))
DEFAULT_AUDIOFEATURES_CONFIG_PATH = Path.home() / ".config/onetagger/audiofeatures.json"
DEFAULT_METADATA_PATH = Path(os.environ.get("DJ_LIBRARY") or os.environ.get("DJ_MP3_ROOT", "./dj_library_mp3"))
DEFAULT_METADATA_CONFIG_PATH = Path.home() / ".config/onetagger/config.tagslut-metadata.json"
DEFAULT_METADATA_TAGS = "genre,style,bpm,key,remixer,label,releaseDate,version,isrc"
DEFAULT_METADATA_PLATFORMS = "beatport,tidal,traxsource,deezer"
DEFAULT_METADATA_STRICTNESS = 0.92
DEFAULT_METADATA_MAX_DURATION_DIFF = 3
PRETTY_OUTPUT = os.environ.get("TAGSLUT_PRETTY", "1").strip() != "0"
_LINK_PREFIX_RE = re.compile(rf"^{re.escape(str(DEFAULT_WORK_ROOT))}/onetagger_links_[^/]+/\\d+__")
DEFAULT_MIN_DURATION_SEC = 240
DEFAULT_MAX_DURATION_SEC = 900
DEFAULT_MIN_BPM = 90.0
DEFAULT_MAX_BPM = 190.0
DEFAULT_EXCLUDE_GENRES = "classical,opera,symphony,concerto,folk,acoustic,singer-songwriter,soundtrack,film score,score,spoken word,audiobook,gospel,sermon"
DEFAULT_EXCLUDE_TITLE_KEYWORDS = "mix,mixed,dj mix,radio mix,continuous mix,mixset"

AUDIO_EXTENSIONS = {
    ".aif",
    ".aiff",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
}


@dataclass
class BuildResult:
    m3u_path: Path
    total_rows: int
    existing_files: int
    missing_on_disk: int


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve_db(path: str | None, *, purpose: str = "read") -> Path:
    try:
        resolution = resolve_cli_env_db_path(path, purpose=purpose, source_label="--db")
    except DbResolutionError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print(f"Resolved DB path: {resolution.path}")
    return resolution.path


def _normalize_path_line(line: str) -> str:
    value = line.strip()
    if not value or value.startswith("#"):
        return ""
    return value


def _read_m3u_lines(m3u_path: Path) -> list[Path]:
    paths: list[Path] = []
    for raw in m3u_path.read_text(encoding="utf-8", errors="replace").splitlines():
        value = _normalize_path_line(raw)
        if not value:
            continue
        paths.append(Path(value).expanduser())
    return paths


def _collect_audio_paths(path: Path) -> list[Path]:
    if not path.exists():
        raise SystemExit(f"Path not found: {path}")
    if path.is_file():
        if path.suffix.lower() in {".m3u", ".m3u8"}:
            return _read_m3u_lines(path)
        return [path]
    results: list[Path] = []
    for item in path.rglob("*"):
        if item.is_file() and item.suffix.lower() in AUDIO_EXTENSIONS:
            results.append(item)
    return results


def _read_easy_tags(path: Path) -> dict[str, list[str]]:
    try:
        audio = MutagenFile(str(path), easy=True)
    except Exception:
        return {}
    if audio is None or not audio.tags:
        return {}
    return {str(k).lower(): [str(v) for v in vals] for k, vals in audio.tags.items()}


def _parse_bpm(value: str | None) -> float | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _estimate_lexicon_energy(tags: dict[str, list[str]]) -> tuple[int, int]:
    try:
        from tagslut.dj.lexicon import estimate_tags
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Failed importing lexicon: {exc}") from exc

    genre_vals = tags.get("genre") or tags.get("genres") or []
    bpm_vals = tags.get("bpm") or []
    key_vals = tags.get("key") or []
    genre = " ".join(genre_vals).strip()
    bpm = _parse_bpm(bpm_vals[0] if bpm_vals else None)
    key = key_vals[0].strip() if key_vals else ""

    payload = {
        "genre": genre,
        "bpm": bpm,
        "key": key,
    }
    result = estimate_tags(payload)
    energy = int(result.get("Energy") or 0)
    danceability = int(result.get("Danceability") or 0)
    return energy, danceability


def _write_energy_tags(path: Path, energy: int, danceability: int, overwrite: bool) -> bool:
    try:
        audio = MutagenFile(str(path), easy=False)
    except Exception:
        return False
    if audio is None:
        return False

    energy_tag = str(int(round(energy * 10)))
    dance_tag = str(int(round(danceability * 10)))

    if isinstance(audio, MP3):
        tags = audio.tags or ID3()
        if not overwrite:
            if tags.getall("TXXX:1T_ENERGY") or tags.getall("TXXX:1T_DANCEABILITY"):
                return False
        tags.add(TXXX(encoding=3, desc="1T_ENERGY", text=[energy_tag]))
        tags.add(TXXX(encoding=3, desc="1T_DANCEABILITY", text=[dance_tag]))
        audio.tags = tags
    elif isinstance(audio, MP4):
        if audio.tags is None:
            audio.add_tags()
        energy_key = "----:com.apple.iTunes:1T_ENERGY"
        dance_key = "----:com.apple.iTunes:1T_DANCEABILITY"
        if not overwrite and (energy_key in audio.tags or dance_key in audio.tags):
            return False
        audio.tags[energy_key] = [MP4FreeForm(energy_tag.encode("utf-8"))]
        audio.tags[dance_key] = [MP4FreeForm(dance_tag.encode("utf-8"))]
    elif isinstance(audio, (FLAC, OggVorbis)):
        if not overwrite:
            if "1T_ENERGY" in audio or "1T_DANCEABILITY" in audio:
                return False
        audio["1T_ENERGY"] = energy_tag
        audio["1T_DANCEABILITY"] = dance_tag
    else:
        # Best effort for other taggers with dict-like tags
        if hasattr(audio, "tags") and isinstance(audio.tags, dict):
            if not overwrite and ("1T_ENERGY" in audio.tags or "1T_DANCEABILITY" in audio.tags):
                return False
            audio.tags["1T_ENERGY"] = energy_tag
            audio.tags["1T_DANCEABILITY"] = dance_tag
        else:
            return False

    audio.save()
    return True


def _write_m3u_lines(paths: list[Path], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for path in paths:
            handle.write(f"{path}\n")
    return out_path


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _query_missing_isrc_paths(db_path: Path, library_root: Path) -> list[sqlite3.Row]:
    sql = """
    SELECT path, canonical_bpm, canonical_genre, canonical_title, canonical_album, canonical_duration
    FROM files
    WHERE path LIKE ?
      AND lower(path) LIKE '%.flac'
      AND (canonical_isrc IS NULL OR trim(canonical_isrc) = '')
    ORDER BY path
    """
    prefix = f"{library_root.as_posix().rstrip('/')}/%"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, (prefix,)).fetchall()
    finally:
        conn.close()
    return rows


def _duration_ok(duration: float | None, min_sec: int, max_sec: int) -> bool:
    if duration is None:
        return True
    if duration <= 0:
        return False
    return min_sec <= duration <= max_sec


def _bpm_ok(bpm: float | None, min_bpm: float, max_bpm: float) -> bool:
    if bpm is None:
        return True
    if bpm <= 0:
        return False
    if min_bpm <= bpm <= max_bpm:
        return True
    # Allow half-tempo values (e.g., 60 treated as 120)
    if min_bpm <= bpm * 2 <= max_bpm:
        return True
    return False


def _genre_blocked(genre: str, excluded: list[str]) -> bool:
    if not genre:
        return False
    g = genre.lower()
    return any(token in g for token in excluded)


def _title_blocked(title: str, album: str, keywords: list[str]) -> bool:
    hay = f"{title} {album}".lower()
    if not hay.strip():
        return False
    if "remix" in hay or "rework" in hay or "edit" in hay:
        return False
    return any(key in hay for key in keywords)


def build_missing_isrc_m3u(
    db_path: Path,
    library_root: Path,
    out_m3u: Path,
    limit: int = 0,
    min_duration_sec: int = DEFAULT_MIN_DURATION_SEC,
    max_duration_sec: int = DEFAULT_MAX_DURATION_SEC,
    min_bpm: float = DEFAULT_MIN_BPM,
    max_bpm: float = DEFAULT_MAX_BPM,
    exclude_genres: list[str] | None = None,
    exclude_title_keywords: list[str] | None = None,
) -> BuildResult:
    rows = _query_missing_isrc_paths(db_path, library_root)
    if limit > 0:
        rows = rows[:limit]

    existing: list[Path] = []
    missing_count = 0
    exclude_genres = exclude_genres or []
    exclude_title_keywords = exclude_title_keywords or []

    for row in rows:
        path = Path(str(row["path"]))
        duration = row["canonical_duration"]
        bpm = row["canonical_bpm"]
        genre = str(row["canonical_genre"] or "")
        title = str(row["canonical_title"] or "")
        album = str(row["canonical_album"] or "")

        if not _duration_ok(duration, min_duration_sec, max_duration_sec):
            continue
        if not _bpm_ok(bpm, min_bpm, max_bpm):
            continue
        if _genre_blocked(genre, exclude_genres):
            continue
        if _title_blocked(title, album, exclude_title_keywords):
            continue

        if path.exists():
            existing.append(path.resolve())
        else:
            missing_count += 1

    existing = _dedupe_paths(existing)
    _write_m3u_lines(existing, out_m3u)
    return BuildResult(
        m3u_path=out_m3u,
        total_rows=len(rows),
        existing_files=len(existing),
        missing_on_disk=missing_count,
    )


def _safe_link_name(index: int, src: Path) -> str:
    base = src.name.replace("/", "_").replace("\x00", "")
    if len(base) > 180:
        stem = src.stem[:140]
        suffix = src.suffix
        base = f"{stem}{suffix}"
    return f"{index:05d}__{base}"


def create_symlink_batch_from_paths(items: list[Path], link_dir: Path, limit: int = 0) -> tuple[list[Path], int]:
    if limit > 0:
        items = items[:limit]
    link_dir.mkdir(parents=True, exist_ok=True)

    links: list[Path] = []
    missing = 0
    for idx, src in enumerate(items, start=1):
        resolved = src.expanduser()
        if not resolved.exists():
            missing += 1
            continue
        link_path = link_dir / _safe_link_name(idx, resolved)
        if link_path.exists():
            links.append(link_path)
            continue
        try:
            link_path.symlink_to(resolved)
            links.append(link_path)
        except FileExistsError:
            links.append(link_path)
    return links, missing


def create_symlink_batch(m3u_path: Path, link_dir: Path, limit: int = 0) -> tuple[list[Path], int]:
    return create_symlink_batch_from_paths(_read_m3u_lines(m3u_path), link_dir, limit=limit)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}


def _extract_spotify_credentials(base_config: Path) -> tuple[str, str]:
    if not base_config.exists():
        raise SystemExit(f"Spotify credentials not found; base config missing: {base_config}")
    cfg = _load_json(base_config)
    spotify = cfg.get("spotify") or {}
    client_id = (
        spotify.get("clientId")
        or spotify.get("clientID")
        or spotify.get("client_id")
        or os.environ.get("SPOTIFY_CLIENT_ID", "")
    )
    client_secret = (
        spotify.get("clientSecret")
        or spotify.get("clientSECRET")
        or spotify.get("client_secret")
        or os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    )
    if not client_id or not client_secret:
        raise SystemExit("Spotify credentials missing in base config and env.")
    return str(client_id), str(client_secret)


def _load_audiofeatures_default(onetagger_bin: Path) -> dict[str, Any]:
    try:
        raw = subprocess.check_output([str(onetagger_bin), "--audiofeatures-config"])
        return json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as exc:
        raise SystemExit(f"Failed generating audiofeatures config via {onetagger_bin}: {exc}") from exc


def write_audiofeatures_config(
    out_config: Path,
    onetagger_bin: Path,
    properties: list[str],
    enable_all: bool,
) -> Path:
    cfg = _load_json(out_config)
    if not cfg:
        cfg = _load_audiofeatures_default(onetagger_bin)
    if not enable_all and properties:
        prop_map = cfg.get("properties", {})
        if isinstance(prop_map, dict):
            allowed = {name.strip().lower() for name in properties if name.strip()}
            for key, payload in prop_map.items():
                if isinstance(payload, dict):
                    payload["enabled"] = key.lower() in allowed
    out_config.parent.mkdir(parents=True, exist_ok=True)
    out_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return out_config


def write_onetagger_config(
    base_config: Path,
    out_config: Path,
    threads: int,
    *,
    strictness: float,
    platforms: list[str],
) -> Path:
    cfg = _load_json(base_config)
    cfg["tags"] = ["isrc"]
    cfg["overwrite"] = False
    cfg["skipTagged"] = False
    cfg["strictness"] = strictness
    cfg["matchDuration"] = True
    cfg["maxDurationDifference"] = min(10, max(1, int(cfg.get("maxDurationDifference", 3) or 3)))
    cfg["shortTitle"] = False
    cfg["parseFilename"] = False
    cfg["matchById"] = False
    cfg["multipleMatches"] = "Default"
    cfg["threads"] = max(1, threads)
    cfg["platforms"] = platforms
    cfg["enableShazam"] = True
    cfg["forceShazam"] = False
    out_config.parent.mkdir(parents=True, exist_ok=True)
    out_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return out_config


def write_onetagger_metadata_config(
    base_config: Path,
    out_config: Path,
    threads: int,
    *,
    strictness: float,
    platforms: list[str],
    tags: list[str],
    max_duration_difference: int,
) -> Path:
    cfg = _load_json(base_config)
    cfg["tags"] = tags
    cfg["overwrite"] = False
    cfg["mergeGenres"] = True
    cfg["strictness"] = strictness
    cfg["matchDuration"] = True
    cfg["maxDurationDifference"] = max(1, int(max_duration_difference))
    cfg["shortTitle"] = False
    cfg["parseFilename"] = False
    cfg["matchById"] = False
    cfg["multipleMatches"] = "Default"
    cfg["enableShazam"] = False
    cfg["forceShazam"] = False
    cfg["platforms"] = platforms
    cfg["albumArtFile"] = False
    cfg["albumTagging"] = False
    cfg["camelot"] = True
    cfg["stylesOptions"] = "stylesToGenre"
    cfg["threads"] = max(1, threads)
    out_config.parent.mkdir(parents=True, exist_ok=True)
    out_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return out_config


def _list_run_files(runs_dir: Path, prefix: str) -> set[Path]:
    return set(runs_dir.glob(f"{prefix}-*.m3u"))


def _latest_file(paths: set[Path]) -> Path | None:
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def _resolve_result_file(before: set[Path], after: set[Path]) -> Path | None:
    new_files = after - before
    if new_files:
        return _latest_file(new_files)
    return _latest_file(after)


def _count_isrc(path: Path) -> str:
    try:
        audio = MutagenFile(str(path), easy=False)
    except Exception:
        return ""
    if audio is None:
        return ""
    tags = getattr(audio, "tags", None) or {}
    values: list[Any] = []

    def _extend(raw: Any) -> None:
        if raw is None:
            return
        if isinstance(raw, (list, tuple)):
            values.extend(raw)
        else:
            values.append(raw)

    for key in ("isrc", "ISRC"):
        if key in tags:
            _extend(tags.get(key))

    if isinstance(tags, ID3) or hasattr(tags, "getall"):
        try:
            for frame in tags.getall("TSRC"):
                if hasattr(frame, "text"):
                    _extend(frame.text)
                else:
                    _extend(frame)
        except Exception:
            pass

    for key in ("----:com.apple.iTunes:ISRC", "----:com.apple.iTunes:TSRC"):
        if key in tags:
            _extend(tags.get(key))

    normalized = [str(value).strip() for value in values if str(value).strip()]
    return ";".join(normalized)


def _paths_missing_isrc(paths: list[Path]) -> list[Path]:
    missing: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if not _count_isrc(path):
            missing.append(path)
    return missing


def _run_with_tee(cmd: list[str], log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        current_track = ""
        total_count = 0
        expected_total = 0
        processed = 0
        current_sources: dict[str, str] = {}

        def _flush_track() -> None:
            if not current_track:
                return
            sources = " ".join(
                f"{src}={state}" for src, state in sorted(current_sources.items())
            )
            msg = f"{_progress_line()} {current_track}"
            if sources:
                msg = f"{msg} | {sources}"
            print(msg)

        def _set_source_state(source: str, state: str, accuracy: str) -> None:
            key = source.lower()
            suffix = f"({accuracy})" if accuracy else ""
            current_sources[key] = f"{state}{suffix}"

        def _format_track(path: str) -> str:
            value = _LINK_PREFIX_RE.sub("", path)
            return value

        def _format_status(state: str) -> str:
            if state.lower() == "ok":
                return "\033[1;32mOK\033[0m"
            return "\033[1;31mFAIL\033[0m"

        def _progress_line() -> str:
            if expected_total:
                return f"[{processed}/{expected_total}]"
            return f"[{processed}]"

        try:
            for line in proc.stdout:
                if PRETTY_OUTPUT:
                    # Track lines and provider status lines
                    if "Starting tagging:" in line and "files" in line:
                        # Example: Starting tagging: 1325 files, 12 threads!
                        try:
                            expected_total = int(line.split("Starting tagging:", 1)[1].split("files", 1)[0].strip())
                        except Exception:
                            expected_total = 0
                        print(line.strip())
                        log.write(line)
                        continue
                    if "Tagging:" in line:
                        _flush_track()
                        current_sources = {}
                        total_count += 1
                        processed = total_count
                        start = line.find("Tagging:")
                        if start >= 0:
                            current_track = line[start + len("Tagging:") :].strip().strip('"')
                            current_track = _format_track(current_track)
                        log.write(line)
                        continue
                    if "State:" in line and "Accuracy:" in line and "[" in line and "]" in line:
                        # Example: [spotify] State: Ok, Accuracy: Some(1.0), Path: "..."
                        source = line.split("[", 1)[1].split("]", 1)[0].strip()
                        parts = line.split("State:", 1)[1].split(",", 2)
                        state = parts[0].strip() if parts else "Error"
                        accuracy = ""
                        if "Accuracy:" in line:
                            accuracy = line.split("Accuracy:", 1)[1].split(",", 1)[0].strip()
                        _set_source_state(source, _format_status(state), accuracy)
                        log.write(line)
                        continue
                    if "Starting tagging:" in line:
                        print(line.strip())
                        log.write(line)
                        continue
                    if line.strip().startswith("Starting "):
                        print(line.strip())
                        log.write(line)
                        continue
                    # Suppress other noisy lines in pretty mode
                    log.write(line)
                    continue
                # Non-pretty: passthrough
                print(line, end="")
                log.write(line)
            exit_code = proc.wait()
            if PRETTY_OUTPUT:
                _flush_track()
            return exit_code
        except KeyboardInterrupt:
            log.write("\n[onetagger_workflow] interrupted by user\n")
            log.flush()
            proc.terminate()
            return 130


def run_audiofeatures(
    *,
    path: Path,
    onetagger_bin: Path,
    audio_config: Path,
    base_config: Path,
    spotify_client_id: str,
    spotify_client_secret: str,
    no_subfolders: bool,
    properties: list[str],
    enable_all: bool,
    out_dir: Path,
) -> Path:
    if not onetagger_bin.exists():
        raise SystemExit(f"OneTagger binary not found: {onetagger_bin}")
    if not path.exists():
        raise SystemExit(f"Audiofeatures path not found: {path}")

    if not spotify_client_id or not spotify_client_secret:
        spotify_client_id, spotify_client_secret = _extract_spotify_credentials(base_config)

    cfg_path = write_audiofeatures_config(
        audio_config,
        onetagger_bin,
        properties=properties,
        enable_all=enable_all,
    )

    stamp = _now_stamp()
    log_path = out_dir / f"onetagger_audiofeatures_{stamp}.log"
    cmd = [
        str(onetagger_bin),
        "audiofeatures",
        "--config",
        str(cfg_path),
        "--path",
        str(path),
        "--client-id",
        spotify_client_id,
        "--client-secret",
        spotify_client_secret,
    ]
    if no_subfolders:
        cmd.append("--no-subfolders")

    print("Running audiofeatures:", " ".join(cmd))
    exit_code = _run_with_tee(cmd, log_path)
    summary = {
        "mode": "audiofeatures",
        "path": str(path),
        "config_path": str(cfg_path),
        "log_path": str(log_path),
        "exit_code": exit_code,
        "source": "spotify",
    }
    summary_path = out_dir / f"onetagger_audiofeatures_summary_{stamp}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote: {summary_path}")
    print("Summary:", json.dumps(summary, indent=2))
    if exit_code != 0:
        raise SystemExit(f"OneTagger audiofeatures failed (exit={exit_code}). Log: {log_path}")
    print(f"Wrote: {log_path}")
    return log_path


def _normalize_paths(items: Iterable[Path]) -> list[Path]:
    out: list[Path] = []
    for item in items:
        resolved = item.expanduser().resolve()
        if resolved.exists():
            out.append(resolved)
    return _dedupe_paths(out)


def run_lexicon_audiofeatures(
    *,
    path: Path,
    db_path: Path | None,
    write_tags: bool,
    overwrite_tags: bool,
    require_bpm_or_genre: bool,
    limit: int,
) -> dict[str, Any]:
    items = _collect_audio_paths(path)
    if limit > 0:
        items = items[:limit]

    processed = 0
    skipped_missing = 0
    skipped_no_tags = 0
    skipped_requirements = 0
    skipped_existing = 0
    updated_tags = 0
    db_updates = 0

    updates: list[tuple[float, float, str]] = []
    for item in items:
        if not item.exists():
            skipped_missing += 1
            continue
        tags = _read_easy_tags(item)
        if not tags:
            skipped_no_tags += 1
            continue

        genre_vals = tags.get("genre") or tags.get("genres") or []
        bpm_vals = tags.get("bpm") or []
        if require_bpm_or_genre and not genre_vals and not bpm_vals:
            skipped_requirements += 1
            continue

        energy, danceability = _estimate_lexicon_energy(tags)
        if energy <= 0 or danceability <= 0:
            skipped_requirements += 1
            continue

        energy_db = round(energy / 10.0, 4)
        dance_db = round(danceability / 10.0, 4)
        updates.append((energy_db, dance_db, str(item.resolve())))

        if write_tags:
            wrote = _write_energy_tags(item, energy, danceability, overwrite_tags)
            if wrote:
                updated_tags += 1
            else:
                skipped_existing += 1

        processed += 1

    if db_path and db_path.exists() and updates:
        conn = sqlite3.connect(str(db_path))
        try:
            before = conn.total_changes
            conn.executemany(
                "UPDATE files SET canonical_energy = ?, canonical_danceability = ?, enriched_at = datetime('now') WHERE path = ?",
                updates,
            )
            conn.commit()
            db_updates = conn.total_changes - before
        finally:
            conn.close()

    return {
        "processed": processed,
        "skipped_missing": skipped_missing,
        "skipped_no_tags": skipped_no_tags,
        "skipped_requirements": skipped_requirements,
        "skipped_existing_tags": skipped_existing,
        "updated_tags": updated_tags,
        "db_updates": db_updates,
    }


def run_metadata_onetagger_for_items(
    *,
    items: Iterable[Path],
    onetagger_bin: Path,
    config_path: Path,
    base_config: Path,
    threads: int,
    strictness: float,
    max_duration_difference: int,
    platforms: list[str],
    tags: list[str],
    link_root: Path,
    out_dir: Path,
    limit: int,
    require_isrc: bool,
) -> Path:
    if not onetagger_bin.exists():
        raise SystemExit(f"OneTagger binary not found: {onetagger_bin}")

    normalized = _normalize_paths(items)
    if require_isrc:
        normalized = [path for path in normalized if _count_isrc(path)]

    if limit > 0:
        normalized = normalized[:limit]

    if not normalized:
        raise SystemExit("No files to tag after ISRC filtering.")

    stamp = _now_stamp()
    out_dir.mkdir(parents=True, exist_ok=True)
    input_m3u = out_dir / f"onetagger_metadata_input_{stamp}.m3u"
    _write_m3u_lines(normalized, input_m3u)

    link_dir = link_root / f"onetagger_metadata_links_{stamp}"
    links, missing = create_symlink_batch_from_paths(normalized, link_dir, limit=0)
    if not links:
        raise SystemExit("No files could be linked for metadata tagging.")
    if missing:
        print(f"Metadata: {missing} input paths missing on disk.")

    write_onetagger_metadata_config(
        base_config,
        config_path,
        threads=threads,
        strictness=strictness,
        platforms=platforms,
        tags=tags,
        max_duration_difference=max_duration_difference,
    )

    log_path = out_dir / f"onetagger_metadata_{stamp}.log"
    cmd = [
        str(onetagger_bin),
        "autotagger",
        "--config",
        str(config_path),
        "--path",
        str(link_dir),
    ]
    print("Running metadata:", " ".join(cmd))
    exit_code = _run_with_tee(cmd, log_path)
    summary = {
        "mode": "metadata",
        "input_files": len(normalized),
        "linked_files": len(links),
        "missing_from_input": missing,
        "config_path": str(config_path),
        "log_path": str(log_path),
        "exit_code": exit_code,
    }
    summary_path = out_dir / f"onetagger_metadata_summary_{stamp}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote: {summary_path}")
    print("Summary:", json.dumps(summary, indent=2))
    if exit_code != 0:
        raise SystemExit(f"OneTagger metadata failed (exit={exit_code}). Log: {log_path}")
    print(f"Wrote: {log_path}")
    return log_path


def run_metadata_onetagger(
    *,
    path: Path,
    onetagger_bin: Path,
    config_path: Path,
    base_config: Path,
    threads: int,
    strictness: float,
    max_duration_difference: int,
    platforms: list[str],
    tags: list[str],
    link_root: Path,
    out_dir: Path,
    limit: int,
    require_isrc: bool,
) -> Path:
    items = _collect_audio_paths(path)
    return run_metadata_onetagger_for_items(
        items=items,
        onetagger_bin=onetagger_bin,
        config_path=config_path,
        base_config=base_config,
        threads=threads,
        strictness=strictness,
        max_duration_difference=max_duration_difference,
        platforms=platforms,
        tags=tags,
        link_root=link_root,
        out_dir=out_dir,
        limit=limit,
        require_isrc=require_isrc,
    )


def _update_db_isrc_from_rows(db_path: Path, rows: list[dict[str, Any]]) -> int:
    updates: list[tuple[str, str]] = []
    for row in rows:
        isrc_value = str(row.get("isrc_after", "")).strip()
        path = str(row.get("target_path", "")).strip()
        if not isrc_value or not path:
            continue
        canonical = isrc_value.split(";", 1)[0].strip()
        if not canonical:
            continue
        updates.append((canonical, path))

    if not updates:
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        before_changes = conn.total_changes
        conn.executemany(
            "UPDATE files SET canonical_isrc = ?, enriched_at = datetime('now') WHERE path = ?",
            updates,
        )
        conn.commit()
        return conn.total_changes - before_changes
    finally:
        conn.close()


def run_onetagger(
    *,
    m3u_path: Path,
    link_root: Path,
    out_dir: Path,
    onetagger_bin: Path,
    config_path: Path,
    base_config: Path,
    runs_dir: Path,
    threads: int,
    limit: int,
    max_passes: int,
    strictness: float,
    platforms: list[str],
    db_path: Path | None,
    db_refresh: bool,
    db_refresh_only: bool,
) -> tuple[Path, Path]:
    stamp = _now_stamp()
    raw_items = _read_m3u_lines(m3u_path)
    if limit > 0:
        raw_items = raw_items[:limit]

    existing_items: list[Path] = []
    missing_input = 0
    for item in raw_items:
        resolved = item.expanduser().resolve()
        if resolved.exists():
            existing_items.append(resolved)
        else:
            missing_input += 1
    existing_items = _dedupe_paths(existing_items)
    if not existing_items:
        raise SystemExit("No existing files resolved from M3U; nothing to tag.")

    unresolved = _paths_missing_isrc(existing_items)
    initial_missing = len(unresolved)

    success_paths: set[Path] = set()
    failed_paths: set[Path] = set()
    pass_results: list[dict[str, Any]] = []
    latest_log_path = out_dir / f"onetagger_run_{stamp}_p00.log"
    final_success_m3u: Path | None = None
    final_failed_m3u: Path | None = None

    effective_max_passes = max(0, max_passes)
    if db_refresh_only:
        effective_max_passes = 0

    for pass_index in range(1, effective_max_passes + 1):
        if not unresolved:
            break

        pass_stamp = f"{stamp}_p{pass_index:02d}"
        pass_input_m3u = out_dir / f"onetagger_input_{pass_stamp}.m3u"
        link_dir = link_root / f"onetagger_links_{pass_stamp}"
        log_path = out_dir / f"onetagger_run_{pass_stamp}.log"
        latest_log_path = log_path
        _write_m3u_lines(unresolved, pass_input_m3u)

        links, missing_from_pass_m3u = create_symlink_batch(pass_input_m3u, link_dir, limit=0)
        if not links:
            pass_results.append(
                {
                    "pass": pass_index,
                    "input_unresolved": len(unresolved),
                    "linked_files": 0,
                    "missing_from_pass_m3u_on_disk": missing_from_pass_m3u,
                    "unresolved_after": len(unresolved),
                    "progress": "no_links",
                }
            )
            break

        write_onetagger_config(
            base_config,
            config_path,
            threads=threads,
            strictness=strictness,
            platforms=platforms,
        )

        success_before = _list_run_files(runs_dir, "success")
        failed_before = _list_run_files(runs_dir, "failed")

        cmd = [
            str(onetagger_bin),
            "autotagger",
            "--config",
            str(config_path),
            "--path",
            str(link_dir),
        ]
        print(f"Running pass {pass_index}/{effective_max_passes}:", " ".join(cmd))
        exit_code = _run_with_tee(cmd, log_path)
        if exit_code != 0:
            raise SystemExit(f"OneTagger failed (exit={exit_code}). Log: {log_path}")

        success_after = _list_run_files(runs_dir, "success")
        failed_after = _list_run_files(runs_dir, "failed")
        success_m3u = _resolve_result_file(success_before, success_after)
        failed_m3u = _resolve_result_file(failed_before, failed_after)
        final_success_m3u = success_m3u
        final_failed_m3u = failed_m3u

        pass_success = set()
        pass_failed = set()
        if success_m3u and success_m3u.exists():
            pass_success = {path.resolve() for path in _read_m3u_lines(success_m3u) if path.exists()}
            success_paths |= pass_success
        if failed_m3u and failed_m3u.exists():
            pass_failed = {path.resolve() for path in _read_m3u_lines(failed_m3u) if path.exists()}
            failed_paths |= pass_failed

        unresolved_after = _paths_missing_isrc(unresolved)
        progress = "ok" if len(unresolved_after) < len(unresolved) else "stalled"
        pass_results.append(
            {
                "pass": pass_index,
                "input_unresolved": len(unresolved),
                "linked_files": len(links),
                "missing_from_pass_m3u_on_disk": missing_from_pass_m3u,
                "pass_success_count": len(pass_success),
                "pass_failed_count": len(pass_failed),
                "unresolved_after": len(unresolved_after),
                "progress": progress,
            }
        )
        unresolved = unresolved_after
        if progress == "stalled":
            break

    rows: list[dict[str, Any]] = []
    isrc_present = 0
    still_missing_sample: list[str] = []
    for target in existing_items:
        isrc_value = _count_isrc(target)
        has_isrc = bool(isrc_value)
        if has_isrc:
            isrc_present += 1
        elif len(still_missing_sample) < 30:
            still_missing_sample.append(target.name)
        rows.append(
            {
                "target_path": str(target),
                "has_isrc_after": 1 if has_isrc else 0,
                "isrc_after": isrc_value,
                "in_success_m3u": 1 if target in success_paths else 0,
                "in_failed_m3u": 1 if target in failed_paths else 0,
            }
        )

    summary = {
        "m3u_input": str(m3u_path),
        "log_path": str(latest_log_path),
        "config_path": str(config_path),
        "total_files": len(existing_items),
        "missing_from_m3u_on_disk": missing_input,
        "max_passes": effective_max_passes,
        "passes_executed": len(pass_results),
        "initial_missing_isrc_count": initial_missing,
        "success_m3u": str(final_success_m3u) if final_success_m3u else "",
        "failed_m3u": str(final_failed_m3u) if final_failed_m3u else "",
        "success_count": len(success_paths),
        "failed_count": len(failed_paths),
        "isrc_present_after_count": isrc_present,
        "isrc_present_after_pct": round((isrc_present / len(existing_items)) * 100, 2) if existing_items else 0.0,
        "isrc_still_missing_after_count": len(existing_items) - isrc_present,
        "isrc_still_missing_sample": still_missing_sample,
        "pass_results": pass_results,
        "db_refresh_only": bool(db_refresh_only),
    }

    db_updates = 0
    if db_refresh and db_path is not None and db_path.exists():
        db_updates = _update_db_isrc_from_rows(db_path, rows)
    summary["db_isrc_rows_updated"] = db_updates

    summary_path = out_dir / f"onetagger_summary_{stamp}.json"
    rows_path = out_dir / f"onetagger_file_status_{stamp}.csv"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with rows_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["target_path"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote: {summary_path}")
    print(f"Wrote: {rows_path}")
    print("Summary:", json.dumps(summary, indent=2))
    return summary_path, rows_path


def _build_default_m3u_path(library_root: Path) -> Path:
    return library_root / f"needs_tagging_missing_isrc_{_now_stamp()}.m3u"


def cmd_build(args: argparse.Namespace) -> int:
    db_path = _resolve_db(args.db, purpose="read")
    library_root = Path(args.library_root).expanduser()
    output_path = Path(args.output).expanduser() if args.output else _build_default_m3u_path(library_root)
    result = build_missing_isrc_m3u(
        db_path=db_path,
        library_root=library_root,
        out_m3u=output_path,
        limit=args.limit,
        min_duration_sec=args.min_duration,
        max_duration_sec=args.max_duration,
        min_bpm=args.min_bpm,
        max_bpm=args.max_bpm,
        exclude_genres=[part.strip().lower() for part in args.exclude_genres.split(",") if part.strip()],
        exclude_title_keywords=[part.strip().lower() for part in args.exclude_title_keywords.split(",") if part.strip()],
    )
    print(f"M3U: {result.m3u_path}")
    print(f"DB rows (missing ISRC): {result.total_rows}")
    print(f"Existing files written: {result.existing_files}")
    print(f"Missing on disk: {result.missing_on_disk}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    m3u_path = Path(args.m3u).expanduser().resolve()
    if not m3u_path.exists():
        raise SystemExit(f"M3U not found: {m3u_path}")
    onetagger_bin = Path(args.onetagger_bin).expanduser().resolve()
    if not onetagger_bin.exists():
        raise SystemExit(f"OneTagger binary not found: {onetagger_bin}")
    db_purpose = "write" if (args.db_refresh or args.db_refresh_only) else "read"
    db_path = _resolve_db(args.db, purpose=db_purpose)

    run_onetagger(
        m3u_path=m3u_path,
        link_root=Path(args.link_root).expanduser(),
        out_dir=Path(args.out_dir).expanduser(),
        onetagger_bin=onetagger_bin,
        config_path=Path(args.config).expanduser(),
        base_config=Path(args.base_config).expanduser(),
        runs_dir=Path(args.runs_dir).expanduser(),
        threads=args.threads,
        limit=args.limit,
        max_passes=args.max_passes,
        strictness=args.strictness,
        platforms=[part.strip() for part in args.platforms.split(",") if part.strip()],
        db_path=db_path,
        db_refresh=args.db_refresh,
        db_refresh_only=args.db_refresh_only,
    )
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    db_purpose = "write" if (args.db_refresh or args.db_refresh_only) else "read"
    db_path = _resolve_db(args.db, purpose=db_purpose)
    library_root = Path(args.library_root).expanduser()
    output_path = Path(args.output).expanduser() if args.output else _build_default_m3u_path(library_root)
    build_result = build_missing_isrc_m3u(
        db_path=db_path,
        library_root=library_root,
        out_m3u=output_path,
        limit=args.limit,
        min_duration_sec=args.min_duration,
        max_duration_sec=args.max_duration,
        min_bpm=args.min_bpm,
        max_bpm=args.max_bpm,
        exclude_genres=[part.strip().lower() for part in args.exclude_genres.split(",") if part.strip()],
        exclude_title_keywords=[part.strip().lower() for part in args.exclude_title_keywords.split(",") if part.strip()],
    )
    print(f"M3U: {build_result.m3u_path}")
    print(f"DB rows (missing ISRC): {build_result.total_rows}")
    print(f"Existing files written: {build_result.existing_files}")
    print(f"Missing on disk: {build_result.missing_on_disk}")
    if build_result.existing_files == 0:
        print("No files to tag.")
        return 0

    onetagger_bin = Path(args.onetagger_bin).expanduser().resolve()
    if not onetagger_bin.exists():
        raise SystemExit(f"OneTagger binary not found: {onetagger_bin}")

    run_onetagger(
        m3u_path=build_result.m3u_path,
        link_root=Path(args.link_root).expanduser(),
        out_dir=Path(args.out_dir).expanduser(),
        onetagger_bin=onetagger_bin,
        config_path=Path(args.config).expanduser(),
        base_config=Path(args.base_config).expanduser(),
        runs_dir=Path(args.runs_dir).expanduser(),
        threads=args.threads,
        limit=args.limit,
        max_passes=args.max_passes,
        strictness=args.strictness,
        platforms=[part.strip() for part in args.platforms.split(",") if part.strip()],
        db_path=db_path,
        db_refresh=args.db_refresh,
        db_refresh_only=args.db_refresh_only,
    )

    if args.metadata_after_isrc and not args.db_refresh_only:
        items = _read_m3u_lines(build_result.m3u_path)
        tags = [part.strip() for part in args.metadata_tags.split(",") if part.strip()]
        platforms = [part.strip() for part in args.metadata_platforms.split(",") if part.strip()]
        run_metadata_onetagger_for_items(
            items=items,
            onetagger_bin=Path(args.onetagger_bin).expanduser().resolve(),
            config_path=Path(args.metadata_config).expanduser(),
            base_config=Path(args.base_config).expanduser(),
            threads=args.threads,
            strictness=args.metadata_strictness,
            max_duration_difference=args.metadata_max_duration_diff,
            platforms=platforms,
            tags=tags,
            link_root=Path(args.link_root).expanduser(),
            out_dir=Path(args.out_dir).expanduser(),
            limit=args.limit,
            require_isrc=True,
        )
    return 0


def cmd_audiofeatures(args: argparse.Namespace) -> int:
    db_path: Path | None = None
    if args.mode == "spotify":
        onetagger_bin = Path(args.onetagger_bin).expanduser().resolve()
        audio_config = Path(args.audiofeatures_config).expanduser()
        base_config = Path(args.base_config).expanduser()
        out_dir = Path(args.out_dir).expanduser()
        properties = [part.strip() for part in args.properties.split(",") if part.strip()]
        run_audiofeatures(
            path=Path(args.path).expanduser().resolve(),
            onetagger_bin=onetagger_bin,
            audio_config=audio_config,
            base_config=base_config,
            spotify_client_id=args.spotify_client_id or "",
            spotify_client_secret=args.spotify_client_secret or "",
            no_subfolders=args.no_subfolders,
            properties=properties,
            enable_all=args.enable_all,
            out_dir=out_dir,
        )
    else:
        db_path = _resolve_db(args.db, purpose="read")
    summary = run_lexicon_audiofeatures(
        path=Path(args.path).expanduser().resolve(),
        db_path=db_path,
        write_tags=not args.no_write_tags,
        overwrite_tags=args.overwrite_tags,
        require_bpm_or_genre=not args.no_require_bpm_or_genre,
        limit=args.limit,
    )
    summary.update(
        {
            "mode": "audiofeatures",
            "source": "lexicon",
            "path": str(Path(args.path).expanduser().resolve()),
        }
    )
    out_dir = Path(args.out_dir).expanduser()
    stamp = _now_stamp()
    summary_path = out_dir / f"lexicon_audiofeatures_summary_{stamp}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote: {summary_path}")
    print("Summary:", json.dumps(summary, indent=2))
    return 0


def cmd_metadata(args: argparse.Namespace) -> int:
    tags = [part.strip() for part in args.metadata_tags.split(",") if part.strip()]
    platforms = [part.strip() for part in args.metadata_platforms.split(",") if part.strip()]
    run_metadata_onetagger(
        path=Path(args.path).expanduser().resolve(),
        onetagger_bin=Path(args.onetagger_bin).expanduser().resolve(),
        config_path=Path(args.metadata_config).expanduser(),
        base_config=Path(args.base_config).expanduser(),
        threads=args.threads,
        strictness=args.metadata_strictness,
        max_duration_difference=args.metadata_max_duration_diff,
        platforms=platforms,
        tags=tags,
        link_root=Path(args.link_root).expanduser(),
        out_dir=Path(args.out_dir).expanduser(),
        limit=args.limit,
        require_isrc=args.require_isrc,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OneTagger helper workflow for missing ISRC enrichment.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(parser_obj: argparse.ArgumentParser) -> None:
        parser_obj.add_argument("--db", help="Path to tagslut SQLite DB.")
        parser_obj.add_argument(
            "--library-root",
            default=str(DEFAULT_LIBRARY_ROOT),
            help="Library root used to filter DB paths.",
        )
        parser_obj.add_argument("--output", default="", help="M3U output path. Default: <library-root>/needs_tagging_missing_isrc_<ts>.m3u")
        parser_obj.add_argument("--limit", type=int, default=0, help="Limit number of files (0 = all).")
        parser_obj.add_argument("--min-duration", type=int, default=DEFAULT_MIN_DURATION_SEC, help="Minimum duration seconds.")
        parser_obj.add_argument("--max-duration", type=int, default=DEFAULT_MAX_DURATION_SEC, help="Maximum duration seconds.")
        parser_obj.add_argument("--min-bpm", type=float, default=DEFAULT_MIN_BPM, help="Minimum BPM (half-tempo allowed).")
        parser_obj.add_argument("--max-bpm", type=float, default=DEFAULT_MAX_BPM, help="Maximum BPM.")
        parser_obj.add_argument(
            "--exclude-genres",
            default=DEFAULT_EXCLUDE_GENRES,
            help="Comma-separated genre keywords to exclude.",
        )
        parser_obj.add_argument(
            "--exclude-title-keywords",
            default=DEFAULT_EXCLUDE_TITLE_KEYWORDS,
            help="Comma-separated title/album keywords to exclude (e.g. mixed).",
        )

    build_cmd = sub.add_parser("build", help="Build missing-ISRC M3U from DB.")
    add_common(build_cmd)
    build_cmd.set_defaults(func=cmd_build)

    run_cmd = sub.add_parser("run", help="Run OneTagger for an existing M3U via symlink batch.")
    run_cmd.add_argument("--m3u", required=True, help="Input M3U path.")
    run_cmd.add_argument("--db", help="Path to tagslut SQLite DB.")
    run_cmd.add_argument("--onetagger-bin", default=str(DEFAULT_ONETAGGER_BIN), help="OneTagger CLI binary path.")
    run_cmd.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Generated OneTagger config path.")
    run_cmd.add_argument("--base-config", default=str(DEFAULT_BASE_CONFIG_PATH), help="Base OneTagger config path to copy/merge.")
    run_cmd.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR), help="OneTagger runs directory containing success/failed M3Us.")
    run_cmd.add_argument("--link-root", default=str(DEFAULT_WORK_ROOT), help="Root dir for temporary symlink batches.")
    run_cmd.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for logs/summaries.")
    run_cmd.add_argument("--threads", type=int, default=12, help="OneTagger thread count.")
    run_cmd.add_argument("--limit", type=int, default=0, help="Limit number of files from M3U (0 = all).")
    run_cmd.add_argument("--max-passes", type=int, default=4, help="Retry unresolved ISRC files for N passes.")
    run_cmd.add_argument("--strictness", type=float, default=0.8, help="OneTagger strictness.")
    run_cmd.add_argument(
        "--platforms",
        default="beatport,tidal,traxsource,deezer",
        help="Comma-separated providers for ISRC lookup.",
    )
    run_cmd.add_argument(
        "--db-refresh",
        dest="db_refresh",
        action="store_true",
        default=True,
        help="Write ISRC back to DB canonical_isrc (default: on).",
    )
    run_cmd.add_argument(
        "--no-db-refresh",
        dest="db_refresh",
        action="store_false",
        help="Do not update DB canonical_isrc.",
    )
    run_cmd.add_argument(
        "--db-refresh-only",
        action="store_true",
        help="Only sync embedded ISRC to DB; skip OneTagger provider passes.",
    )
    run_cmd.set_defaults(func=cmd_run)

    sync_cmd = sub.add_parser("sync", help="Build missing-ISRC M3U then run OneTagger.")
    add_common(sync_cmd)
    sync_cmd.add_argument("--onetagger-bin", default=str(DEFAULT_ONETAGGER_BIN), help="OneTagger CLI binary path.")
    sync_cmd.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Generated OneTagger config path.")
    sync_cmd.add_argument("--base-config", default=str(DEFAULT_BASE_CONFIG_PATH), help="Base OneTagger config path to copy/merge.")
    sync_cmd.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR), help="OneTagger runs directory containing success/failed M3Us.")
    sync_cmd.add_argument("--link-root", default=str(DEFAULT_WORK_ROOT), help="Root dir for temporary symlink batches.")
    sync_cmd.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for logs/summaries.")
    sync_cmd.add_argument("--threads", type=int, default=12, help="OneTagger thread count.")
    sync_cmd.add_argument("--max-passes", type=int, default=4, help="Retry unresolved ISRC files for N passes.")
    sync_cmd.add_argument("--strictness", type=float, default=0.8, help="OneTagger strictness.")
    sync_cmd.add_argument(
        "--platforms",
        default="beatport,tidal,traxsource,deezer",
        help="Comma-separated providers for ISRC lookup.",
    )
    sync_cmd.add_argument(
        "--db-refresh",
        dest="db_refresh",
        action="store_true",
        default=True,
        help="Write ISRC back to DB canonical_isrc (default: on).",
    )
    sync_cmd.add_argument(
        "--no-db-refresh",
        dest="db_refresh",
        action="store_false",
        help="Do not update DB canonical_isrc.",
    )
    sync_cmd.add_argument(
        "--db-refresh-only",
        action="store_true",
        help="Only sync embedded ISRC to DB; skip OneTagger provider passes.",
    )
    sync_cmd.add_argument(
        "--metadata-after-isrc",
        dest="metadata_after_isrc",
        action="store_true",
        default=False,
        help="Run metadata tagging pass on ISRC-verified files after ISRC pass.",
    )
    sync_cmd.add_argument(
        "--no-metadata-after-isrc",
        dest="metadata_after_isrc",
        action="store_false",
        help="Disable metadata tagging after ISRC pass.",
    )
    sync_cmd.add_argument(
        "--metadata-config",
        default=str(DEFAULT_METADATA_CONFIG_PATH),
        help="Metadata OneTagger config path.",
    )
    sync_cmd.add_argument(
        "--metadata-tags",
        default=DEFAULT_METADATA_TAGS,
        help="Comma-separated metadata tags to write.",
    )
    sync_cmd.add_argument(
        "--metadata-platforms",
        default=DEFAULT_METADATA_PLATFORMS,
        help="Comma-separated metadata platforms.",
    )
    sync_cmd.add_argument(
        "--metadata-strictness",
        type=float,
        default=DEFAULT_METADATA_STRICTNESS,
        help="Metadata strictness (0.0 - 1.0).",
    )
    sync_cmd.add_argument(
        "--metadata-max-duration-diff",
        type=int,
        default=DEFAULT_METADATA_MAX_DURATION_DIFF,
        help="Metadata max duration difference (seconds).",
    )
    sync_cmd.set_defaults(func=cmd_sync)

    audio_cmd = sub.add_parser("audiofeatures", help="Run audio features tagging.")
    audio_cmd.add_argument("--path", default=str(DEFAULT_AUDIOFEATURES_PATH), help="Path to music files or M3U.")
    audio_cmd.add_argument("--mode", choices=["lexicon", "spotify"], default="lexicon", help="Audio features source.")
    audio_cmd.add_argument("--limit", type=int, default=0, help="Limit number of files (0 = all).")
    audio_cmd.add_argument("--db", help="Path to tagslut SQLite DB (lexicon mode).")
    audio_cmd.add_argument("--no-write-tags", action="store_true", help="Do not write tags (lexicon mode).")
    audio_cmd.add_argument("--overwrite-tags", action="store_true", help="Overwrite existing 1T_* tags (lexicon mode).")
    audio_cmd.add_argument("--no-require-bpm-or-genre", action="store_true", help="Allow lexicon even without BPM/genre.")

    audio_cmd.add_argument("--onetagger-bin", default=str(DEFAULT_ONETAGGER_BIN), help="OneTagger CLI binary path.")
    audio_cmd.add_argument("--audiofeatures-config", default=str(DEFAULT_AUDIOFEATURES_CONFIG_PATH), help="Audio features config path.")
    audio_cmd.add_argument("--base-config", default=str(DEFAULT_BASE_CONFIG_PATH), help="Base OneTagger config path with Spotify creds.")
    audio_cmd.add_argument("--spotify-client-id", default="", help="Spotify Client ID (optional).")
    audio_cmd.add_argument("--spotify-client-secret", default="", help="Spotify Client Secret (optional).")
    audio_cmd.add_argument("--no-subfolders", action="store_true", help="Do not include subfolders.")
    audio_cmd.add_argument("--properties", default="energy,danceability", help="Comma-separated audio features to enable.")
    audio_cmd.add_argument("--enable-all", action="store_true", help="Enable all audio features in config.")
    audio_cmd.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for logs.")
    audio_cmd.set_defaults(func=cmd_audiofeatures)

    metadata_cmd = sub.add_parser("metadata", help="Run OneTagger metadata tagging.")
    metadata_cmd.add_argument("--path", default=str(DEFAULT_METADATA_PATH), help="Path to music files or M3U.")
    metadata_cmd.add_argument("--onetagger-bin", default=str(DEFAULT_ONETAGGER_BIN), help="OneTagger CLI binary path.")
    metadata_cmd.add_argument("--metadata-config", default=str(DEFAULT_METADATA_CONFIG_PATH), help="Metadata config path.")
    metadata_cmd.add_argument("--base-config", default=str(DEFAULT_BASE_CONFIG_PATH), help="Base OneTagger config path.")
    metadata_cmd.add_argument("--threads", type=int, default=12, help="OneTagger thread count.")
    metadata_cmd.add_argument("--link-root", default=str(DEFAULT_WORK_ROOT), help="Root dir for temporary symlink batches.")
    metadata_cmd.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for logs.")
    metadata_cmd.add_argument("--limit", type=int, default=0, help="Limit number of files (0 = all).")
    metadata_cmd.add_argument(
        "--metadata-tags",
        default=DEFAULT_METADATA_TAGS,
        help="Comma-separated metadata tags to write.",
    )
    metadata_cmd.add_argument(
        "--metadata-platforms",
        default=DEFAULT_METADATA_PLATFORMS,
        help="Comma-separated metadata platforms.",
    )
    metadata_cmd.add_argument(
        "--metadata-strictness",
        type=float,
        default=DEFAULT_METADATA_STRICTNESS,
        help="Metadata strictness (0.0 - 1.0).",
    )
    metadata_cmd.add_argument(
        "--metadata-max-duration-diff",
        type=int,
        default=DEFAULT_METADATA_MAX_DURATION_DIFF,
        help="Metadata max duration difference (seconds).",
    )
    metadata_cmd.add_argument(
        "--require-isrc",
        dest="require_isrc",
        action="store_true",
        default=True,
        help="Only tag files with ISRC present (default).",
    )
    metadata_cmd.add_argument(
        "--no-require-isrc",
        dest="require_isrc",
        action="store_false",
        help="Allow tagging files without ISRC.",
    )
    metadata_cmd.set_defaults(func=cmd_metadata)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
