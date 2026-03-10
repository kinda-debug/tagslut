from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from mutagen import File as MutagenFile
from mutagen.flac import FLAC

from tagslut.exec.dj_tag_snapshot import DjTagSnapshot
from tagslut.storage.v3 import record_provenance_event, resolve_asset_id_by_path, resolve_dj_tag_snapshot_for_path
from tagslut.utils.final_library_layout import (
    FinalLibraryLayoutError,
    build_final_library_destination,
    sanitize_component,
)
from tagslut.utils.paths import list_files

DEFAULT_DURATION_TOLERANCE = 2.0
CORE_TAG_FIELDS = ("title", "artist", "album", "albumartist", "date", "tracknumber")
PLAYLIST_EXTENSIONS = {".m3u", ".m3u8"}


@dataclass(frozen=True)
class AudioMetadata:
    path: Path
    tags: dict[str, list[str]]
    duration_s: float | None

    @property
    def title(self) -> str:
        return first_tag(self.tags, ("title",))

    @property
    def artist(self) -> str:
        return first_tag(self.tags, ("artist",))

    @property
    def album(self) -> str:
        return first_tag(self.tags, ("album",))

    @property
    def albumartist(self) -> str:
        return first_tag(self.tags, ("albumartist", "album artist"))

    @property
    def date(self) -> str:
        return first_tag(self.tags, ("date", "originaldate", "year"))

    @property
    def tracknumber(self) -> str:
        return first_tag(self.tags, ("tracknumber", "track"))


@dataclass(frozen=True)
class DjPoolLookupRow:
    dj_pool_path: Path
    source_path: Path
    identity_id: int | None
    snapshot: DjTagSnapshot | None
    source_metadata: AudioMetadata | None


@dataclass(frozen=True)
class PlannedMoveRow:
    source_path: Path
    dest_path: Path
    reason: str
    bucket: str
    source_flac_path: Path | None = None
    identity_id: int | None = None


@dataclass(frozen=True)
class RepairRow:
    path: Path
    flac_path: Path
    match_source: str
    reason: str
    missing_fields: tuple[str, ...]
    expected_dest_path: Path | None
    identity_id: int | None = None


@dataclass(frozen=True)
class PlaylistRewriteRow:
    playlist_path: Path
    line_number: int
    old_path: str
    new_path: str
    action: str
    reason: str


@dataclass(frozen=True)
class DjPoolRelinkRow:
    source_path: Path
    old_dj_pool_path: Path
    new_dj_pool_path: Path
    identity_id: int | None
    reason: str


@dataclass(frozen=True)
class RelinkStats:
    rows: int
    updated: int
    skipped: int
    errors: int
    playlist_rewrites: int = 0


def _norm(text: str | None) -> str:
    return " ".join((text or "").strip().casefold().split())


def _json_ready_path(path: Path | None) -> str | None:
    return str(path) if path is not None else None


def first_tag(tags: dict[str, list[str]], keys: Iterable[str]) -> str:
    for key in keys:
        values = tags.get(str(key).lower()) or []
        if values:
            value = str(values[0]).strip()
            if value:
                return value
    return ""


def normalize_tags(tags: dict[str, Any] | None) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    if not tags:
        return normalized
    for key, value in tags.items():
        lowered = str(key).lower()
        if isinstance(value, (list, tuple)):
            items = [str(item).strip() for item in value if str(item).strip()]
        else:
            item = str(value).strip()
            items = [item] if item else []
        if items:
            normalized[lowered] = items
    return normalized


def missing_core_fields(tags: dict[str, list[str]]) -> tuple[str, ...]:
    missing: list[str] = []
    if not first_tag(tags, ("title",)):
        missing.append("title")
    if not first_tag(tags, ("artist",)):
        missing.append("artist")
    if not first_tag(tags, ("album",)):
        missing.append("album")
    if not first_tag(tags, ("albumartist", "album artist")):
        missing.append("albumartist")
    if not first_tag(tags, ("date", "originaldate", "year")):
        missing.append("date")
    if not first_tag(tags, ("tracknumber", "track")):
        missing.append("tracknumber")
    return tuple(missing)


