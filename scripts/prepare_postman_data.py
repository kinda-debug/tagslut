#!/usr/bin/env python3
"""
prepare_postman_data.py - Convert library export to Postman-ready data files.

Creates filtered CSV files for different API lookup workflows:
- beatport_lookup.csv: Tracks with Beatport IDs
- isrc_lookup.csv: Tracks with ISRCs (for iTunes/MusicBrainz)
- search_lookup.csv: Tracks without IDs (need artist+title search)
- duration_mismatches.csv: Tracks flagged for duration issues

Usage:
    python prepare_postman_data.py library_export.ndjson --output-dir ./postman_data
"""

import argparse
import csv
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def load_ndjson(path: Path) -> List[Dict[str, Any]]:
    """Load all records from NDJSON file."""
    records = []
    with open(path, 'r') as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def export_beatport_lookup(records: List[Dict], output_path: Path) -> int:
    """Export tracks with Beatport IDs for direct API lookup."""
    columns = ['path', 'beatport_id', 'artist', 'title', 'actual_ms', 'tag_ms', 'isrc']
    
    count = 0
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        
        for record in records:
            beatport_id = record.get('identifiers', {}).get('beatport_track_id')
            if beatport_id:
                writer.writerow({
                    'path': record.get('path'),
                    'beatport_id': beatport_id,
                    'artist': record.get('tags', {}).get('artist'),
                    'title': record.get('tags', {}).get('title'),
                    'actual_ms': record.get('durations', {}).get('actual_ms'),
                    'tag_ms': record.get('durations', {}).get('tag_ms'),
                    'isrc': record.get('identifiers', {}).get('isrc'),
                })
                count += 1
    
    return count


def export_isrc_lookup(records: List[Dict], output_path: Path) -> int:
    """Export tracks with ISRCs for iTunes/MusicBrainz lookup."""
    columns = ['path', 'isrc', 'artist', 'title', 'actual_ms', 'tag_ms', 'beatport_id']
    
    count = 0
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        
        for record in records:
            isrc = record.get('identifiers', {}).get('isrc')
            if isrc:
                writer.writerow({
                    'path': record.get('path'),
                    'isrc': isrc,
                    'artist': record.get('tags', {}).get('artist'),
                    'title': record.get('tags', {}).get('title'),
                    'actual_ms': record.get('durations', {}).get('actual_ms'),
                    'tag_ms': record.get('durations', {}).get('tag_ms'),
                    'beatport_id': record.get('identifiers', {}).get('beatport_track_id'),
                })
                count += 1
    
    return count


def export_search_lookup(records: List[Dict], output_path: Path) -> int:
    """Export tracks without IDs that need artist+title search."""
    columns = ['path', 'artist', 'title', 'album', 'actual_ms', 'genre', 'year']
    
    count = 0
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        
        for record in records:
            identifiers = record.get('identifiers', {})
            # No useful identifiers
            if not any([
                identifiers.get('beatport_track_id'),
                identifiers.get('isrc'),
                identifiers.get('musicbrainz_track_id'),
            ]):
                tags = record.get('tags', {})
                # But has artist and title for search
                if tags.get('artist') and tags.get('title'):
                    writer.writerow({
                        'path': record.get('path'),
                        'artist': tags.get('artist'),
                        'title': tags.get('title'),
                        'album': tags.get('album'),
                        'actual_ms': record.get('durations', {}).get('actual_ms'),
                        'genre': tags.get('genre'),
                        'year': tags.get('year'),
                    })
                    count += 1
    
    return count


def export_duration_mismatches(records: List[Dict], output_path: Path) -> int:
    """Export tracks with duration mismatches for investigation."""
    columns = [
        'path', 'artist', 'title', 'tag_ms', 'actual_ms', 'delta_ms',
        'beatport_id', 'isrc', 'streaminfo_md5'
    ]
    
    count = 0
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        
        for record in records:
            durations = record.get('durations', {})
            if durations.get('mismatch_flag'):
                writer.writerow({
                    'path': record.get('path'),
                    'artist': record.get('tags', {}).get('artist'),
                    'title': record.get('tags', {}).get('title'),
                    'tag_ms': durations.get('tag_ms'),
                    'actual_ms': durations.get('actual_ms'),
                    'delta_ms': durations.get('mismatch_delta_ms'),
                    'beatport_id': record.get('identifiers', {}).get('beatport_track_id'),
                    'isrc': record.get('identifiers', {}).get('isrc'),
                    'streaminfo_md5': record.get('technical', {}).get('streaminfo_md5'),
                })
                count += 1
    
    return count


def export_full_summary(records: List[Dict], output_path: Path) -> int:
    """Export full summary CSV with all key fields."""
    columns = [
        'path', 'filename', 'artist', 'title', 'album', 'genre', 'bpm', 'key',
        'year', 'label', 'isrc', 'beatport_id', 'musicbrainz_id', 'spotify_id',
        'tag_ms', 'actual_ms', 'mismatch_flag', 'sample_rate', 'bit_depth'
    ]
    
    count = 0
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        
        for record in records:
            tags = record.get('tags', {})
            ids = record.get('identifiers', {})
            durations = record.get('durations', {})
            tech = record.get('technical', {})
            
            writer.writerow({
                'path': record.get('path'),
                'filename': record.get('filename'),
                'artist': tags.get('artist'),
                'title': tags.get('title'),
                'album': tags.get('album'),
                'genre': tags.get('genre'),
                'bpm': tags.get('bpm'),
                'key': tags.get('key'),
                'year': tags.get('year'),
                'label': tags.get('label'),
                'isrc': ids.get('isrc'),
                'beatport_id': ids.get('beatport_track_id'),
                'musicbrainz_id': ids.get('musicbrainz_track_id'),
                'spotify_id': ids.get('spotify_id'),
                'tag_ms': durations.get('tag_ms'),
                'actual_ms': durations.get('actual_ms'),
                'mismatch_flag': durations.get('mismatch_flag'),
                'sample_rate': tech.get('sample_rate'),
                'bit_depth': tech.get('bit_depth'),
            })
            count += 1
    
    return count


def main():
    parser = argparse.ArgumentParser(
        description='Convert library export to Postman-ready data files'
    )
    parser.add_argument('input', type=Path, help='Input NDJSON file from library_export.py')
    parser.add_argument('--output-dir', '-o', type=Path, default=Path('./postman_data'),
                        help='Output directory for CSV files')
    
    args = parser.parse_args()
    
    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        return 1
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Loading records from {args.input}...")
    records = load_ndjson(args.input)
    logger.info(f"Loaded {len(records)} records")
    
    # Export different subsets
    exports = [
        ('beatport_lookup.csv', export_beatport_lookup),
        ('isrc_lookup.csv', export_isrc_lookup),
        ('search_lookup.csv', export_search_lookup),
        ('duration_mismatches.csv', export_duration_mismatches),
        ('full_summary.csv', export_full_summary),
    ]
    
    logger.info("\n=== Exporting Postman Data Files ===")
    for filename, export_func in exports:
        output_path = args.output_dir / filename
        count = export_func(records, output_path)
        logger.info(f"  {filename}: {count} records")
    
    logger.info(f"\nOutput directory: {args.output_dir}")
    return 0


if __name__ == '__main__':
    exit(main())
