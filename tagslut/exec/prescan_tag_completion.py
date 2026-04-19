"""
Pre-scan tag completion for --no-download mode.

Scans batch root for files missing ISRC or artist/title tags.
Extracts ISRC from filename schema: {num}. {Artist} - {Title} [{ISRC}].flac
Uses ISRC to fetch and write missing tags before planning runs.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Optional

from mutagen.flac import FLAC

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.models.types import MatchConfidence, ProviderTrack
from tagslut.metadata.providers.tidal import TidalProvider

_ISRC_FROM_STEM = re.compile(r"\[([A-Z]{2}[A-Z0-9]{3}\d{7})\]", re.IGNORECASE)


def extract_isrc_from_filename(path: Path) -> Optional[str]:
    match = _ISRC_FROM_STEM.search(path.stem)
    if not match:
        return None
    value = (match.group(1) or "").strip().upper()
    return value or None


def _first_tag_value(audio: object, key: str) -> str:
    try:
        raw = getattr(audio, "get")(key)  # type: ignore[misc]
    except Exception:
        return ""
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple)):
        if not raw:
            return ""
        return str(raw[0] or "").strip()
    return str(raw or "").strip()


def _is_missing(audio: object, key: str) -> bool:
    return not _first_tag_value(audio, key)


def _pick_exact_match(results: list[ProviderTrack], isrc: str) -> Optional[ProviderTrack]:
    target = (isrc or "").strip().upper()
    for track in results:
        if track.match_confidence != MatchConfidence.EXACT:
            continue
        if (track.isrc or "").strip().upper() != target:
            continue
        return track
    return None


@dataclass(frozen=True)
class PrescanStats:
    files_scanned: int = 0
    files_changed: int = 0
    tags_filled: int = 0
    files_still_missing_tags: int = 0


def prescan_batch_root(*, batch_root: Path, db_path: Path, execute: bool) -> PrescanStats:
    del db_path  # CLI contract; unused for targeted tag writebacks.

    root = batch_root.expanduser().resolve()
    provider = TidalProvider(token_manager=TokenManager())
    cached: dict[str, Optional[ProviderTrack]] = {}

    scanned = 0
    changed = 0
    filled = 0
    still_missing = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() != ".flac":
            continue

        scanned += 1
        audio = FLAC(str(path))

        isrc_tag = _first_tag_value(audio, "isrc").upper()
        artist_tag = _first_tag_value(audio, "artist")
        title_tag = _first_tag_value(audio, "title")

        missing_isrc = not isrc_tag
        missing_artist = not artist_tag
        missing_title = not title_tag

        filename_isrc = extract_isrc_from_filename(path) if missing_isrc else None
        isrc_value = (isrc_tag or filename_isrc or "").strip().upper() or None

        provider_track: Optional[ProviderTrack] = None
        if (missing_artist or missing_title) and isrc_value:
            if isrc_value in cached:
                provider_track = cached[isrc_value]
            else:
                try:
                    results = provider.search_by_isrc(isrc_value, limit=5)
                except Exception:
                    results = []
                provider_track = _pick_exact_match(results, isrc_value)
                cached[isrc_value] = provider_track

        want_isrc = filename_isrc if missing_isrc else None
        want_artist = (provider_track.artist or "").strip() if (missing_artist and provider_track) else ""
        want_title = (provider_track.title or "").strip() if (missing_title and provider_track) else ""

        will_change = bool(want_isrc or want_artist or want_title)
        if not will_change:
            if missing_isrc or missing_artist or missing_title:
                still_missing += 1
            continue

        if execute:
            if want_isrc:
                audio["isrc"] = [want_isrc]
                filled += 1
            if want_artist:
                audio["artist"] = [want_artist]
                filled += 1
            if want_title:
                audio["title"] = [want_title]
                filled += 1
            audio.save()
            changed += 1
        else:
            filled += int(bool(want_isrc)) + int(bool(want_artist)) + int(bool(want_title))

            # Still missing because we didn't write.
            still_missing += 1

    if execute:
        # Re-scan missing count from actual state would require a second pass; keep it conservative.
        # still_missing currently counts only files we skipped or couldn't fill.
        pass

    return PrescanStats(
        files_scanned=scanned,
        files_changed=changed,
        tags_filled=filled,
        files_still_missing_tags=still_missing,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-scan tag completion for --no-download mode.")
    ap.add_argument("--batch-root", required=True, help="Directory to scan")
    ap.add_argument("--db", required=True, help="Database path (contract only; unused)")
    ap.add_argument("--execute", action="store_true", help="Actually write tags (default: dry-run)")
    args = ap.parse_args()

    stats = prescan_batch_root(
        batch_root=Path(args.batch_root),
        db_path=Path(args.db),
        execute=bool(args.execute),
    )
    print(
        "Pre-scan complete:"
        f" files_scanned={stats.files_scanned}"
        f" tags_filled={stats.tags_filled}"
        f" files_changed={stats.files_changed}"
        f" files_still_missing_tags={stats.files_still_missing_tags}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
