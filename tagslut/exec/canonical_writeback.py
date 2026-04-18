"""Canonical FLAC tag writeback.

Reads linked `track_identity.canonical_*` fields first and falls back to
`files.canonical_*` mirrors when identity fields are blank. Existing FLAC tags
are preserved unless `force=True`.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

from mutagen.flac import FLAC

from tagslut.metadata.genre_normalization import default_genre_normalizer


@dataclass(frozen=True)
class CanonicalWritebackStats:
    scanned: int
    updated: int
    skipped: int
    missing: int


def iter_flacs_from_root(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    yield from root.rglob("*.flac")


def iter_flacs_from_m3u(m3u_path: Path) -> Iterable[Path]:
    for raw in m3u_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        path = Path(line)
        if path.suffix.lower() == ".flac":
            yield path


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row[1]) == column_name for row in rows)


def _canonical_row_for_path(conn: sqlite3.Connection, path: Path) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    active_join = "AND al.active = 1" if _column_exists(conn, "asset_link", "active") else ""
    merged_join = "AND ti.merged_into_id IS NULL" if _column_exists(conn, "track_identity", "merged_into_id") else ""
    return conn.execute(
        f"""
        SELECT
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_artist AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_artist AS TEXT)), '')) AS canonical_artist,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_title AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_title AS TEXT)), '')) AS canonical_title,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_album AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_album AS TEXT)), '')) AS canonical_album,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_genre AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_genre AS TEXT)), '')) AS canonical_genre,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_sub_genre AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_sub_genre AS TEXT)), '')) AS canonical_sub_genre,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_label AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_label AS TEXT)), '')) AS canonical_label,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_catalog_number AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_catalog_number AS TEXT)), '')) AS canonical_catalog_number,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_year AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_year AS TEXT)), '')) AS canonical_year,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_release_date AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_release_date AS TEXT)), '')) AS canonical_release_date,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_bpm AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_bpm AS TEXT)), '')) AS canonical_bpm,
            COALESCE(NULLIF(TRIM(CAST(ti.canonical_key AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_key AS TEXT)), '')) AS canonical_key,
            COALESCE(NULLIF(TRIM(CAST(ti.isrc AS TEXT)), ''), NULLIF(TRIM(CAST(f.canonical_isrc AS TEXT)), '')) AS isrc,
            COALESCE(NULLIF(TRIM(CAST(ti.beatport_id AS TEXT)), ''), NULLIF(TRIM(CAST(f.beatport_id AS TEXT)), '')) AS beatport_id
        FROM files f
        LEFT JOIN asset_file af ON af.path = f.path
        LEFT JOIN asset_link al ON al.asset_id = af.id {active_join}
        LEFT JOIN track_identity ti ON ti.id = al.identity_id {merged_join}
        WHERE f.path = ?
        ORDER BY al.id ASC
        LIMIT 1
        """,
        (str(path),),
    ).fetchone()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _latest_provider_payload_for_path(
    conn: sqlite3.Connection,
    path: Path,
    *,
    service: str,
) -> dict | None:
    if not (_table_exists(conn, "files") and _table_exists(conn, "library_track_sources")):
        return None

    # Support both schema variants:
    # - files.library_track_key <-> library_track_sources.library_track_key + service
    # - files.library_track_key <-> library_track_sources.identity_key + provider
    if _column_exists(conn, "library_track_sources", "library_track_key"):
        source_key_col = "library_track_key"
    elif _column_exists(conn, "library_track_sources", "identity_key"):
        source_key_col = "identity_key"
    else:
        return None

    if _column_exists(conn, "library_track_sources", "service"):
        source_provider_col = "service"
    elif _column_exists(conn, "library_track_sources", "provider"):
        source_provider_col = "provider"
    else:
        return None

    conn.row_factory = sqlite3.Row
    row = conn.execute(
        f"""
        SELECT lts.metadata_json
        FROM files f
        JOIN library_track_sources lts ON lts.{source_key_col} = f.library_track_key
        WHERE f.path = ? AND lts.{source_provider_col} = ?
        ORDER BY lts.fetched_at DESC, lts.id DESC
        LIMIT 1
        """,
        (str(path), service),
    ).fetchone()
    if row is None:
        return None

    raw_json = row["metadata_json"]
    if not raw_json:
        return None
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _nested(payload: dict | None, *keys: str) -> object:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _beatport_payload_tags(payload: dict | None) -> dict[str, str]:
    if not payload:
        return {}

    release = _nested(payload, "_release")
    if not isinstance(release, dict):
        release = _nested(payload, "release")
    release = release if isinstance(release, dict) else {}

    label = _nested(payload, "label")
    if not isinstance(label, dict):
        label = _nested(release, "label")
    label = label if isinstance(label, dict) else {}

    track_id = _as_text(payload.get("id") or payload.get("track_id"))
    track_url = _as_text(payload.get("url") or payload.get("track_url"))
    release_id = _as_text(release.get("id") or release.get("release_id") or payload.get("release_id"))
    release_url = _as_text(release.get("url") or release.get("release_url") or payload.get("release_url"))
    label_url = _as_text(label.get("url") or payload.get("label_url"))
    upc = _as_text(release.get("upc") or payload.get("upc") or release.get("barcode") or payload.get("barcode"))
    catalog_number = _as_text(release.get("catalog_number") or payload.get("catalog_number"))
    preview_url = _as_text(payload.get("preview_url") or payload.get("sample_url"))
    waveform_url = _as_text(payload.get("waveform_url"))
    mix_name = _as_text(payload.get("mix_name") or payload.get("mixName"))
    genre = _as_text(_nested(payload, "genre", "name") or payload.get("genre_name") or payload.get("genre"))
    subgenre = _as_text(
        _nested(payload, "sub_genre", "name")
        or payload.get("sub_genre_name")
        or payload.get("subgenre")
    )

    tags: dict[str, str] = {}
    if track_id:
        tags["TRACK_ID"] = track_id
        tags["BEATPORT_TRACK_ID"] = track_id
    if track_url:
        tags["TRACK_URL"] = track_url
        tags["BEATPORT_TRACK_URL"] = track_url
    if release_id:
        tags["RELEASE_ID"] = release_id
        tags["BEATPORT_RELEASE_ID"] = release_id
    if release_url:
        tags["RELEASE_URL"] = release_url
        tags["BEATPORT_RELEASE_URL"] = release_url
    if label_url:
        tags["LABEL_URL"] = label_url
        tags["BEATPORT_LABEL_URL"] = label_url
    if upc:
        tags["UPC"] = upc
        tags["BEATPORT_UPC"] = upc
    if catalog_number:
        tags["CATALOGNUMBER"] = catalog_number
    if preview_url:
        tags["PREVIEW_URL"] = preview_url
    if waveform_url:
        tags["WAVEFORM_URL"] = waveform_url
    if mix_name:
        tags["MIXNAME"] = mix_name
    if genre:
        tags["BEATPORT_GENRE"] = genre
    if subgenre:
        tags["BEATPORT_SUBGENRE"] = subgenre

    return tags


def _tidal_payload_tags(payload: dict | None) -> dict[str, str]:
    if not payload:
        return {}

    attributes = _nested(payload, "attributes")
    attributes = attributes if isinstance(attributes, dict) else payload

    track_id = _as_text(payload.get("id"))
    isrc = _as_text(attributes.get("isrc") if isinstance(attributes, dict) else None)
    bpm = _as_text(attributes.get("bpm") if isinstance(attributes, dict) else None)
    key = _as_text(attributes.get("key") if isinstance(attributes, dict) else None)
    key_scale = _as_text(attributes.get("keyScale") if isinstance(attributes, dict) else None)
    replay_gain_track = _as_text(attributes.get("replayGainTrack") if isinstance(attributes, dict) else None)
    replay_gain_album = _as_text(attributes.get("replayGainAlbum") if isinstance(attributes, dict) else None)
    explicit = _as_text(attributes.get("explicit") if isinstance(attributes, dict) else None)
    popularity = _as_text(attributes.get("popularity") if isinstance(attributes, dict) else None)
    copyright_text = _as_text(attributes.get("copyright") if isinstance(attributes, dict) else None)
    tone_tags = None
    if isinstance(attributes, dict):
        raw_tones = attributes.get("toneTags")
        if isinstance(raw_tones, list):
            compact = [str(item).strip() for item in raw_tones if str(item).strip()]
            if compact:
                tone_tags = ",".join(compact)
    audio_quality = None
    if isinstance(attributes, dict):
        media_tags = attributes.get("mediaTags")
        if isinstance(media_tags, list):
            compact = [str(item).strip() for item in media_tags if str(item).strip()]
            if compact:
                audio_quality = ",".join(compact)

    lyrics_text = _as_text(payload.get("_lyrics") or payload.get("lyrics") or payload.get("subtitles"))

    tags: dict[str, str] = {}
    if track_id:
        tags["TIDAL_TRACK_ID"] = track_id
        tags["TIDAL_URL"] = f"https://tidal.com/browse/track/{track_id}"
    if isrc:
        tags["TIDAL_ISRC"] = isrc
    if bpm:
        tags["TIDAL_BPM"] = bpm
    if key:
        tags["TIDAL_KEY"] = key
    if key_scale:
        tags["TIDAL_KEYSCALE"] = key_scale
    if replay_gain_track:
        tags["REPLAYGAIN_TRACK_GAIN"] = replay_gain_track
    if replay_gain_album:
        tags["REPLAYGAIN_ALBUM_GAIN"] = replay_gain_album
    if audio_quality:
        tags["TIDAL_MEDIA_TAGS"] = audio_quality
    if explicit:
        tags["TIDAL_EXPLICIT"] = explicit
    if popularity:
        tags["TIDAL_POPULARITY"] = popularity
    if tone_tags:
        tags["TIDAL_TONE_TAGS"] = tone_tags
    if copyright_text:
        tags["COPYRIGHT"] = copyright_text
    if lyrics_text:
        tags["LYRICS"] = lyrics_text

    return tags


def _tag_exists(tags: object, key: str) -> bool:
    if tags is None:
        return False
    return key in tags and bool(tags[key])  # type: ignore[index]


def _set_tag(tags: object, key: str, value: str) -> None:
    tags[key] = [value]  # type: ignore[index]


def write_canonical_tags(
    conn: sqlite3.Connection,
    sources: Sequence[Path],
    *,
    force: bool = False,
    execute: bool = False,
    progress_interval: int = 100,
    echo: Callable[[str], None] | None = None,
) -> CanonicalWritebackStats:
    updated = 0
    skipped = 0
    missing = 0

    for idx, path in enumerate(sources, start=1):
        resolved = path.expanduser().resolve()
        if not resolved.exists():
            missing += 1
            if echo is not None and progress_interval > 0 and idx % progress_interval == 0:
                echo(f"Writeback {idx}/{len(sources)} updated={updated} skipped={skipped} missing={missing}")
            continue

        row = _canonical_row_for_path(conn, resolved)
        if row is None:
            skipped += 1
            if echo is not None and progress_interval > 0 and idx % progress_interval == 0:
                echo(f"Writeback {idx}/{len(sources)} updated={updated} skipped={skipped} missing={missing}")
            continue

        audio = FLAC(resolved)
        tags = audio.tags
        updates: list[str] = []

        def maybe_set(tag_key: str, value: object) -> None:
            if value in (None, ""):
                return
            if force or not _tag_exists(tags, tag_key):
                _set_tag(tags, tag_key, str(value))
                updates.append(tag_key)

        maybe_set("ARTIST", row["canonical_artist"])
        maybe_set("TITLE", row["canonical_title"])
        maybe_set("ALBUM", row["canonical_album"])

        date_value = row["canonical_release_date"] or row["canonical_year"]
        if date_value is not None:
            maybe_set("DATE", date_value)

        maybe_set("ISRC", row["isrc"])
        maybe_set("LABEL", row["canonical_label"])
        maybe_set("CATALOGNUMBER", row["canonical_catalog_number"])
        maybe_set("BEATPORT_TRACK_ID", row["beatport_id"])
        maybe_set("BPM", row["canonical_bpm"])
        maybe_set("INITIALKEY", row["canonical_key"])

        genre, sub_genre = default_genre_normalizer().normalize_pair(
            row["canonical_genre"],
            row["canonical_sub_genre"],
        )
        maybe_set("GENRE", genre)
        maybe_set("SUBGENRE", sub_genre)
        if genre and sub_genre:
            maybe_set("GENRE_FULL", f"{genre} | {sub_genre}")
            maybe_set("GENRE_PREFERRED", sub_genre)

        beatport_payload = _latest_provider_payload_for_path(conn, resolved, service="beatport")
        for tag_key, tag_value in _beatport_payload_tags(beatport_payload).items():
            maybe_set(tag_key, tag_value)

        tidal_payload = _latest_provider_payload_for_path(conn, resolved, service="tidal")
        for tag_key, tag_value in _tidal_payload_tags(tidal_payload).items():
            maybe_set(tag_key, tag_value)

        if updates:
            if execute:
                audio.save()
            updated += 1
        else:
            skipped += 1

        if echo is not None and progress_interval > 0 and idx % progress_interval == 0:
            echo(f"Writeback {idx}/{len(sources)} updated={updated} skipped={skipped} missing={missing}")

    return CanonicalWritebackStats(scanned=len(sources), updated=updated, skipped=skipped, missing=missing)
