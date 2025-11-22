"""Global multi-volume recovery workflow utilities."""

from __future__ import annotations

import csv
import datetime as _dt
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

from . import rstudio_parser, scanner, utils

LOGGER = logging.getLogger(__name__)

FILES_TABLE = "global_files"
FRAGMENTS_TABLE = "global_fragments"
RESOLVED_TABLE = "global_resolved_tracks"


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Ensure all tables required for the global recovery workflow exist."""

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {FILES_TABLE} (
            id INTEGER PRIMARY KEY,
            source_root TEXT NOT NULL,
            path TEXT UNIQUE NOT NULL,
            relative_path TEXT NOT NULL,
            filename TEXT NOT NULL,
            extension TEXT,
            size_bytes INTEGER,
            mtime REAL NOT NULL,
            duration REAL,
            sample_rate INTEGER,
            bit_rate INTEGER,
            channels INTEGER,
            bit_depth INTEGER,
            checksum TEXT,
            fingerprint TEXT,
            fingerprint_duration REAL,
            tags_json TEXT,
            scanned_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{FILES_TABLE}_source_root
            ON {FILES_TABLE} (source_root)
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {FRAGMENTS_TABLE} (
            id INTEGER PRIMARY KEY,
            source_path TEXT UNIQUE NOT NULL,
            suggested_name TEXT,
            filename TEXT,
            extension TEXT,
            size_bytes INTEGER,
            parsed_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {RESOLVED_TABLE} (
            group_key TEXT PRIMARY KEY,
            best_file_id INTEGER,
            best_score REAL,
            confidence REAL,
            reason TEXT,
            resolved_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(best_file_id) REFERENCES {FILES_TABLE}(id)
        )
        """
    )


def _collect_existing_index(
    connection: sqlite3.Connection,
) -> dict[str, tuple[int, float]]:
    """Return a mapping of already indexed paths to ``(size, mtime)``."""

    index: dict[str, tuple[int, float]] = {}
    cursor = connection.execute(
        f"SELECT path, size_bytes, mtime FROM {FILES_TABLE}"
    )
    for row in cursor.fetchall():
        npath = utils.normalise_path(row["path"])
        index[npath] = (row["size_bytes"], row["mtime"])
    return index


