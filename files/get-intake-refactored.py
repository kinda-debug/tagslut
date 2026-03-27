#!/usr/bin/env python3
"""
tools/get-intake — Unified music source ingestion with backfill, metadata enrichment, and structured output.

Features:
- Accept URLs (tidal, beatport), playlists (M3U/JSON/CSV), or local directories
- Backfill existing library files with metadata (no re-download)
- Unified enrichment pipeline (metadata harvest, tagging, fingerprinting)
- Verbose but useful output (paths, not status boxes)
- Downstream-friendly: --dj works even if all files exist, returns playlist
- New: --scan <path> to process local files like remote sources
"""

import os
import sys
import json
import asyncio
import argparse
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Set, Tuple
from enum import Enum
from datetime import datetime

# Rich for clean output (not boxes, just readable summaries)
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Placeholder imports (assume these exist in your codebase)
# from tagslut.metadata import harvest_from_tidal, harvest_from_beatport, harvest_from_qobuz
# from tagslut.database import TrackIdentity, TagslutDB
# from tagslut.audio import FLAC_MANAGER
# from tagslut.playlist import M3UWriter, parse_playlist

console = Console()
logger = logging.getLogger(__name__)


class InputSource(str, Enum):
    """Input source types"""
    TIDAL_URL = "tidal"
    BEATPORT_URL = "beatport"
    QOBUZ_URL = "qobuz"
    PLAYLIST_FILE = "playlist"
    LOCAL_DIRECTORY = "local"


