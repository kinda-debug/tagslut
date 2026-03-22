from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from mutagen.easyid3 import EasyID3

from tagslut.exec.transcoder import TranscodeError, transcode_to_mp3, transcode_to_mp3_from_snapshot
from tagslut.storage.v3 import (
    record_provenance_event,
    resolve_asset_id_by_path,
    resolve_dj_tag_snapshot_for_path,
)
from tagslut.storage.v3.dj_exports import resolve_latest_dj_export_path


def _normalize_text(value: str | None) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _artist_token_key(value: str | None) -> tuple[str, ...]:
    text = _normalize_text(value)
    if not text:
        return ()
    parts = re.split(r"\s*(?:,|&|/|\+| feat\.? | featuring )\s*", text)
    clean = sorted({part.strip() for part in parts if part.strip()})
    return tuple(clean)


def _safe_m3u_name(value: str) -> str:
    text = _normalize_text(value)
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "playlist"


def _is_inside(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _path_exists(value: str | None) -> bool:
    return bool(value) and Path(value).expanduser().exists()


@dataclass(frozen=True)
class PrecheckSkipRow:
    playlist_index: int
    title: str
    artist: str
    album: str
    isrc: str
    db_path: str


@dataclass(frozen=True)
class ResolvedRow:
    playlist_index: int
    title: str
    artist: str
    album: str
    isrc: str
    db_path: str
    mp3_path: str
    source_path: str
    resolution: str


@dataclass(frozen=True)
class UnresolvedRow:
    playlist_index: int
    title: str
    artist: str
    album: str
    isrc: str
    db_path: str
    reason: str


def _load_skip_rows(decisions_csv: Path) -> list[PrecheckSkipRow]:
    rows: list[PrecheckSkipRow] = []
    with decisions_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            decision = (raw.get("decision") or raw.get("action") or "").strip().lower()
            if decision != "skip":
                continue
            playlist_index_raw = (raw.get("playlist_index") or "").strip() or "0"
            rows.append(
                PrecheckSkipRow(
                    playlist_index=int(playlist_index_raw),
                    title=(raw.get("title") or "").strip(),
                    artist=(raw.get("artist") or "").strip(),
                    album=(raw.get("album") or "").strip(),
                    isrc=(raw.get("isrc") or "").strip(),
                    db_path=(raw.get("db_path") or "").strip(),
                )
            )
    return rows


def _read_mp3_tag(path: Path) -> tuple[str, str, str]:
    try:
        tags = EasyID3(str(path))
    except Exception:
        return "", "", ""
    title = (tags.get("title") or [""])[0]
    artist = (tags.get("artist") or [""])[0]
    album = (tags.get("album") or [""])[0]
    return title, artist, album


class _DjTagIndex:
    def __init__(self, dj_root: Path) -> None:
        self._dj_root = dj_root.expanduser().resolve()
        self._exact: dict[tuple[str, str, str], list[Path]] = {}
        self._loose: dict[tuple[str, tuple[str, ...], str], list[Path]] = {}
        self._title_artist: dict[tuple[str, tuple[str, ...]], list[Path]] = {}

    def build(self) -> None:
        if not self._dj_root.exists():
            return
        for mp3_path in sorted(self._dj_root.rglob("*.mp3")):
            title, artist, album = _read_mp3_tag(mp3_path)
            if not title and not artist:
                continue
            resolved_path = mp3_path.expanduser().resolve()
            exact_key = (_normalize_text(title), _normalize_text(artist), _normalize_text(album))
            loose_key = (_normalize_text(title), _artist_token_key(artist), _normalize_text(album))
            title_artist_key = (_normalize_text(title), _artist_token_key(artist))
            self._exact.setdefault(exact_key, []).append(resolved_path)
            self._loose.setdefault(loose_key, []).append(resolved_path)
            self._title_artist.setdefault(title_artist_key, []).append(resolved_path)

    def _rank(self, path: Path) -> tuple[int, str]:
        unresolved_root = self._dj_root / "_UNRESOLVED"
        if _is_inside(unresolved_root, path):
            return (1, str(path))
        if _is_inside(self._dj_root, path):
            return (0, str(path))
        return (9, str(path))

    def best_match(self, row: PrecheckSkipRow) -> Path | None:
        exact_key = (_normalize_text(row.title), _normalize_text(row.artist), _normalize_text(row.album))
        exact_matches = self._exact.get(exact_key, [])
        if exact_matches:
            return min(exact_matches, key=self._rank)

        loose_key = (_normalize_text(row.title), _artist_token_key(row.artist), _normalize_text(row.album))
        loose_matches = self._loose.get(loose_key, [])
        if loose_matches:
            return min(loose_matches, key=self._rank)

        title_artist_key = (_normalize_text(row.title), _artist_token_key(row.artist))
        title_artist_matches = self._title_artist.get(title_artist_key, [])
        if len(title_artist_matches) == 1:
            return title_artist_matches[0]
        return None


def _query_exact_row(conn: sqlite3.Connection, db_path: str) -> sqlite3.Row | None:
    if not db_path:
        return None
    return conn.execute(
        """
        SELECT path, dj_pool_path, canonical_title, canonical_artist, canonical_album, canonical_isrc, isrc
        FROM files
        WHERE path = ?
        """,
        (db_path,),
    ).fetchone()


def _rank_inventory_row(row: sqlite3.Row) -> tuple[int, int, str]:
    path = Path(str(row["path"])).expanduser().resolve()
    root_rank = 9
    path_text = str(path)
    if path_text.startswith("/Volumes/MUSIC/MASTER_LIBRARY/"):
        root_rank = 0
    elif path_text.startswith("/Volumes/MUSIC/_work/fix/"):
        root_rank = 1
    elif path_text.startswith("/Volumes/MUSIC/mdl/tidal/"):
        root_rank = 2
    has_dj = 0 if _path_exists(row["dj_pool_path"]) else 1
    return (has_dj, root_rank, path_text)


def _candidate_rows_by_isrc(conn: sqlite3.Connection, isrc: str) -> list[sqlite3.Row]:
    if not isrc:
        return []
    rows = conn.execute(
        """
        SELECT path, dj_pool_path, canonical_title, canonical_artist, canonical_album, canonical_isrc, isrc
        FROM files
        WHERE canonical_isrc = ? OR isrc = ?
        """,
        (isrc, isrc),
    ).fetchall()
    return sorted(rows, key=_rank_inventory_row)


def _candidate_rows_by_meta(conn: sqlite3.Connection, row: PrecheckSkipRow) -> list[sqlite3.Row]:
    if not row.title or not row.artist:
        return []
    exact_rows = conn.execute(
        """
        SELECT path, dj_pool_path, canonical_title, canonical_artist, canonical_album, canonical_isrc, isrc
        FROM files
        WHERE canonical_title = ? COLLATE NOCASE
          AND canonical_artist = ? COLLATE NOCASE
          AND canonical_album = ? COLLATE NOCASE
        """,
        (row.title, row.artist, row.album),
    ).fetchall()
    if exact_rows:
        return sorted(exact_rows, key=_rank_inventory_row)

    loose_rows = conn.execute(
        """
        SELECT path, dj_pool_path, canonical_title, canonical_artist, canonical_album, canonical_isrc, isrc
        FROM files
        WHERE canonical_title = ? COLLATE NOCASE
          AND canonical_album = ? COLLATE NOCASE
        """,
        (row.title, row.album),
    ).fetchall()
    filtered = [
        item
        for item in loose_rows
        if _artist_token_key(item["canonical_artist"]) == _artist_token_key(row.artist)
    ]
    return sorted(filtered, key=_rank_inventory_row)


def _resolve_existing_mp3(
    conn: sqlite3.Connection,
    row: PrecheckSkipRow,
    dj_index: _DjTagIndex,
) -> tuple[Path | None, str, str]:
    exact = _query_exact_row(conn, row.db_path)
    if exact is not None:
        latest = resolve_latest_dj_export_path(conn, source_path=row.db_path)
        if latest is not None and latest.exists():
            return latest.resolve(), row.db_path, "db_provenance_dj_export"
        if _path_exists(exact["dj_pool_path"]):
            return Path(str(exact["dj_pool_path"])).expanduser().resolve(), row.db_path, "db_dj_pool_path"

    for candidate in _candidate_rows_by_isrc(conn, row.isrc):
        candidate_path = str(candidate["path"])
        latest = resolve_latest_dj_export_path(conn, source_path=candidate_path)
        if latest is not None and latest.exists():
            return latest.resolve(), candidate_path, "isrc_provenance_dj_export"
        if _path_exists(candidate["dj_pool_path"]):
            return Path(str(candidate["dj_pool_path"])).expanduser().resolve(), candidate_path, "isrc_dj_pool_path"

    dj_match = dj_index.best_match(row)
    if dj_match is not None and dj_match.exists():
        return dj_match.resolve(), row.db_path or "", "dj_tag_match"

    for candidate in _candidate_rows_by_meta(conn, row):
        candidate_path = str(candidate["path"])
        latest = resolve_latest_dj_export_path(conn, source_path=candidate_path)
        if latest is not None and latest.exists():
            return latest.resolve(), candidate_path, "meta_provenance_dj_export"
        if _path_exists(candidate["dj_pool_path"]):
            return Path(str(candidate["dj_pool_path"])).expanduser().resolve(), candidate_path, "meta_dj_pool_path"

    return None, "", ""


def _resolve_source_path(conn: sqlite3.Connection, row: PrecheckSkipRow) -> tuple[Path | None, str]:
    if row.db_path and Path(row.db_path).expanduser().exists():
        return Path(row.db_path).expanduser().resolve(), "db_path_exists"

    for candidate in _candidate_rows_by_isrc(conn, row.isrc):
        candidate_path = Path(str(candidate["path"])).expanduser().resolve()
        if candidate_path.exists():
            return candidate_path, "isrc_live_path"

    for candidate in _candidate_rows_by_meta(conn, row):
        candidate_path = Path(str(candidate["path"])).expanduser().resolve()
        if candidate_path.exists():
            return candidate_path, "meta_live_path"

    return None, ""


def _record_dj_export(
    conn: sqlite3.Connection,
    *,
    source_path: Path,
    dest_path: Path,
    identity_id: int | None,
    snapshot_dict: dict[str, object] | None,
    partial_metadata: bool,
) -> None:
    record_provenance_event(
        conn,
        event_type="dj_export",
        status="success",
        asset_id=resolve_asset_id_by_path(conn, source_path),
        identity_id=identity_id,
        source_path=str(source_path),
        dest_path=str(dest_path),
        details={
            "format": "mp3",
            "bitrate": 320,
            "tool_version": "precheck_inventory_dj",
            "partial_metadata": partial_metadata,
            "tag_snapshot": snapshot_dict,
        },
    )


def _write_playlist(path: Path, rows: Iterable[ResolvedRow]) -> int:
    count = 0
    lines = ["#EXTM3U"]
    for row in sorted(rows, key=lambda item: item.playlist_index):
        mp3_path = Path(row.mp3_path).expanduser().resolve()
        title, artist, _album = _read_mp3_tag(mp3_path)
        label_artist = artist.strip() or row.artist
        label_title = title.strip() or row.title
        lines.append(f"#EXTINF:-1,{label_artist} - {label_title}")
        lines.append(str(mp3_path))
        count += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


def link_precheck_inventory_to_dj(
    *,
    db_path: Path,
    decisions_csv: Path,
    dj_root: Path,
    playlist_dir: Path,
    playlist_base_name: str,
    artifact_dir: Path | None = None,
) -> dict[str, object]:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    skip_rows = _load_skip_rows(decisions_csv)
    dj_root = dj_root.expanduser().resolve()
    playlist_dir = playlist_dir.expanduser().resolve()
    artifact_dir = artifact_dir.expanduser().resolve() if artifact_dir is not None else None
    dj_index = _DjTagIndex(dj_root)
    dj_index.build()

    resolved_rows: list[ResolvedRow] = []
    unresolved_rows: list[UnresolvedRow] = []
    existing_count = 0
    transcode_count = 0

    unresolved_export_root = dj_root / "_UNRESOLVED" / "precheck_inventory_link"

    try:
        for row in sorted(skip_rows, key=lambda item: item.playlist_index):
            existing_mp3, source_hint, resolution = _resolve_existing_mp3(conn, row, dj_index)
            if existing_mp3 is not None:
                resolved_rows.append(
                    ResolvedRow(
                        playlist_index=row.playlist_index,
                        title=row.title,
                        artist=row.artist,
                        album=row.album,
                        isrc=row.isrc,
                        db_path=row.db_path,
                        mp3_path=str(existing_mp3),
                        source_path=source_hint,
                        resolution=resolution,
                    )
                )
                if row.db_path:
                    conn.execute(
                        "UPDATE files SET dj_pool_path = ? WHERE path = ?",
                        (str(existing_mp3), row.db_path),
                    )
                existing_count += 1
                continue

            source_path, source_resolution = _resolve_source_path(conn, row)
            if source_path is None:
                unresolved_rows.append(
                    UnresolvedRow(
                        playlist_index=row.playlist_index,
                        title=row.title,
                        artist=row.artist,
                        album=row.album,
                        isrc=row.isrc,
                        db_path=row.db_path,
                        reason="no_existing_mp3_or_live_source",
                    )
                )
                continue

            try:
                snapshot = resolve_dj_tag_snapshot_for_path(
                    conn,
                    source_path,
                    run_essentia=False,
                    dry_run=True,
                )
                if snapshot is not None:
                    mp3_path = transcode_to_mp3_from_snapshot(
                        source_path,
                        unresolved_export_root,
                        snapshot,
                        bitrate=320,
                        overwrite=False,
                    )
                    _record_dj_export(
                        conn,
                        source_path=source_path,
                        dest_path=mp3_path.expanduser().resolve(),
                        identity_id=snapshot.identity_id,
                        snapshot_dict=snapshot.as_dict(),
                        partial_metadata=any(
                            value is None
                            for value in (snapshot.bpm, snapshot.musical_key, snapshot.energy_1_10)
                        ),
                    )
                else:
                    mp3_path = transcode_to_mp3(
                        source_path,
                        unresolved_export_root,
                        bitrate=320,
                        overwrite=False,
                    )
                    _record_dj_export(
                        conn,
                        source_path=source_path,
                        dest_path=mp3_path.expanduser().resolve(),
                        identity_id=None,
                        snapshot_dict=None,
                        partial_metadata=True,
                    )
            except (FileNotFoundError, TranscodeError) as exc:
                unresolved_rows.append(
                    UnresolvedRow(
                        playlist_index=row.playlist_index,
                        title=row.title,
                        artist=row.artist,
                        album=row.album,
                        isrc=row.isrc,
                        db_path=row.db_path,
                        reason=f"{source_resolution}:{exc}",
                    )
                )
                continue

            resolved_rows.append(
                ResolvedRow(
                    playlist_index=row.playlist_index,
                    title=row.title,
                    artist=row.artist,
                    album=row.album,
                    isrc=row.isrc,
                    db_path=row.db_path,
                    mp3_path=str(mp3_path.expanduser().resolve()),
                    source_path=str(source_path),
                    resolution=source_resolution,
                )
            )
            if row.db_path:
                conn.execute(
                    "UPDATE files SET dj_pool_path = ? WHERE path = ?",
                    (str(mp3_path.expanduser().resolve()), row.db_path),
                )
            transcode_count += 1

        conn.commit()
    finally:
        conn.close()

    playlist_path = playlist_dir / f"{playlist_base_name}.m3u"
    written_count = _write_playlist(playlist_path, resolved_rows)

    summary: dict[str, object] = {
        "decisions_csv": str(decisions_csv),
        "playlist_path": str(playlist_path),
        "playlist_name": playlist_base_name,
        "skip_rows": len(skip_rows),
        "resolved_rows": len(resolved_rows),
        "playlist_rows_written": written_count,
        "existing_mp3_rows": existing_count,
        "transcoded_rows": transcode_count,
        "unresolved_rows": len(unresolved_rows),
    }

    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        resolved_csv = artifact_dir / "resolved_rows.csv"
        with resolved_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "playlist_index",
                    "title",
                    "artist",
                    "album",
                    "isrc",
                    "db_path",
                    "mp3_path",
                    "source_path",
                    "resolution",
                ],
            )
            writer.writeheader()
            for item in sorted(resolved_rows, key=lambda row: row.playlist_index):
                writer.writerow(asdict(item))

        unresolved_csv = artifact_dir / "unresolved_rows.csv"
        with unresolved_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "playlist_index",
                    "title",
                    "artist",
                    "album",
                    "isrc",
                    "db_path",
                    "reason",
                ],
            )
            writer.writeheader()
            for item in sorted(unresolved_rows, key=lambda row: row.playlist_index):
                writer.writerow(asdict(item))

        playlist_inputs = artifact_dir / "playlist_inputs.txt"
        playlist_inputs.write_text(
            "\n".join(item.mp3_path for item in sorted(resolved_rows, key=lambda row: row.playlist_index))
            + ("\n" if resolved_rows else ""),
            encoding="utf-8",
        )

        summary["artifact_dir"] = str(artifact_dir)
        summary["resolved_csv"] = str(resolved_csv)
        summary["unresolved_csv"] = str(unresolved_csv)
        summary["playlist_inputs"] = str(playlist_inputs)
        (artifact_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Link precheck skip matches to DJ_LIBRARY MP3s.")
    parser.add_argument("--db", required=True, help="SQLite DB path")
    parser.add_argument("--decisions-csv", required=True, help="precheck_decisions CSV path")
    parser.add_argument("--dj-root", required=True, help="DJ MP3 root")
    parser.add_argument("--playlist-dir", required=True, help="Directory to write DJ playlist")
    parser.add_argument("--playlist-base-name", required=False, help="Playlist basename without extension")
    parser.add_argument("--playlist-title", required=False, help="Human title used to derive basename")
    parser.add_argument("--artifact-dir", required=False, help="Optional artifact directory")
    args = parser.parse_args()

    playlist_base_name = (args.playlist_base_name or "").strip()
    if not playlist_base_name:
        playlist_title = (args.playlist_title or "").strip() or Path(args.decisions_csv).stem
        playlist_base_name = f"dj-{_safe_m3u_name(playlist_title)}"

    summary = link_precheck_inventory_to_dj(
        db_path=Path(args.db).expanduser().resolve(),
        decisions_csv=Path(args.decisions_csv).expanduser().resolve(),
        dj_root=Path(args.dj_root).expanduser().resolve(),
        playlist_dir=Path(args.playlist_dir).expanduser().resolve(),
        playlist_base_name=playlist_base_name,
        artifact_dir=Path(args.artifact_dir).expanduser().resolve() if args.artifact_dir else None,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