def _iter_scan_records(
    paths: Iterable[Path],
    include_fingerprints: bool,
) -> Iterator[scanner.ScanRecord]:
    """Yield :class:`~dedupe.scanner.ScanRecord` for *paths* using metadata."""

    for path in paths:
        try:
            yield scanner.prepare_record(
                path,
                include_fingerprints,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Failed to scan %s: %s", path, exc)


def _resolve_relative_path(path: Path, root: Path) -> str:
    """Return the POSIX relative path of *path* with respect to *root*."""

    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def scan_roots(
    roots: Sequence[Path],
    database: Path,
    *,
    include_fingerprints: bool = False,
    batch_size: int = 100,
    resume: bool = False,
    show_progress: bool = False,
) -> int:
    """Scan *roots* and persist file metadata into *database*.

    Args:
        roots: Root directories to scan recursively.
        database: SQLite database file to update.
        include_fingerprints: Whether to compute audio fingerprints.
        batch_size: Number of files written per transaction batch.
        resume: Skip files whose size and mtime have not changed.
        show_progress: Whether to display a progress bar when scanning.

    Returns:
        The total number of files inserted or updated across all roots.
    """

    utils.ensure_parent_directory(database)
    total = 0
    db = utils.DatabaseContext(database)
    fingerprints_enabled = scanner.resolve_fingerprint_usage(include_fingerprints)
    with db.connect() as connection:
        ensure_schema(connection)

    for root in roots:
        LOGGER.info("Scanning root %s", root)
        root = root.expanduser().resolve()
        iterator = utils.iter_audio_files(root)
        utils.ensure_parent_directory(database)
        with db.connect() as connection:
            ensure_schema(connection)
            existing_index = (
                _collect_existing_index(connection) if resume else {}
            )

            def batches() -> Iterator[list[Path]]:
                batch: list[Path] = []
                for path in iterator:
                    npath = utils.normalise_path(str(path))
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    if resume:
                        existing = existing_index.get(npath)
                        if existing is not None:
                            size, mtime = existing
                            unchanged = (
                                size == stat.st_size
                                and abs(mtime - stat.st_mtime) < 1.0
                            )
                            if unchanged:
                                continue
                    batch.append(path)
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []
                if batch:
                    yield batch

            progress = None
            total_files = None
            if show_progress:
                total_files = sum(1 for _ in utils.iter_audio_files(root))
                try:
                    from tqdm import tqdm  # type: ignore

                    progress = tqdm(total=total_files, unit="files")
                except Exception:  # pragma: no cover - tqdm optional
                    progress = None

            for batch in batches():
                records = list(_iter_scan_records(batch, fingerprints_enabled))
                if not records:
                    if progress:
                        progress.update(len(batch))
                    continue
                payload = [
                    {
                        "source_root": root.as_posix(),
                        "path": record.path,
                        "relative_path": _resolve_relative_path(
                            Path(record.path),
                            root,
                        ),
                        "filename": Path(record.path).name,
                        "extension": Path(record.path)
                        .suffix.lower()
                        .lstrip("."),
                        "size_bytes": record.size_bytes,
                        "mtime": record.mtime,
                        "duration": record.duration,
                        "sample_rate": record.sample_rate,
                        "bit_rate": record.bit_rate,
                        "channels": record.channels,
                        "bit_depth": record.bit_depth,
                        "checksum": record.checksum,
                        "fingerprint": record.fingerprint,
                        "fingerprint_duration": record.fingerprint_duration,
                        "tags_json": record.tags_json,
                    }
                    for record in records
                ]
                connection.executemany(
                    f"""
                    INSERT INTO {FILES_TABLE} (
                        source_root,
                        path,
                        relative_path,
                        filename,
                        extension,
                        size_bytes,
                        mtime,
                        duration,
                        sample_rate,
                        bit_rate,
                        channels,
                        bit_depth,
                        checksum,
                        fingerprint,
                        fingerprint_duration,
                        tags_json
                    ) VALUES (
                        :source_root,
                        :path,
                        :relative_path,
                        :filename,
                        :extension,
                        :size_bytes,
                        :mtime,
                        :duration,
                        :sample_rate,
                        :bit_rate,
                        :channels,
                        :bit_depth,
                        :checksum,
                        :fingerprint,
                        :fingerprint_duration,
                        :tags_json
                    )
                    ON CONFLICT(path) DO UPDATE SET
                        source_root=excluded.source_root,
                        relative_path=excluded.relative_path,
                        filename=excluded.filename,
                        extension=excluded.extension,
                        size_bytes=excluded.size_bytes,
                        mtime=excluded.mtime,
                        duration=excluded.duration,
                        sample_rate=excluded.sample_rate,
                        bit_rate=excluded.bit_rate,
                        channels=excluded.channels,
                        bit_depth=excluded.bit_depth,
                        checksum=excluded.checksum,
                        fingerprint=excluded.fingerprint,
                        fingerprint_duration=excluded.fingerprint_duration,
                        tags_json=excluded.tags_json,
                        scanned_at=CURRENT_TIMESTAMP
                    """,
                    payload,
                )
                connection.commit()
                total += len(records)
                if progress:
                    progress.update(len(batch))

            if progress:
                progress.close()

    LOGGER.info("Recorded %s files across %s roots", total, len(roots))
    return total


def parse_recognized_export(path: Path, database: Path) -> int:
    """Parse an R-Studio export and store fragments in *database*."""

    utils.ensure_parent_directory(database)
    records = list(rstudio_parser.parse_export(path))
    db = utils.DatabaseContext(database)
    with db.connect() as connection:
        ensure_schema(connection)
        connection.executemany(
            f"""
            INSERT INTO {FRAGMENTS_TABLE} (
                source_path,
                suggested_name,
                filename,
                extension,
                size_bytes
            ) VALUES (
                :source_path,
                :suggested_name,
                :filename,
                :extension,
                :size_bytes
            )
            ON CONFLICT(source_path) DO UPDATE SET
                suggested_name=excluded.suggested_name,
                filename=excluded.filename,
                extension=excluded.extension,
                size_bytes=excluded.size_bytes,
                parsed_at=CURRENT_TIMESTAMP
            """,
            [
                {
                    "source_path": record.source_path,
                    "suggested_name": record.suggested_name,
                    "filename": Path(record.source_path).name,
                    "extension": record.extension,
                    "size_bytes": record.size_bytes,
                }
                for record in records
            ],
        )
        count = connection.execute(
            f"SELECT COUNT(*) FROM {FRAGMENTS_TABLE}"
        ).fetchone()[0]
    LOGGER.info("Recorded %s fragments from %s", len(records), path)
    return int(count)


def _normalise_component(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in text.lower())
    return " ".join(cleaned.split())


def _extract_tag_value(tags: dict[str, object], *keys: str) -> Optional[str]:
    for key in keys:
        if key in tags:
            value = tags[key]
            if isinstance(value, list):
                return str(value[0])
            return str(value)
    return None


def _load_tags(row: sqlite3.Row) -> dict[str, object]:
    try:
        return json.loads(row["tags_json"]) if row["tags_json"] else {}
    except json.JSONDecodeError:
        return {}


def _name_tokens_from_row(row: sqlite3.Row) -> list[str]:
    tags = {k.lower(): v for k, v in _load_tags(row).items()}
    tokens: list[str] = []
    artist = _extract_tag_value(tags, "albumartist", "artist")
    album = _extract_tag_value(tags, "album")
    track_number = _extract_tag_value(tags, "tracknumber", "track")
    title = _extract_tag_value(tags, "title")
    if artist:
        tokens.append(artist)
    if album:
        tokens.append(album)
    if track_number:
        tokens.append(track_number)
    if title:
        tokens.append(title)
    if not tokens:
        parts = [part for part in Path(row["relative_path"]).parts if part]
        if parts:
            tokens.extend(parts[-3:])
    if not tokens:
        tokens.append(Path(row["filename"]).stem)
    return [_normalise_component(token) for token in tokens if token]


def _build_group_key(tokens: Sequence[str]) -> str:
    return "::".join(token for token in tokens if token)


def _similarity(left: str, right: str) -> float:
    from difflib import SequenceMatcher

    return SequenceMatcher(None, left, right).ratio()


@dataclass(slots=True)
class Candidate:
    """Representation of a file candidate participating in resolution."""

    row: sqlite3.Row
    tokens: Sequence[str]
    key: str
    score: float = 0.0
    reason: list[str] = field(default_factory=list)
    penalties: list[str] = field(default_factory=list)

    @property
    def path(self) -> str:
        return self.row["path"]

    @property
    def source_root(self) -> str:
        return self.row["source_root"]


@dataclass(slots=True)
class Fragment:
    """Parsed fragment row used during resolution."""

    row: sqlite3.Row
    tokens: Sequence[str]
    key: str


@dataclass(slots=True)
class ResolverConfig:
    """Configuration controlling :func:`resolve_database`."""

    database: Path
    out_prefix: Path
    min_name_similarity: float = 0.65
    duration_tolerance: float = 1.0
    size_tolerance: float = 0.02
    threshold: float = 0.55


@dataclass(slots=True)
class ResolutionResult:
    """Container summarising per-group resolution output."""

    group_key: str
    best: Optional[Candidate]
    ordered: list[Candidate]
    fragments: list[Fragment]
    needs_manual: bool


def _score_candidate(
    candidate: Candidate,
    *,
    max_duration: Optional[float],
    max_size: Optional[int],
    max_bitrate: Optional[int],
    max_samplerate: Optional[int],
    config: ResolverConfig,
) -> None:
    """Score ``candidate`` in-place and populate reasons/penalties lists."""

    row = candidate.row
    ext = (row["extension"] or "").lower()
    quality_bonus = {
        "flac": 0.35,
        "wav": 0.3,
        "aiff": 0.3,
        "aif": 0.3,
        "alac": 0.3,
        "m4a": 0.25,
        "mp3": 0.15,
        "ogg": 0.2,
        "aac": 0.2,
    }.get(ext, 0.1)
    candidate.score += quality_bonus
    candidate.reason.append(f"format={ext or 'unknown'}")

    duration = row["duration"]
    if duration and max_duration:
        ratio = min(duration / max_duration, 1.0)
        candidate.score += 0.4 * ratio
        candidate.reason.append(f"duration_ratio={ratio:.2f}")
        if abs(duration - max_duration) > config.duration_tolerance:
            candidate.score -= 0.25
            candidate.penalties.append("duration_mismatch")
    elif duration:
        candidate.score += 0.1
        candidate.reason.append("duration=present")
    else:
        candidate.penalties.append("missing_duration")
        candidate.score -= 0.05

    size = row["size_bytes"]
    if size and max_size:
        size_ratio = min(size / max_size, 1.0)
        candidate.score += 0.2 * size_ratio
        candidate.reason.append(f"size_ratio={size_ratio:.2f}")
        if abs(size - max_size) / max(max_size, 1) > config.size_tolerance:
            candidate.penalties.append("size_mismatch")
            candidate.score -= 0.1
    elif size:
        candidate.score += 0.05
    else:
        candidate.penalties.append("missing_size")
        candidate.score -= 0.05

    bit_rate = row["bit_rate"]
    if bit_rate and max_bitrate:
        bitrate_ratio = min(bit_rate / max_bitrate, 1.0)
        candidate.score += 0.15 * bitrate_ratio
        candidate.reason.append(f"bitrate_ratio={bitrate_ratio:.2f}")
    elif bit_rate:
        candidate.score += 0.05
    else:
        candidate.penalties.append("missing_bitrate")
        candidate.score -= 0.05

    sample_rate = row["sample_rate"]
    if sample_rate and max_samplerate:
        samplerate_ratio = min(sample_rate / max_samplerate, 1.0)
        candidate.score += 0.1 * samplerate_ratio
        candidate.reason.append(f"samplerate_ratio={samplerate_ratio:.2f}")
    elif sample_rate:
        candidate.score += 0.03
    else:
        candidate.penalties.append("missing_samplerate")

    if row["fingerprint"]:
        candidate.score += 0.05
        candidate.reason.append("fingerprint_present")


def _load_candidates(connection: sqlite3.Connection) -> list[Candidate]:
    cursor = connection.execute(f"SELECT * FROM {FILES_TABLE}")
    candidates: list[Candidate] = []
    for row in cursor.fetchall():
        tokens = _name_tokens_from_row(row)
        candidates.append(
            Candidate(
                row=row,
                tokens=tokens,
                key=_build_group_key(tokens),
            )
        )
    return candidates


def _load_fragments(connection: sqlite3.Connection) -> list[Fragment]:
    cursor = connection.execute(f"SELECT * FROM {FRAGMENTS_TABLE}")
    fragments: list[Fragment] = []
    for row in cursor.fetchall():
        raw_name = row["suggested_name"] or row["filename"] or ""
        tokens = [
            _normalise_component(token)
            for token in raw_name.split()
            if token
        ]
        if not tokens:
            tokens = [_normalise_component(Path(row["source_path"]).stem)]
        fragments.append(
            Fragment(
                row=row,
                tokens=tokens,
                key=_build_group_key(tokens),
            )
        )
    return fragments


def _group_candidates(
    candidates: Sequence[Candidate],
) -> dict[str, list[Candidate]]:
    groups: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        groups.setdefault(candidate.key, []).append(candidate)
    return groups


def _assign_fragments(
    groups: dict[str, list[Candidate]],
    fragments: Sequence[Fragment],
    *,
    min_similarity: float,
) -> dict[str, list[Fragment]]:
    assigned: dict[str, list[Fragment]] = {key: [] for key in groups.keys()}
    for fragment in fragments:
        best_key = None
        best_score = 0.0
        for key in groups.keys():
            score = _similarity(fragment.key, key)
            if score > best_score:
                best_score = score
                best_key = key
        if best_key and best_score >= min_similarity:
            assigned.setdefault(best_key, []).append(fragment)
        else:
            assigned.setdefault(fragment.key, []).append(fragment)
    return assigned


def _score_group(
    group_key: str,
    candidates: Sequence[Candidate],
    fragments: Sequence[Fragment],
    config: ResolverConfig,
) -> ResolutionResult:
    if not candidates:
        return ResolutionResult(
            group_key=group_key,
            best=None,
            ordered=[],
            fragments=list(fragments),
            needs_manual=True,
        )

    max_duration = (
        max((c.row["duration"] or 0 for c in candidates), default=0) or None
    )
    max_size = max(
        (c.row["size_bytes"] or 0 for c in candidates),
        default=0,
    ) or None
    max_bitrate = max(
        (c.row["bit_rate"] or 0 for c in candidates),
        default=0,
    ) or None
    max_samplerate = max(
        (c.row["sample_rate"] or 0 for c in candidates),
        default=0,
    ) or None

    for candidate in candidates:
        _score_candidate(
            candidate,
            max_duration=max_duration,
            max_size=max_size,
            max_bitrate=max_bitrate,
            max_samplerate=max_samplerate,
            config=config,
        )

    ordered = sorted(candidates, key=lambda c: c.score, reverse=True)
    best = ordered[0] if ordered else None
    needs_manual = False
    if not best or best.score < config.threshold:
        needs_manual = True

    if len(ordered) > 1:
        second = ordered[1]
        if best.score - second.score < 0.05:
            needs_manual = True

    # Additional manual flag if fragments exist without strong candidate.
    if fragments and not ordered:
        needs_manual = True

    return ResolutionResult(
        group_key=group_key,
        best=best,
        ordered=list(ordered),
        fragments=list(fragments),
        needs_manual=needs_manual,
    )


def resolve_database(config: ResolverConfig) -> list[ResolutionResult]:
    """Execute the resolver and write CSV reports to ``config.out_prefix``."""

    utils.ensure_parent_directory(config.database)
    utils.ensure_parent_directory(config.out_prefix)
    db = utils.DatabaseContext(config.database)
    results: list[ResolutionResult] = []
    with db.connect() as connection:
        ensure_schema(connection)
        candidates = _load_candidates(connection)
        fragments = _load_fragments(connection)
        groups = _group_candidates(candidates)
        fragment_map = _assign_fragments(
            groups,
            fragments,
            min_similarity=config.min_name_similarity,
        )
        all_keys = set(groups.keys()) | set(fragment_map.keys())
        resolved_rows: list[dict[str, object]] = []
        for key in sorted(all_keys):
            group_candidates = groups.get(key, [])
            group_fragments = fragment_map.get(key, [])
            result = _score_group(
                key,
                group_candidates,
                group_fragments,
                config,
            )
            results.append(result)
            if result.best:
                confidence = _compute_confidence(result.ordered)
                resolved_rows.append(
                    {
                        "group_key": key,
                        "best_file_id": result.best.row["id"],
                        "best_score": result.best.score,
                        "confidence": confidence,
                        "reason": ";".join(result.best.reason),
                        "resolved_at": _dt.datetime.now().isoformat(),
                    }
                )
        connection.executemany(
            f"""
            INSERT INTO {RESOLVED_TABLE} (
                group_key,
                best_file_id,
                best_score,
                confidence,
                reason,
                resolved_at
            ) VALUES (
                :group_key,
                :best_file_id,
                :best_score,
                :confidence,
                :reason,
                :resolved_at
            )
            ON CONFLICT(group_key) DO UPDATE SET
                best_file_id=excluded.best_file_id,
                best_score=excluded.best_score,
                confidence=excluded.confidence,
                reason=excluded.reason,
                resolved_at=excluded.resolved_at
            """,
            resolved_rows,
        )

    _write_reports(results, config)
    LOGGER.info("Wrote recovery reports to %s", config.out_prefix)
    return results


def _compute_confidence(candidates: Sequence[Candidate]) -> float:
    if not candidates:
        return 0.0
    best = candidates[0]
    if len(candidates) == 1:
        return min(1.0, max(0.0, best.score))
    second = candidates[1]
    margin = best.score - second.score
    return max(0.0, min(1.0, best.score * 0.5 + margin))


def _write_reports(
    results: Sequence[ResolutionResult],
    config: ResolverConfig,
) -> None:
    keepers_path = config.out_prefix.with_name(
        f"{config.out_prefix.name}_keepers.csv"
    )
    improvements_path = config.out_prefix.with_name(
        f"{config.out_prefix.name}_improvements.csv"
    )
    manual_path = config.out_prefix.with_name(
        f"{config.out_prefix.name}_manual_repair.csv"
    )
    archive_path = config.out_prefix.with_name(
        f"{config.out_prefix.name}_archive_candidates.csv"
    )

    keepers_rows: list[dict[str, object]] = []
    improvements_rows: list[dict[str, object]] = []
    manual_rows: list[dict[str, object]] = []
    archive_rows: list[dict[str, object]] = []

    for result in results:
        best = result.best
        if result.needs_manual or not best:
            manual_rows.append(
                {
                    "group_key": result.group_key,
                    "status": "no_files" if not best else "low_confidence",
                    "fragment_count": len(result.fragments),
                }
            )
            continue

        keepers_rows.append(
            {
                "group_key": result.group_key,
                "best_path": best.path,
                "score": f"{best.score:.3f}",
                "reason": ";".join(best.reason),
                "source_root": best.source_root,
                "size_bytes": best.row["size_bytes"],
                "duration": best.row["duration"],
                "bit_rate": best.row["bit_rate"],
                "sample_rate": best.row["sample_rate"],
            }
        )

        for alt in result.ordered[1:]:
            improvements_rows.append(
                {
                    "group_key": result.group_key,
                    "replacement_path": best.path,
                    "replacement_source": best.source_root,
                    "replacement_score": f"{best.score:.3f}",
                    "original_path": alt.path,
                    "original_source": alt.source_root,
                    "original_score": f"{alt.score:.3f}",
                    "reason": ";".join(best.reason),
                }
            )
            duration_penalty = "duration_mismatch" in alt.penalties
            if best.score - alt.score >= 0.2 or duration_penalty:
                archive_rows.append(
                    {
                        "group_key": result.group_key,
                        "path": alt.path,
                        "source_root": alt.source_root,
                        "score": f"{alt.score:.3f}",
                        "penalties": ";".join(alt.penalties),
                    }
                )

    csv_definitions = [
        (
            keepers_path,
            keepers_rows,
            [
                "group_key",
                "best_path",
                "score",
                "reason",
                "source_root",
                "size_bytes",
                "duration",
                "bit_rate",
                "sample_rate",
            ],
        ),
        (
            improvements_path,
            improvements_rows,
            [
                "group_key",
                "replacement_path",
                "replacement_source",
                "replacement_score",
                "original_path",
                "original_source",
                "original_score",
                "reason",
            ],
        ),
        (
            manual_path,
            manual_rows,
            ["group_key", "status", "fragment_count"],
        ),
        (
            archive_path,
            archive_rows,
            ["group_key", "path", "source_root", "score", "penalties"],
        ),
    ]

    for path, rows, fieldnames in csv_definitions:
        _write_csv(path, rows, fieldnames)


def _write_csv(
    path: Path,
    rows: Sequence[dict[str, object]],
    fieldnames: Sequence[str],
) -> None:
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