def read_audio_metadata(path: Path) -> AudioMetadata | None:
    try:
        audio = MutagenFile(str(path), easy=True)
    except Exception:
        return None
    if audio is None:
        return None

    raw_tags = getattr(audio, "tags", None)
    tags = normalize_tags(raw_tags)
    duration_s: float | None = None
    try:
        info = getattr(audio, "info", None)
        length = getattr(info, "length", None)
        if length is not None:
            duration_s = float(length)
    except Exception:
        duration_s = None
    return AudioMetadata(path=path, tags=tags, duration_s=duration_s)


def build_canonical_mp3_destination(tags: dict[str, list[str]], root: Path) -> Path:
    return build_final_library_destination(tags, root).dest_path.with_suffix(".mp3")


def build_unresolved_destination(
    unresolved_root: Path,
    reason: str,
    source_path: Path,
    *,
    used_destinations: set[Path] | None = None,
) -> Path:
    used_destinations = used_destinations or set()
    reason_dir = sanitize_component(reason) or "unknown_reason"
    dest = unresolved_root / reason_dir / source_path.name
    return dedupe_destination(dest, source_path, used_destinations=used_destinations)


def dedupe_destination(dest: Path, src: Path, *, used_destinations: set[Path] | None = None) -> Path:
    used_destinations = used_destinations or set()
    candidate = dest
    if candidate not in used_destinations and not candidate.exists():
        used_destinations.add(candidate)
        return candidate

    stem = dest.stem
    suffix = dest.suffix
    src_suffix = abs(hash(str(src))) % 100000
    for idx in range(1, 1000):
        name = f"{stem}__dup_{src_suffix}" if idx == 1 else f"{stem}__dup_{src_suffix}_{idx}"
        candidate = dest.with_name(f"{name}{suffix}")
        if candidate not in used_destinations and not candidate.exists():
            used_destinations.add(candidate)
            return candidate
    raise RuntimeError(f"could not allocate deduped path for {src}")


def _samefile(path_a: Path, path_b: Path) -> bool:
    """Best-effort "same file" check to handle macOS normalization/case quirks.

    On case-insensitive or Unicode-normalization-insensitive filesystems, two different
    textual paths can refer to the same inode. We treat those as equivalent for
    canonicalization decisions.
    """
    try:
        return path_a.samefile(path_b)
    except (FileNotFoundError, OSError, ValueError):
        return False


def classify_current_layout(path: Path, tags: dict[str, list[str]], root: Path) -> tuple[str, Path | None, str]:
    try:
        expected = build_canonical_mp3_destination(tags, root)
    except FinalLibraryLayoutError as exc:
        return "incomplete", None, str(exc)
    if expected == path or _samefile(expected, path):
        return "already_canonical", expected, "already_canonical"
    return "move_only", expected, "path_mismatch"


def merge_tags_for_master_repair(
    current_tags: dict[str, list[str]],
    flac_metadata: AudioMetadata,
) -> dict[str, list[str]]:
    merged = {key: list(values) for key, values in current_tags.items()}
    field_map = {
        "title": (flac_metadata.title,),
        "artist": (flac_metadata.artist,),
        "album": (flac_metadata.album,),
        "albumartist": (flac_metadata.albumartist,),
        "date": (flac_metadata.date,),
        "tracknumber": (flac_metadata.tracknumber,),
    }
    for key, candidates in field_map.items():
        if first_tag(merged, (key,)):
            continue
        candidate = next((value for value in candidates if value), "")
        if candidate:
            merged[key] = [candidate]
    return merged


