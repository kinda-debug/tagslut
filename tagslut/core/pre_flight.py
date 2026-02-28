"""
Pre-download resolution engine.

Builds a filtered download manifest before any files are downloaded,
preventing redundant downloads of tracks already in the master library
at equal or better quality.
"""
import sqlite3
from dataclasses import dataclass, field
from typing import List

from tagslut.core.quality import compute_quality_rank
from tagslut.filters.identity_resolver import IdentityResolver, ResolutionResult, TrackIntent


@dataclass
class DownloadManifest:
    """
    Output of the pre-flight check. Only 'new' and 'upgrade' tracks
    should be passed to the downloader.
    """

    new: List[ResolutionResult] = field(default_factory=list)
    upgrades: List[ResolutionResult] = field(default_factory=list)
    skipped: List[ResolutionResult] = field(default_factory=list)

    @property
    def download_count(self) -> int:
        return len(self.new) + len(self.upgrades)

    @property
    def skip_count(self) -> int:
        return len(self.skipped)

    def summary(self) -> str:
        return (
            f"Pre-flight: {len(self.new)} new, "
            f"{len(self.upgrades)} upgrades, "
            f"{len(self.skipped)} skipped — "
            f"downloading {self.download_count} tracks"
        )


class PreFlightResolver:
    """
    Resolves a list of TrackIntents against the inventory database
    and produces a DownloadManifest.

    Usage:
        with get_connection(db_path) as conn:
            resolver = PreFlightResolver(conn)
            manifest = resolver.resolve(intents)
            print(manifest.summary())
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._resolver = IdentityResolver(conn)

    def resolve(self, intents: List[TrackIntent]) -> DownloadManifest:
        manifest = DownloadManifest()
        for intent in intents:
            candidate_rank = self._candidate_rank(intent)
            result = self._resolver.resolve(intent, candidate_rank)
            if result.action == "new":
                manifest.new.append(result)
            elif result.action == "upgrade":
                manifest.upgrades.append(result)
            else:
                manifest.skipped.append(result)
        return manifest

    @staticmethod
    def _candidate_rank(intent: TrackIntent) -> int:
        """
        Compute quality rank of the candidate. If provider info is unknown,
        assume worst case (rank 7) to avoid skipping a potentially better file.
        """
        if intent.bit_depth and intent.sample_rate:
            return int(
                compute_quality_rank(
                    intent.bit_depth,
                    intent.sample_rate,
                    intent.bitrate or 0,
                )
            )
        return 7  # unknown = assume worst, always download
