"""Matching logic between scanned library and recovered files."""

from __future__ import annotations

import csv
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from rapidfuzz import fuzz

from . import utils

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LibEntry:
    """Single library row from library.db."""

    path: str
    name: str
    size_bytes: int


@dataclass(slots=True)
class RecEntry:
    """Single recovered row from recovered.db."""

    source_path: str
    name: str
    size_bytes: int
    extension: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TOKEN_SPLIT_RE = re.compile(r"[^0-9a-zA-Z]+", re.UNICODE)


def _tokenise_name(name: str) -> List[str]:
    """
    Tokenise a filename into normalised tokens.

    We:
    - lowercase
    - strip extension
    - split on non-alphanumeric characters
    - drop tokens of length < 2
    """
    base = os.path.basename(name)
    stem, _ext = os.path.splitext(base)
    stem = stem.lower()
    tokens = [t for t in _TOKEN_SPLIT_RE.split(stem) if len(t) >= 2]
    return tokens


def _filename_similarity(a: str, b: str) -> float:
    """
    Compute similarity between two filenames.

    Uses RapidFuzz's ratio (0–100) and normalises to 0–1.
    """
    if not a or not b:
        return 0.0
    return fuzz.ratio(a.lower(), b.lower()) / 100.0


def _load_library_entries(db_path: Path) -> List[LibEntry]:
    """Load all library entries from library.db."""
    db = utils.DatabaseContext(db_path)
    entries: List[LibEntry] = []

    with db.connect() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT path, size_bytes FROM library_files ORDER BY path"
        )
        for row in cursor:
            path = row["path"]
            entries.append(
                LibEntry(
                    path=path,
                    name=os.path.basename(path),
                    size_bytes=row["size_bytes"],
                )
            )

    LOGGER.info("Loaded %d library entries", len(entries))
    return entries


def _load_recovered_entries(db_path: Path) -> List[RecEntry]:
    """Load all recovered entries from recovered.db."""
    db = utils.DatabaseContext(db_path)
    entries: List[RecEntry] = []

    with db.connect() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT source_path, suggested_name, size_bytes, extension "
            "FROM recovered_files "
            "ORDER BY source_path"
        )
        for row in cursor:
            source_path = row["source_path"]
            suggested_name = row["suggested_name"]
            extension = row["extension"] or ""
            name = suggested_name or os.path.basename(source_path)

            entries.append(
                RecEntry(
                    source_path=source_path,
                    name=name,
                    size_bytes=row["size_bytes"] or 0,
                    extension=extension.lower(),
                )
            )

    LOGGER.info("Loaded %d recovery entries", len(entries))
    return entries


def _build_token_index(recovered: Iterable[RecEntry]) -> Dict[str, List[RecEntry]]:
    """
    Build an inverted index from token -> list[RecEntry].

    This lets us avoid comparing every library entry to every recovered entry.
    """
    index: Dict[str, List[RecEntry]] = {}
    for r in recovered:
        tokens = _tokenise_name(r.name)
        if not tokens:
            # Fallback: use bare stem
            stem, _ext = os.path.splitext(os.path.basename(r.name))
            if stem:
                tokens = [stem.lower()]

        for tok in tokens:
            index.setdefault(tok, []).append(r)

    LOGGER.info("Built token index for %d distinct tokens", len(index))
    return index


def _filter_candidates(
    lib: LibEntry,
    token_index: Dict[str, List[RecEntry]],
    recovered_all: List[RecEntry],
    max_candidates: int = 500,
) -> List[RecEntry]:
    """
    Select a manageable candidate set for a library entry.

    Strategy:
    - Tokenise the library filename.
    - Union all recovered entries that share at least one token.
    - Deduplicate by `source_path`.
    - If nothing is found, fall back to all recovered entries
      (capped at `max_candidates`).
    """
    tokens = _tokenise_name(lib.name)
    candidates: List[RecEntry] = []
    seen: set[str] = set()

    # Use token hits first
    for tok in tokens:
        for r in token_index.get(tok, []):
            if r.source_path in seen:
                continue
            seen.add(r.source_path)
            candidates.append(r)
            if len(candidates) >= max_candidates:
                return candidates

    # Fallback: if no tokens hit, use the first N recovered entries
    if not candidates:
        if recovered_all:
            limit = min(max_candidates, len(recovered_all))
            candidates = recovered_all[:limit]

    return candidates