def merge_tags_for_db_repair(
    current_tags: dict[str, list[str]],
    *,
    snapshot: DjTagSnapshot | None,
    flac_metadata: AudioMetadata | None,
) -> dict[str, list[str]]:
    merged = {key: list(values) for key, values in current_tags.items()}
    if not first_tag(merged, ("title",)):
        candidate = (snapshot.title if snapshot is not None else "") or (
            flac_metadata.title if flac_metadata is not None else ""
        )
        if candidate:
            merged["title"] = [candidate]
    if not first_tag(merged, ("artist",)):
        candidate = (snapshot.artist if snapshot is not None else "") or (
            flac_metadata.artist if flac_metadata is not None else ""
        )
        if candidate:
            merged["artist"] = [candidate]
    if not first_tag(merged, ("album",)):
        candidate = (snapshot.album if snapshot is not None else "") or (
            flac_metadata.album if flac_metadata is not None else ""
        )
        if candidate:
            merged["album"] = [candidate]
    if not first_tag(merged, ("albumartist", "album artist")):
        candidate = (
            (flac_metadata.albumartist if flac_metadata is not None else "")
            or (snapshot.artist if snapshot is not None else "")
            or (flac_metadata.artist if flac_metadata is not None else "")
        )
        if candidate:
            merged["albumartist"] = [candidate]
    if not first_tag(merged, ("date", "originaldate", "year")):
        candidate = (
            str(snapshot.year)
            if snapshot is not None and snapshot.year is not None
            else ((flac_metadata.date if flac_metadata is not None else ""))
        )
        if candidate:
            merged["date"] = [candidate]
    if not first_tag(merged, ("tracknumber", "track")) and flac_metadata is not None and flac_metadata.tracknumber:
        merged["tracknumber"] = [flac_metadata.tracknumber]
    return merged


def load_db_dj_pool_lookup(conn: sqlite3.Connection, root: Path) -> dict[Path, DjPoolLookupRow]:
    root_text = str(root.expanduser().resolve())
    if not root_text.endswith("/"):
        root_text += "/"

    rows = conn.execute(
        """
        SELECT path, dj_pool_path
        FROM files
        WHERE dj_pool_path LIKE ?
        """,
        (root_text + "%",),
    ).fetchall()
    lookup: dict[Path, DjPoolLookupRow] = {}
    for source_path_raw, dj_pool_raw in rows:
        dj_pool_path = Path(str(dj_pool_raw)).expanduser().resolve()
        source_path = Path(str(source_path_raw)).expanduser().resolve()
        snapshot: DjTagSnapshot | None = None
        try:
            snapshot = resolve_dj_tag_snapshot_for_path(conn, source_path, run_essentia=False, dry_run=True)
        except Exception:
            snapshot = None
        source_metadata = read_audio_metadata(source_path) if source_path.exists() else None
        lookup[dj_pool_path] = DjPoolLookupRow(
            dj_pool_path=dj_pool_path,
            source_path=source_path,
            identity_id=snapshot.identity_id if snapshot is not None else None,
            snapshot=snapshot,
            source_metadata=source_metadata,
        )
    return lookup


def load_master_index(master_root: Path, wanted_keys: set[tuple[str, str]]) -> dict[tuple[str, str], list[AudioMetadata]]:
    index: dict[tuple[str, str], list[AudioMetadata]] = defaultdict(list)
    if not wanted_keys:
        return index
    for flac_path in list_files(master_root, {".flac"}):
        metadata = read_audio_metadata(flac_path)
        if metadata is None:
            continue
        key = (_norm(metadata.title), _norm(metadata.artist))
        if not key[0] or not key[1] or key not in wanted_keys:
            continue
        index[key].append(metadata)
    return index


def pick_best_master_match(
    mp3_metadata: AudioMetadata,
    candidates: list[AudioMetadata],
    *,
    duration_tol: float,
) -> AudioMetadata | None:
    if not candidates:
        return None
    album = _norm(mp3_metadata.album)
    filtered = candidates
    if album:
        exact_album = [candidate for candidate in filtered if _norm(candidate.album) == album]
        if exact_album:
            filtered = exact_album
    if mp3_metadata.duration_s is not None:
        close = [
            candidate
            for candidate in filtered
            if candidate.duration_s is None or abs(candidate.duration_s - mp3_metadata.duration_s) <= duration_tol
        ]
        if close:
            filtered = close
    return filtered[0] if filtered else None


