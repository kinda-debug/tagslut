"""Pre-download resolution manifest builder for intake workflows."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from tagslut.core.quality import compute_quality_rank
from tagslut.filters.identity_resolver import IdentityResolver, TrackIntent


@dataclass
class ManifestEntry:
    """A single manifest decision entry for one intended track."""

    track_intent: TrackIntent
    action: str
    reason: str
    existing_path: str | None = None
    existing_quality_rank: int | None = None
    candidate_quality_rank: int | None = None
    match_method: str | None = None
    match_score: float | None = None


@dataclass
class DownloadManifest:
    """Manifest containing deterministic NEW/UPGRADE/SKIP buckets."""

    new: list[ManifestEntry] = field(default_factory=list)
    upgrades: list[ManifestEntry] = field(default_factory=list)
    skipped: list[ManifestEntry] = field(default_factory=list)

    @property
    def download_count(self) -> int:
        return len(self.new) + len(self.upgrades)

    def summary(self) -> str:
        return (
            f"Manifest: {len(self.new)} new, {len(self.upgrades)} upgrades, "
            f"{len(self.skipped)} skipped"
        )

    def to_dict(self) -> dict:
        def _entry_dict(entry: ManifestEntry) -> dict:
            payload = asdict(entry)
            payload["track_intent"] = asdict(entry.track_intent)
            return payload

        return {
            "new": [_entry_dict(entry) for entry in self.new],
            "upgrades": [_entry_dict(entry) for entry in self.upgrades],
            "skipped": [_entry_dict(entry) for entry in self.skipped],
            "counts": {
                "new": len(self.new),
                "upgrades": len(self.upgrades),
                "skipped": len(self.skipped),
                "download": self.download_count,
            },
            "summary": self.summary(),
        }

    def to_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )


def _candidate_rank(intent: TrackIntent) -> int:
    explicit_rank = getattr(intent, "candidate_quality_rank", None)
    if explicit_rank is None:
        explicit_rank = getattr(intent, "quality_rank", None)
    if explicit_rank is not None:
        try:
            return int(explicit_rank)
        except (TypeError, ValueError):
            pass

    if intent.bit_depth is not None and intent.sample_rate is not None:
        return int(
            compute_quality_rank(
                int(intent.bit_depth),
                int(intent.sample_rate),
                int(intent.bitrate or 0),
            )
        )

    if intent.bitrate is not None:
        return 6 if int(intent.bitrate) >= 320000 else 7

    # Unknown quality => assume worst and allow download.
    return 7


def _build_reason(
    action: str,
    *,
    match_method: str | None,
    existing_rank: int | None,
    candidate_rank: int,
) -> str:
    if action == "new":
        return "no inventory match"

    method = match_method or "unknown"
    if action == "upgrade":
        return f"matched by {method}; candidate rank {candidate_rank} improves existing rank {existing_rank}"

    return f"matched by {method}; existing rank {existing_rank} is equal or better than candidate rank {candidate_rank}"


def build_manifest(track_intents: Iterable[TrackIntent], conn: sqlite3.Connection) -> DownloadManifest:
    """Resolve track intents against inventory and build a deterministic manifest."""
    resolver = IdentityResolver(conn)
    manifest = DownloadManifest()

    for intent in track_intents:
        candidate_rank = _candidate_rank(intent)
        resolution = resolver.resolve(intent, candidate_rank)
        entry = ManifestEntry(
            track_intent=intent,
            action=resolution.action,
            reason=_build_reason(
                resolution.action,
                match_method=resolution.match_method,
                existing_rank=resolution.existing_quality_rank,
                candidate_rank=candidate_rank,
            ),
            existing_path=resolution.existing_path,
            existing_quality_rank=resolution.existing_quality_rank,
            candidate_quality_rank=candidate_rank,
            match_method=resolution.match_method,
            match_score=resolution.match_score,
        )

        if resolution.action == "new":
            manifest.new.append(entry)
        elif resolution.action == "upgrade":
            manifest.upgrades.append(entry)
        else:
            manifest.skipped.append(entry)

    return manifest