def _score_match(lib: LibEntry, rec: RecEntry) -> Tuple[float, str]:
    """
    Compute a similarity score and 'reason' label for a candidate pair.

    - base: RapidFuzz filename similarity
    - +0.02 if extensions match
    - +0.03 if sizes are within ~1% or ≤ 8 KiB difference
    """
    sim = _filename_similarity(lib.name, rec.name)
    reason = "base"

    # Extension bonus
    lib_ext = os.path.splitext(lib.name)[1].lower()
    rec_ext = rec.extension.lower()
    if lib_ext and rec_ext and lib_ext == rec_ext:
        sim += 0.02
        reason = "ext_match"

    # Size bonus
    if lib.size_bytes and rec.size_bytes:
        delta = abs(lib.size_bytes - rec.size_bytes)
        if delta <= 8192 or delta / max(lib.size_bytes, 1) <= 0.01:
            sim += 0.03
            if reason == "base":
                reason = "size_match"
            else:
                reason = reason + "+size"

    # Clamp to [0, 1]
    if sim < 0.0:
        sim = 0.0
    if sim > 1.0:
        sim = 1.0

    return sim, reason


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def match_databases(
    library_db: Path,
    recovered_db: Path,
    out_csv: Path,
    min_similarity: float = 0.80,
    max_candidates: int = 500,
) -> None:
    """
    Match entries from `library_db` to `recovered_db` and write CSV.

    Output CSV schema (compatible with existing tooling):

        library_path,recovered_path,similarity,reason
    """
    LOGGER.info("Loading library DB: %s", library_db)
    library_entries = _load_library_entries(library_db)

    LOGGER.info("Loading recovered DB: %s", recovered_db)
    recovered_entries = _load_recovered_entries(recovered_db)

    if not recovered_entries:
        LOGGER.warning("No recovered entries found; nothing to match.")
        # Still write an empty CSV with header for downstream tools
        utils.ensure_parent_directory(out_csv)
        with out_csv.open("w", newline="", encoding="utf8") as f:
            writer = csv.writer(f)
            writer.writerow(["library_path", "recovered_path", "similarity", "reason"])
        return

    token_index = _build_token_index(recovered_entries)

    utils.ensure_parent_directory(out_csv)
    total_matches = 0
    processed = 0

    with out_csv.open("w", newline="", encoding="utf8") as f:
        writer = csv.writer(f)
        writer.writerow(["library_path", "recovered_path", "similarity", "reason"])

        for lib in library_entries:
            processed += 1
            if processed % 500 == 0:
                LOGGER.info(
                    "Matching progress: %d/%d (matches so far=%d)",
                    processed,
                    len(library_entries),
                    total_matches,
                )

            candidates = _filter_candidates(
                lib, token_index, recovered_entries, max_candidates=max_candidates
            )
            if not candidates:
                continue

            best_rec: RecEntry | None = None
            best_sim = 0.0
            best_reason = "none"

            for rec in candidates:
                sim, reason = _score_match(lib, rec)
                if sim > best_sim:
                    best_sim = sim
                    best_reason = reason
                    best_rec = rec

            if best_rec is None:
                continue

            if best_sim < min_similarity:
                continue

            writer.writerow(
                [
                    lib.path,
                    best_rec.source_path,
                    f"{best_sim:.3f}",
                    "top1" if best_reason == "base" else best_reason,
                ]
            )
            total_matches += 1

    LOGGER.info(
        "Matching complete: processed=%d library entries; "
        "total_matches=%d; avg_candidates_per_entry=%.2f",
        len(library_entries),
        total_matches,
        max_candidates if library_entries else 0.0,
    )
    LOGGER.info("Wrote %d matches to %s", total_matches, out_csv)