def plan_playlist_rewrites(
    root: Path,
    move_rows: list[PlannedMoveRow],
    unresolved_rows: list[PlannedMoveRow],
) -> list[PlaylistRewriteRow]:
    rewrite_map = {str(row.source_path): row for row in move_rows}
    unresolved_map = {str(row.source_path): row for row in unresolved_rows}
    rows: list[PlaylistRewriteRow] = []
    for playlist_path in sorted(path for path in root.iterdir() if path.suffix.lower() in PLAYLIST_EXTENSIONS):
        lines = playlist_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for idx, line in enumerate(lines, start=1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            if text in rewrite_map:
                row = rewrite_map[text]
                rows.append(
                    PlaylistRewriteRow(
                        playlist_path=playlist_path,
                        line_number=idx,
                        old_path=text,
                        new_path=str(row.dest_path),
                        action="rewrite",
                        reason=row.reason,
                    )
                )
            elif text in unresolved_map:
                row = unresolved_map[text]
                rows.append(
                    PlaylistRewriteRow(
                        playlist_path=playlist_path,
                        line_number=idx,
                        old_path=text,
                        new_path=str(row.dest_path),
                        action="comment",
                        reason=row.reason,
                    )
                )
    return rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _entry_reason_from_layout_error(message: str) -> str:
    lowered = message.strip().lower()
    if "missing required tag" in lowered or "missing/invalid required tag" in lowered:
        return "missing_core_tags"
    if "path component too long" in lowered:
        return "path_component_too_long"
    return "layout_rejected"


def _load_active_mp3s(root: Path, unresolved_root: Path) -> list[Path]:
    paths = []
    for mp3_path in list_files(root, {".mp3"}):
        resolved = mp3_path.expanduser().resolve()
        try:
            resolved.relative_to(unresolved_root)
        except ValueError:
            paths.append(resolved)
    return sorted(paths)


def _to_move_row_dict(row: PlannedMoveRow) -> dict[str, object]:
    return {
        "source_path": str(row.source_path),
        "dest_path": str(row.dest_path),
        "mode": "move",
        "reason": row.reason,
        "bucket": row.bucket,
        "db_path": str(row.source_flac_path) if row.source_flac_path is not None else "",
        "identity_id": row.identity_id or "",
    }


def _to_repair_row_dict(row: RepairRow) -> dict[str, object]:
    return {
        "path": str(row.path),
        "flac_path": str(row.flac_path),
        "match_source": row.match_source,
        "reason": row.reason,
        "missing_fields": ",".join(row.missing_fields),
        "expected_dest_path": _json_ready_path(row.expected_dest_path) or "",
        "identity_id": row.identity_id or "",
    }


def _to_playlist_row_dict(row: PlaylistRewriteRow) -> dict[str, object]:
    return {
        "playlist_path": str(row.playlist_path),
        "line_number": row.line_number,
        "old_path": row.old_path,
        "new_path": row.new_path,
        "action": row.action,
        "reason": row.reason,
    }


def _to_relink_row_dict(row: DjPoolRelinkRow) -> dict[str, object]:
    return {
        "source_path": str(row.source_path),
        "old_dj_pool_path": str(row.old_dj_pool_path),
        "new_dj_pool_path": str(row.new_dj_pool_path),
        "identity_id": row.identity_id or "",
        "reason": row.reason,
    }


def plan_dj_library_normalize(
    *,
    root: Path,
    master_root: Path,
    conn: sqlite3.Connection,
    out_dir: Path,
    unresolved_root: Path,
    duration_tol: float = DEFAULT_DURATION_TOLERANCE,
) -> dict[str, object]:
    root = root.expanduser().resolve()
    master_root = master_root.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()
    unresolved_root = unresolved_root.expanduser().resolve()

    db_lookup = load_db_dj_pool_lookup(conn, root)
    active_mp3s = _load_active_mp3s(root, unresolved_root)

    metadata_by_path: dict[Path, AudioMetadata | None] = {}
    classification_seed: list[tuple[Path, AudioMetadata | None, str, Path | None, str]] = []
    wanted_master_keys: set[tuple[str, str]] = set()
    bucket_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()

    for mp3_path in active_mp3s:
        metadata = read_audio_metadata(mp3_path)
        metadata_by_path[mp3_path] = metadata
        if metadata is None:
            classification_seed.append((mp3_path, None, "incomplete", None, "tag_read_error"))
            reason_counts["tag_read_error"] += 1
            continue
        status, expected_dest, reason = classify_current_layout(mp3_path, metadata.tags, root)
        classification_seed.append((mp3_path, metadata, status, expected_dest, reason))
        if status == "incomplete":
            if metadata.title and metadata.artist:
                wanted_master_keys.add((_norm(metadata.title), _norm(metadata.artist)))
            reason_counts[_entry_reason_from_layout_error(reason)] += 1

    master_index = load_master_index(master_root, wanted_master_keys)

    move_rows: list[PlannedMoveRow] = []
    repair_master_rows: list[RepairRow] = []
    repair_db_rows: list[RepairRow] = []
    unresolved_rows: list[PlannedMoveRow] = []
    already_canonical = 0
    planned_destinations: set[Path] = set()
    unresolved_destinations: set[Path] = set()

    for mp3_path, metadata, status, expected_dest, reason in classification_seed:
        if status == "already_canonical":
            already_canonical += 1
            bucket_counts["already_canonical"] += 1
            continue

        if status == "move_only" and metadata is not None and expected_dest is not None:
            if _samefile(expected_dest, mp3_path):
                already_canonical += 1
                bucket_counts["already_canonical"] += 1
                continue
            if expected_dest.exists() and expected_dest != mp3_path:
                unresolved_rows.append(
                    PlannedMoveRow(
                        source_path=mp3_path,
                        dest_path=build_unresolved_destination(
                            unresolved_root,
                            "dest_exists",
                            mp3_path,
                            used_destinations=unresolved_destinations,
                        ),
                        reason="dest_exists",
                        bucket="unresolved",
                        source_flac_path=db_lookup.get(mp3_path).source_path if mp3_path in db_lookup else None,
                        identity_id=db_lookup.get(mp3_path).identity_id if mp3_path in db_lookup else None,
                    )
                )
                bucket_counts["unresolved"] += 1
                reason_counts["dest_exists"] += 1
                continue
            if expected_dest in planned_destinations:
                unresolved_rows.append(
                    PlannedMoveRow(
                        source_path=mp3_path,
                        dest_path=build_unresolved_destination(
                            unresolved_root,
                            "conflict_same_dest",
                            mp3_path,
                            used_destinations=unresolved_destinations,
                        ),
                        reason="conflict_same_dest",
                        bucket="unresolved",
                        source_flac_path=db_lookup.get(mp3_path).source_path if mp3_path in db_lookup else None,
                        identity_id=db_lookup.get(mp3_path).identity_id if mp3_path in db_lookup else None,
                    )
                )
                bucket_counts["unresolved"] += 1
                reason_counts["conflict_same_dest"] += 1
                continue

            planned_destinations.add(expected_dest)
            lookup = db_lookup.get(mp3_path)
            move_rows.append(
                PlannedMoveRow(
                    source_path=mp3_path,
                    dest_path=expected_dest,
                    reason=reason,
                    bucket="move_only",
                    source_flac_path=lookup.source_path if lookup is not None else None,
                    identity_id=lookup.identity_id if lookup is not None else None,
                )
            )
            bucket_counts["move_only"] += 1
            continue

        lookup = db_lookup.get(mp3_path)
        missing = missing_core_fields(metadata.tags if metadata is not None else {})

        if lookup is not None:
            merged = merge_tags_for_db_repair(
                metadata.tags if metadata is not None else {},
                snapshot=lookup.snapshot,
                flac_metadata=lookup.source_metadata,
            )
            merged_missing = missing_core_fields(merged)
            try:
                repaired_dest = build_canonical_mp3_destination(merged, root)
            except FinalLibraryLayoutError:
                repaired_dest = None
            if not merged_missing and repaired_dest is not None:
                repair_db_rows.append(
                    RepairRow(
                        path=mp3_path,
                        flac_path=lookup.source_path,
                        match_source="db_dj_pool_path",
                        reason="repair_then_move_db",
                        missing_fields=missing,
                        expected_dest_path=repaired_dest,
                        identity_id=lookup.identity_id,
                    )
                )
                bucket_counts["repair_then_move_db"] += 1
                continue

        if metadata is not None and metadata.title and metadata.artist:
            candidates = master_index.get((_norm(metadata.title), _norm(metadata.artist)), [])
            match = pick_best_master_match(metadata, candidates, duration_tol=duration_tol)
            if match is not None:
                merged = merge_tags_for_master_repair(metadata.tags, match)
                merged_missing = missing_core_fields(merged)
                try:
                    repaired_dest = build_canonical_mp3_destination(merged, root)
                except FinalLibraryLayoutError:
                    repaired_dest = None
                if not merged_missing and repaired_dest is not None:
                    repair_master_rows.append(
                        RepairRow(
                            path=mp3_path,
                            flac_path=match.path,
                            match_source="master",
                            reason="repair_then_move_master",
                            missing_fields=missing,
                            expected_dest_path=repaired_dest,
                        )
                    )
                    bucket_counts["repair_then_move_master"] += 1
                    continue
                unresolved_reason = "partial_flac_match"
            else:
                unresolved_reason = "no_flac_match"
        else:
            unresolved_reason = "missing_title_artist"

        unresolved_rows.append(
            PlannedMoveRow(
                source_path=mp3_path,
                dest_path=build_unresolved_destination(
                    unresolved_root,
                    unresolved_reason,
                    mp3_path,
                    used_destinations=unresolved_destinations,
                ),
                reason=unresolved_reason,
                bucket="unresolved",
                source_flac_path=lookup.source_path if lookup is not None else None,
                identity_id=lookup.identity_id if lookup is not None else None,
            )
        )
        bucket_counts["unresolved"] += 1
        reason_counts[unresolved_reason] += 1

    relink_rows = [
        DjPoolRelinkRow(
            source_path=row.source_flac_path,
            old_dj_pool_path=row.source_path,
            new_dj_pool_path=row.dest_path,
            identity_id=row.identity_id,
            reason=row.reason,
        )
        for row in move_rows
        if row.source_flac_path is not None
    ]
    playlist_rows = plan_playlist_rewrites(root, move_rows, unresolved_rows)

    move_plan_path = _write_csv(
        out_dir / "move_plan.csv",
        ["source_path", "dest_path", "mode", "reason", "bucket", "db_path", "identity_id"],
        [_to_move_row_dict(row) for row in move_rows],
    )
    repair_master_path = _write_csv(
        out_dir / "repair_master.csv",
        ["path", "flac_path", "match_source", "reason", "missing_fields", "expected_dest_path", "identity_id"],
        [_to_repair_row_dict(row) for row in repair_master_rows],
    )
    repair_db_path = _write_csv(
        out_dir / "repair_db.csv",
        ["path", "flac_path", "match_source", "reason", "missing_fields", "expected_dest_path", "identity_id"],
        [_to_repair_row_dict(row) for row in repair_db_rows],
    )
    unresolved_path = _write_csv(
        out_dir / "unresolved.csv",
        ["source_path", "dest_path", "mode", "reason", "bucket", "db_path", "identity_id"],
        [_to_move_row_dict(row) for row in unresolved_rows],
    )
    relink_path = _write_csv(
        out_dir / "dj_pool_relink_manifest.csv",
        ["source_path", "old_dj_pool_path", "new_dj_pool_path", "identity_id", "reason"],
        [_to_relink_row_dict(row) for row in relink_rows],
    )
    playlist_path = _write_csv(
        out_dir / "playlist_rewrite.csv",
        ["playlist_path", "line_number", "old_path", "new_path", "action", "reason"],
        [_to_playlist_row_dict(row) for row in playlist_rows],
    )

    summary = {
        "root": str(root),
        "master_root": str(master_root),
        "unresolved_root": str(unresolved_root),
        "duration_tol": duration_tol,
        "total_mp3": len(active_mp3s),
        "already_canonical": already_canonical,
        "move_plan_rows": len(move_rows),
        "repair_master_rows": len(repair_master_rows),
        "repair_db_rows": len(repair_db_rows),
        "unresolved_rows": len(unresolved_rows),
        "relink_rows": len(relink_rows),
        "playlist_rewrite_rows": len(playlist_rows),
        "bucket_counts": dict(bucket_counts),
        "reason_counts": dict(reason_counts),
        "outputs": {
            "summary_json": str(out_dir / "summary.json"),
            "move_plan_csv": str(move_plan_path),
            "repair_master_csv": str(repair_master_path),
            "repair_db_csv": str(repair_db_path),
            "dj_pool_relink_manifest_csv": str(relink_path),
            "unresolved_csv": str(unresolved_path),
            "playlist_rewrite_csv": str(playlist_path),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def load_playlist_rewrite_rows(path: Path) -> list[PlaylistRewriteRow]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        PlaylistRewriteRow(
            playlist_path=Path(str(row["playlist_path"])).expanduser().resolve(),
            line_number=int(row["line_number"]),
            old_path=str(row["old_path"]),
            new_path=str(row["new_path"]),
            action=str(row["action"]),
            reason=str(row["reason"]),
        )
        for row in rows
    ]


def apply_playlist_rewrite_manifest(
    manifest_path: Path,
    *,
    execute: bool,
) -> int:
    rows = load_playlist_rewrite_rows(manifest_path)
    grouped: dict[Path, list[PlaylistRewriteRow]] = defaultdict(list)
    for row in rows:
        grouped[row.playlist_path].append(row)
    rewrites = 0
    for playlist_path, playlist_rows in grouped.items():
        if not playlist_path.exists():
            continue
        lines = playlist_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for row in playlist_rows:
            if row.line_number - 1 >= len(lines):
                continue
            rewrites += 1
            if not execute:
                continue
            if row.action == "rewrite":
                lines[row.line_number - 1] = row.new_path
            else:
                lines[row.line_number - 1] = f"# unresolved: {row.old_path} ({row.reason})"
        if execute:
            playlist_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return rewrites


def apply_dj_pool_relink(
    conn: sqlite3.Connection,
    manifest_path: Path,
    *,
    execute: bool,
) -> RelinkStats:
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    updated = 0
    skipped = 0
    errors = 0

    for row in rows:
        source_path = Path(str(row["source_path"])).expanduser().resolve()
        old_path = Path(str(row["old_dj_pool_path"])).expanduser().resolve()
        new_path = Path(str(row["new_dj_pool_path"])).expanduser().resolve()
        identity_text = str(row.get("identity_id") or "").strip()
        identity_id = int(identity_text) if identity_text else None
        reason = str(row.get("reason") or "").strip()

        current = conn.execute("SELECT dj_pool_path FROM files WHERE path = ?", (str(source_path),)).fetchone()
        if current is None:
            skipped += 1
            continue
        current_path = str(current[0] or "").strip()
        if current_path and Path(current_path).expanduser().resolve() != old_path:
            skipped += 1
            continue
        if not execute:
            updated += 1
            continue

        try:
            conn.execute("UPDATE files SET dj_pool_path = ? WHERE path = ?", (str(new_path), str(source_path)))
            asset_id = resolve_asset_id_by_path(conn, source_path)
            record_provenance_event(
                conn,
                event_type="dj_pool_relink",
                status="success",
                asset_id=asset_id,
                identity_id=identity_id,
                source_path=str(source_path),
                dest_path=str(new_path),
                details={
                    "old_dj_pool_path": str(old_path),
                    "reason": reason,
                    "tool": "ops.relink-dj-pool",
                },
            )
            updated += 1
        except Exception:
            errors += 1

    if execute:
        conn.commit()
    return RelinkStats(rows=len(rows), updated=updated, skipped=skipped, errors=errors)


def summary_json_for_display(summary: dict[str, object]) -> str:
    return json.dumps(summary, indent=2, sort_keys=True)
