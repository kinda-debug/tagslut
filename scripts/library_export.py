#!/usr/bin/env python3
"""
library_export.py - Scan audio library and export analysis data for Postman workflows.

Extracts genres, tags, identifiers, and durations from local audio files,
outputting NDJSON suitable for Postman Collection Runner data-driven testing.

Usage:
    python library_export.py /path/to/music --output library_export.ndjson
    python library_export.py /path/to/music --output library.ndjson --csv library.csv

Requirements:
    pip install mutagen tqdm
"""

import argparse
import json
import logging
import os
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Iterator

from mutagen import MutagenError
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

SCANNER_VERSION = "1.0.0"
DURATION_TOLERANCE_MS = 2000  # 2 seconds


@dataclass
class TrackRecord:
    """Canonical export record for a single audio file."""
    path: str
    filename: str
    identifiers: Dict[str, Optional[str]]
    tags: Dict[str, Any]
    durations: Dict[str, Any]
    technical: Dict[str, Any]
    export_meta: Dict[str, str]


def get_tag_value(tags: Dict[str, Any], *keys: str) -> Optional[str]:
    """Get first matching tag value from multiple possible keys."""
    for key in keys:
        key_lower = key.lower()
        if key_lower in tags:
            val = tags[key_lower]
            if isinstance(val, (list, tuple)):
                return str(val[0]) if val else None
            return str(val) if val else None
    return None


def get_tag_int(tags: Dict[str, Any], *keys: str) -> Optional[int]:
    """Get first matching tag as integer."""
    val = get_tag_value(tags, *keys)
    if val:
        # Handle "1/12" format for track numbers
        if '/' in val:
            val = val.split('/')[0]
        try:
            return int(float(val))
        except (ValueError, TypeError):
            pass
    return None


def get_tag_float(tags: Dict[str, Any], *keys: str) -> Optional[float]:
    """Get first matching tag as float."""
    val = get_tag_value(tags, *keys)
    if val:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    return None


def extract_beatport_id_from_url(url: Optional[str]) -> Optional[str]:
    """Extract numeric ID from Beatport URL."""
    if not url:
        return None
    # Pattern: https://www.beatport.com/track/name/12345678
    match = re.search(r'/(\d{6,})(?:/|$|\?)', url)
    return match.group(1) if match else None