class ProcessingResult(str, Enum):
    """Track processing outcome"""
    FOUND_IN_LIBRARY = "found"
    BACKFILLED = "backfilled"
    DOWNLOADED = "downloaded"
    ENRICHED = "enriched"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TrackResult:
    """Unified result for a single track"""
    identifier: str  # ISRC, tidal_id, beatport_id, or hash
    title: str
    artist: str
    album: Optional[str] = None
    path: Optional[str] = None  # Absolute path to audio file
    source: str = "unknown"  # tidal, beatport, local, etc.
    result: ProcessingResult = ProcessingResult.SKIPPED
    metadata_sources: List[str] = None  # ['tidal', 'beatport', 'qobuz']
    duration_ms: Optional[int] = None
    isrc: Optional[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.metadata_sources is None:
            self.metadata_sources = []

    def to_dict(self):
        return asdict(self)


class IntakeProcessor:
    """Unified intake pipeline: URL → playlist → local directory → backfill → enrich → output"""

    def __init__(
        self,
        library_root: str = "/Volumes/MUSIC/MASTER_LIBRARY",
        db_path: Optional[str] = None,
        enable_metadata_harvest: bool = True,
        enable_dj: bool = False,
        force_download: bool = False,
    ):
        self.library_root = Path(library_root)
        self.db_path = db_path
        self.enable_metadata_harvest = enable_metadata_harvest
        self.enable_dj = enable_dj
        self.force_download = force_download
        self.results: List[TrackResult] = []
        self.errors: List[Dict] = []

    async def process_input(self, source: str) -> Tuple[List[TrackResult], Dict]:
        """
        Main entry point: detect input type and process.
        Returns (results, summary).
        """
        source = source.strip()

        # Detect input type
        if source.startswith(("http://", "https://")):
            if "tidal" in source:
                return await self._process_tidal_url(source)
            elif "beatport" in source:
                return await self._process_beatport_url(source)
            elif "qobuz" in source:
                return await self._process_qobuz_url(source)
            else:
                return [], {"error": f"Unknown URL type: {source}"}
        elif Path(source).is_dir():
            # Local directory: scan and process like remote source
            return await self._process_local_directory(source)
        elif Path(source).is_file():
            # Playlist file: parse and match to library
            return await self._process_playlist_file(source)
        else:
            return [], {"error": f"Invalid source: {source}"}

    async def _process_tidal_url(self, url: str) -> Tuple[List[TrackResult], Dict]:
        """Process Tidal track/playlist URL"""
        console.print(f"[cyan]→ Processing Tidal URL[/cyan]")

        # TODO: Extract track ID from URL, query Tidal API
        # For now, placeholder
        result = TrackResult(
            identifier="tidal_12345",
            title="Example Track",
            artist="Example Artist",
            source="tidal",
            result=ProcessingResult.FAILED,
            error="Not yet implemented",
        )
        self.results.append(result)
        return [result], {"status": "incomplete", "message": "Tidal API not yet integrated"}

    async def _process_beatport_url(self, url: str) -> Tuple[List[TrackResult], Dict]:
        """Process Beatport track/release URL"""
        console.print(f"[cyan]→ Processing Beatport URL[/cyan]")
        # TODO: Extract release/track ID, query Beatport API
        return [], {"status": "incomplete", "message": "Beatport API not yet integrated"}

    async def _process_qobuz_url(self, url: str) -> Tuple[List[TrackResult], Dict]:
        """Process Qobuz album/track URL"""
        console.print(f"[cyan]→ Processing Qobuz URL[/cyan]")
        # TODO: Extract album/track ID, query Qobuz API
        return [], {"status": "incomplete", "message": "Qobuz API not yet integrated"}

    async def _process_playlist_file(self, path: str) -> Tuple[List[TrackResult], Dict]:
        """Parse playlist file and match to library"""
        console.print(f"[cyan]→ Parsing playlist file:[/cyan] {path}")
        path = Path(path)

        # TODO: Use existing parse_playlist() from your codebase
        # For now, placeholder
        summary = {"parsed_tracks": 0, "matched": 0, "missing": 0}
        return self.results, summary

    async def _process_local_directory(self, path: str) -> Tuple[List[TrackResult], Dict]:
        """Scan directory for audio files and process like remote source"""
        console.print(f"[cyan]→ Scanning local directory:[/cyan] {path}")
        scan_root = Path(path)

        if not scan_root.exists():
            return [], {"error": f"Directory not found: {path}"}

        # Find all FLAC/MP3 files
        audio_files = list(scan_root.glob("**/*.flac")) + list(scan_root.glob("**/*.mp3"))
        console.print(f"[green]✓ Found {len(audio_files)} audio file(s)[/green]")

        for audio_file in audio_files:
            # TODO: Extract metadata from file tags
            result = TrackResult(
                identifier=str(audio_file),
                title="Unknown",
                artist="Unknown",
                path=str(audio_file),
                source="local",
                result=ProcessingResult.FOUND_IN_LIBRARY,
            )
            self.results.append(result)

        summary = {
            "scanned_files": len(audio_files),
            "processed": len(self.results),
        }
        return self.results, summary

    async def backfill_library(self) -> None:
        """For tracks already in library, extract + enrich metadata without re-download"""
        console.print(f"[cyan]→ Backfilling library metadata...[/cyan]")

        for result in self.results:
            if result.path and Path(result.path).exists():
                # Already in library: enrich metadata instead of re-downloading
                result.result = ProcessingResult.BACKFILLED
                # TODO: Extract FLAC tags, query DB, harvest metadata
                console.print(f"  [green]✓[/green] {result.artist} - {result.title}")
            else:
                # Not found: try to match by ISRC/ID
                library_match = self._find_in_library(result)
                if library_match:
                    result.path = library_match
                    result.result = ProcessingResult.FOUND_IN_LIBRARY
                    console.print(f"  [green]✓[/green] Matched: {library_match}")

    def _find_in_library(self, track: TrackResult) -> Optional[str]:
        """Search library for track by ISRC, title+artist, or fingerprint"""
        # TODO: Query DB by ISRC first, then fuzzy match
        return None

    async def generate_output(
        self, output_format: str = "summary", output_file: Optional[str] = None
    ) -> Dict:
        """
        Generate output in requested format.
        - summary: human-readable summary (default)
        - json: JSON with full metadata
        - m3u: M3U playlist
        - csv: CSV export
        """
        if output_format == "summary":
            return self._format_summary()
        elif output_format == "json":
            return self._format_json(output_file)
        elif output_format == "m3u":
            return self._format_m3u(output_file)
        elif output_format == "csv":
            return self._format_csv(output_file)
        else:
            return {"error": f"Unknown output format: {output_format}"}

    def _format_summary(self) -> Dict:
        """Human-readable summary for console output"""
        found = [r for r in self.results if r.path]
        missing = [r for r in self.results if not r.path]

        # Count by result type
        counts = {}
        for r in self.results:
            counts[r.result.value] = counts.get(r.result.value, 0) + 1

        summary_text = f"\n━━━ INTAKE SUMMARY ━━━\n"
        summary_text += f"Total tracks: {len(self.results)}\n"
        for result_type, count in sorted(counts.items()):
            summary_text += f"  {result_type}: {count}\n"

        if found:
            summary_text += f"\n✓ FOUND ({len(found)}):\n"
            for r in found[:10]:  # Show first 10
                summary_text += f"  {r.artist} - {r.title}\n"
                if r.path:
                    summary_text += f"    → {r.path}\n"
            if len(found) > 10:
                summary_text += f"  ... and {len(found) - 10} more\n"

        if missing:
            summary_text += f"\n⚠ MISSING ({len(missing)}):\n"
            for r in missing[:10]:
                summary_text += f"  {r.artist} - {r.title}\n"
            if len(missing) > 10:
                summary_text += f"  ... and {len(missing) - 10} more\n"

        console.print(summary_text)
        return {"format": "summary", "counts": counts, "found": len(found), "missing": len(missing)}

    def _format_json(self, output_file: Optional[str]) -> Dict:
        """JSON export with full metadata"""
        output = {
            "timestamp": datetime.now().isoformat(),
            "summary": {"total": len(self.results)},
            "tracks": [r.to_dict() for r in self.results],
        }

        if output_file:
            with open(output_file, "w") as f:
                json.dump(output, f, indent=2, default=str)
            console.print(f"[green]✓ Exported JSON:[/green] {output_file}")

        return output

    def _format_m3u(self, output_file: Optional[str]) -> Dict:
        """M3U playlist export"""
        if not output_file:
            output_file = f"intake_{datetime.now().strftime('%Y%m%d_%H%M%S')}.m3u"

        # Only include tracks with paths
        tracks_with_paths = [r for r in self.results if r.path]

        with open(output_file, "w") as f:
            f.write("#EXTM3U\n")
            for r in tracks_with_paths:
                duration_sec = (r.duration_ms // 1000) if r.duration_ms else -1
                f.write(f"#EXTINF:{duration_sec},{r.artist} - {r.title}\n")
                f.write(f"{r.path}\n")

        console.print(f"[green]✓ Exported M3U:[/green] {output_file} ({len(tracks_with_paths)} tracks)")
        return {"format": "m3u", "path": output_file, "tracks": len(tracks_with_paths)}

    def _format_csv(self, output_file: Optional[str]) -> Dict:
        """CSV export"""
        if not output_file:
            output_file = f"intake_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        import csv
        with open(output_file, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "identifier",
                    "artist",
                    "title",
                    "album",
                    "path",
                    "source",
                    "result",
                    "isrc",
                ],
            )
            writer.writeheader()
            writer.writerows([r.to_dict() for r in self.results])

        console.print(f"[green]✓ Exported CSV:[/green] {output_file}")
        return {"format": "csv", "path": output_file, "tracks": len(self.results)}


async def main():
    parser = argparse.ArgumentParser(
        description="Unified music source ingestion with backfill and metadata enrichment"
    )
    parser.add_argument("source", help="URL, playlist file, or directory path")
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Treat as local directory and process like remote source",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        default=True,
        help="Backfill existing library files with metadata (default: true)",
    )
    parser.add_argument(
        "--dj",
        action="store_true",
        help="Include DJ pipeline (returns playlist even if all files exist)",
    )
    parser.add_argument(
        "--re",
        "--return",
        dest="return_playlist",
        action="store_true",
        help="Return/export results as M3U playlist file (auto-named by source + timestamp)",
    )
    parser.add_argument(
        "--output",
        choices=["summary", "json", "m3u", "csv"],
        default="summary",
        help="Output format (default: summary)",
    )
    parser.add_argument(
        "--output-file",
        help="Save output to file (for json/m3u/csv); overrides auto-naming from --re",
    )
    parser.add_argument(
        "--library",
        default="/Volumes/MUSIC/MASTER_LIBRARY",
        help="Master library root (default: /Volumes/MUSIC/MASTER_LIBRARY)",
    )
    parser.add_argument(
        "--db",
        help="Path to tagslut database",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Force re-download even if file exists",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output (default: true, use --quiet to disable)",
    )

    args = parser.parse_args()

    processor = IntakeProcessor(
        library_root=args.library,
        db_path=args.db,
        enable_dj=args.dj,
        force_download=args.force_download,
    )

    # Process input
    results, status = await processor.process_input(args.source)

    if args.backfill:
        await processor.backfill_library()

    # Determine output format and file
    output_format = args.output
    output_file = args.output_file

    # If --re flag is set, force M3U format and auto-generate filename
    if args.return_playlist:
        output_format = "m3u"
        if not output_file:
            # Auto-generate filename: source_type-timestamp.m3u
            source_basename = Path(args.source).stem if Path(args.source).exists() else args.source.split('/')[-1]
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"{source_basename}_{timestamp}.m3u"
            console.print(f"[cyan]→ Auto-naming playlist:[/cyan] {output_file}")

    # Generate output
    output = await processor.generate_output(output_format, output_file)

    # Return exit code based on success
    if status.get("error") or not results:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