def extract_identifiers(tags: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Extract all known identifiers from tags."""
    beatport_id = get_tag_value(tags, 'beatport_track_id', 'beatport_id')
    if not beatport_id:
        beatport_id = extract_beatport_id_from_url(
            get_tag_value(tags, 'beatport_track_url', 'beatport_url')
        )
    
    beatport_release_id = get_tag_value(tags, 'beatport_release_id')
    if not beatport_release_id:
        beatport_release_id = extract_beatport_id_from_url(
            get_tag_value(tags, 'beatport_release_url')
        )
    
    return {
        'musicbrainz_track_id': get_tag_value(tags, 'musicbrainz_trackid', 'musicbrainz_track_id'),
        'musicbrainz_release_id': get_tag_value(tags, 'musicbrainz_albumid', 'musicbrainz_release_id'),
        'musicbrainz_artist_id': get_tag_value(tags, 'musicbrainz_artistid'),
        'isrc': get_tag_value(tags, 'isrc'),
        'beatport_track_id': beatport_id,
        'beatport_release_id': beatport_release_id,
        'discogs_release_id': get_tag_value(tags, 'discogs_release_id', 'discogs_release'),
        'spotify_id': get_tag_value(tags, 'spotify_id', 'spotify_track_id'),
        'tidal_id': get_tag_value(tags, 'tidal_id', 'tidal_track_id'),
        'acoustid': get_tag_value(tags, 'acoustid_id', 'acoustid'),
    }


def extract_basic_tags(tags: Dict[str, Any]) -> Dict[str, Any]:
    """Extract basic metadata tags."""
    return {
        'artist': get_tag_value(tags, 'artist'),
        'album_artist': get_tag_value(tags, 'albumartist', 'album_artist'),
        'title': get_tag_value(tags, 'title'),
        'album': get_tag_value(tags, 'album'),
        'track_number': get_tag_int(tags, 'tracknumber', 'track'),
        'disc_number': get_tag_int(tags, 'discnumber', 'disc'),
        'total_tracks': get_tag_int(tags, 'tracktotal', 'totaltracks'),
        'total_discs': get_tag_int(tags, 'disctotal', 'totaldiscs'),
        'year': get_tag_int(tags, 'date', 'year', 'originaldate'),
        'genre': get_tag_value(tags, 'genre'),
        'label': get_tag_value(tags, 'label', 'publisher', 'organization'),
        'catalog_number': get_tag_value(tags, 'catalognumber', 'catalog', 'labelno'),
        'bpm': get_tag_float(tags, 'bpm', 'tbpm'),
        'key': get_tag_value(tags, 'initialkey', 'key'),
        'comment': get_tag_value(tags, 'comment', 'description'),
    }


def extract_durations(tags: Dict[str, Any], actual_duration_sec: float) -> Dict[str, Any]:
    """
    Extract and compare duration values.
    
    Three duration sources:
    1. tag_ms: From embedded tags (MUSICBRAINZ_TRACK_LENGTH, etc.)
    2. actual_ms: From decoded audio stream (ground truth)
    3. external_ms: To be filled later from Beatport/iTunes API
    """
    actual_ms = int(actual_duration_sec * 1000)
    
    # Try to get tagged duration (MusicBrainz stores in milliseconds)
    tag_ms = None
    mb_length = get_tag_value(tags, 'musicbrainz_track_length')
    if mb_length:
        try:
            tag_ms = int(float(mb_length))
        except (ValueError, TypeError):
            pass
    
    # Fallback: some taggers store duration in seconds
    if tag_ms is None:
        duration_tag = get_tag_float(tags, 'length', 'duration')
        if duration_tag:
            # Heuristic: if < 1000, assume seconds; otherwise milliseconds
            tag_ms = int(duration_tag * 1000) if duration_tag < 1000 else int(duration_tag)
    
    # Calculate mismatch
    mismatch_flag = False
    mismatch_delta_ms = None
    if tag_ms is not None:
        mismatch_delta_ms = actual_ms - tag_ms
        mismatch_flag = abs(mismatch_delta_ms) > DURATION_TOLERANCE_MS
    
    return {
        'tag_ms': tag_ms,
        'actual_ms': actual_ms,
        'external_ms': None,  # To be filled by Postman workflow
        'external_source': None,
        'mismatch_flag': mismatch_flag,
        'mismatch_delta_ms': mismatch_delta_ms,
    }


def extract_technical(audio: Any, file_path: Path) -> Dict[str, Any]:
    """Extract technical audio properties."""
    info = audio.info if hasattr(audio, 'info') else None
    
    # Get STREAMINFO MD5 for FLAC files
    streaminfo_md5 = None
    if info and hasattr(info, 'md5_signature'):
        md5_sig = info.md5_signature
        if isinstance(md5_sig, (bytes, bytearray)):
            streaminfo_md5 = md5_sig.hex()
        elif isinstance(md5_sig, int):
            streaminfo_md5 = f"{md5_sig:032x}"
        elif md5_sig:
            streaminfo_md5 = str(md5_sig)
    
    return {
        'sample_rate': getattr(info, 'sample_rate', None) if info else None,
        'bit_depth': getattr(info, 'bits_per_sample', None) if info else None,
        'bitrate': getattr(info, 'bitrate', None) if info else None,
        'channels': getattr(info, 'channels', None) if info else None,
        'streaminfo_md5': streaminfo_md5,
        'file_size_bytes': file_path.stat().st_size,
    }


def scan_file(file_path: Path) -> Optional[TrackRecord]:
    """Scan a single audio file and return a TrackRecord."""
    try:
        # Detect format and load
        suffix = file_path.suffix.lower()
        if suffix == '.flac':
            audio = FLAC(file_path)
        elif suffix == '.mp3':
            audio = MP3(file_path)
        elif suffix in ('.m4a', '.mp4', '.aac'):
            audio = MP4(file_path)
        else:
            logger.debug(f"Unsupported format: {file_path}")
            return None
        
        # Extract tags as lowercase dict
        tags: Dict[str, Any] = {}
        if audio.tags:
            for k, v in audio.tags.items():
                key = k.lower() if isinstance(k, str) else str(k).lower()
                if isinstance(v, (list, tuple)):
                    tags[key] = [str(x) for x in v] if len(v) > 1 else str(v[0]) if v else None
                else:
                    tags[key] = str(v) if v else None
        
        # Get actual duration
        actual_duration = audio.info.length if audio.info else 0.0
        
        return TrackRecord(
            path=str(file_path),
            filename=file_path.name,
            identifiers=extract_identifiers(tags),
            tags=extract_basic_tags(tags),
            durations=extract_durations(tags, actual_duration),
            technical=extract_technical(audio, file_path),
            export_meta={
                'exported_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'scanner_version': SCANNER_VERSION,
            }
        )
    
    except MutagenError as e:
        logger.warning(f"Failed to read {file_path}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error scanning {file_path}: {e}")
        return None


def find_audio_files(root_path: Path) -> Iterator[Path]:
    """Recursively find all audio files."""
    extensions = {'.flac', '.mp3', '.m4a', '.mp4', '.aac'}
    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            if Path(filename).suffix.lower() in extensions:
                yield Path(dirpath) / filename


def scan_library(
    root_path: Path,
    output_path: Path,
    resume: bool = True
) -> Dict[str, int]:
    """
    Scan entire library and write NDJSON output.
    
    Returns statistics dict.
    """
    # Count files for progress bar
    logger.info(f"Counting files in {root_path}...")
    all_files = list(find_audio_files(root_path))
    total_files = len(all_files)
    logger.info(f"Found {total_files} audio files")
    
    # Check for resume
    processed_paths = set()
    if resume and output_path.exists():
        logger.info("Checking for existing progress...")
        with open(output_path, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line)
                    processed_paths.add(record.get('path'))
                except json.JSONDecodeError:
                    continue
        logger.info(f"Resuming: {len(processed_paths)} already processed")
    
    stats = {
        'total': total_files,
        'processed': 0,
        'skipped': len(processed_paths),
        'failed': 0,
        'with_beatport_id': 0,
        'with_isrc': 0,
        'with_duration_mismatch': 0,
    }
    
    mode = 'a' if resume else 'w'
    with open(output_path, mode) as out_file:
        for file_path in tqdm(all_files, desc="Scanning"):
            if str(file_path) in processed_paths:
                continue
            
            record = scan_file(file_path)
            if record:
                # Write NDJSON line
                out_file.write(json.dumps(asdict(record)) + '\n')
                stats['processed'] += 1
                
                # Update stats
                if record.identifiers.get('beatport_track_id'):
                    stats['with_beatport_id'] += 1
                if record.identifiers.get('isrc'):
                    stats['with_isrc'] += 1
                if record.durations.get('mismatch_flag'):
                    stats['with_duration_mismatch'] += 1
            else:
                stats['failed'] += 1
    
    return stats


def export_csv_summary(ndjson_path: Path, csv_path: Path) -> None:
    """Export a CSV summary from NDJSON for quick analysis."""
    import csv
    
    columns = [
        'path', 'artist', 'title', 'album', 'isrc', 'beatport_track_id',
        'tag_ms', 'actual_ms', 'mismatch_flag', 'genre', 'bpm', 'key'
    ]
    
    with open(ndjson_path, 'r') as infile, open(csv_path, 'w', newline='') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=columns)
        writer.writeheader()
        
        for line in infile:
            try:
                record = json.loads(line)
                row = {
                    'path': record.get('path'),
                    'artist': record.get('tags', {}).get('artist'),
                    'title': record.get('tags', {}).get('title'),
                    'album': record.get('tags', {}).get('album'),
                    'isrc': record.get('identifiers', {}).get('isrc'),
                    'beatport_track_id': record.get('identifiers', {}).get('beatport_track_id'),
                    'tag_ms': record.get('durations', {}).get('tag_ms'),
                    'actual_ms': record.get('durations', {}).get('actual_ms'),
                    'mismatch_flag': record.get('durations', {}).get('mismatch_flag'),
                    'genre': record.get('tags', {}).get('genre'),
                    'bpm': record.get('tags', {}).get('bpm'),
                    'key': record.get('tags', {}).get('key'),
                }
                writer.writerow(row)
            except json.JSONDecodeError:
                continue
    
    logger.info(f"CSV summary written to {csv_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Export audio library metadata for Postman workflows'
    )
    parser.add_argument('library_path', type=Path, help='Root path of audio library')
    parser.add_argument('--output', '-o', type=Path, default=Path('library_export.ndjson'),
                        help='Output NDJSON file (default: library_export.ndjson)')
    parser.add_argument('--csv', type=Path, help='Also export CSV summary')
    parser.add_argument('--no-resume', action='store_true', help='Start fresh, ignore existing output')
    
    args = parser.parse_args()
    
    if not args.library_path.exists():
        logger.error(f"Library path does not exist: {args.library_path}")
        return 1
    
    stats = scan_library(args.library_path, args.output, resume=not args.no_resume)
    
    logger.info("\n=== Scan Complete ===")
    logger.info(f"Total files:           {stats['total']}")
    logger.info(f"Processed:             {stats['processed']}")
    logger.info(f"Previously processed:  {stats['skipped']}")
    logger.info(f"Failed:                {stats['failed']}")
    logger.info(f"With Beatport ID:      {stats['with_beatport_id']}")
    logger.info(f"With ISRC:             {stats['with_isrc']}")
    logger.info(f"Duration mismatches:   {stats['with_duration_mismatch']}")
    logger.info(f"\nOutput: {args.output}")
    
    if args.csv:
        export_csv_summary(args.output, args.csv)
    
    return 0


if __name__ == '__main__':
    exit(main())
