#!/usr/bin/env python3
"""
Verify metadata health results.

Exports suspect files for review and allows confirmation/rejection.
"""

import argparse
import csv
import sqlite3
import subprocess
import sys
from pathlib import Path


def get_suspect_files(db_path: Path, health_type: str = "suspect_truncated"):
    """Get suspect files from database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute("""
        SELECT
            path,
            duration as local_duration,
            canonical_duration,
            canonical_duration_source,
            metadata_health,
            metadata_health_reason,
            enrichment_confidence,
            enrichment_providers
        FROM files
        WHERE metadata_health = ?
        ORDER BY (canonical_duration - duration) DESC
    """, (health_type,))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def export_csv(files: list, output_path: Path):
    """Export suspect files to CSV."""
    if not files:
        print("No files to export.")
        return

    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'path', 'local_duration', 'canonical_duration',
            'delta', 'canonical_duration_source', 'enrichment_confidence',
            'status', 'notes'
        ])
        writer.writeheader()

        for file in files:
            local = file['local_duration'] or 0
            canonical = file['canonical_duration'] or 0
            delta = local - canonical

            writer.writerow({
                'path': file['path'],
                'local_duration': f"{local:.1f}s",
                'canonical_duration': f"{canonical:.1f}s",
                'delta': f"{delta:+.1f}s",
                'canonical_duration_source': file['canonical_duration_source'],
                'enrichment_confidence': file['enrichment_confidence'],
                'status': '',  # User fills: confirmed, false_positive, unknown
                'notes': ''
            })

    print(f"Exported {len(files)} files to {output_path}")


def play_tail(file_path: str, seconds: int = 10):
    """Play the last N seconds of an audio file using ffplay."""
    path = Path(file_path)
    if not path.exists():
        print(f"  File not found: {file_path}")
        return False

    # Get duration first
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
            capture_output=True, text=True, timeout=10
        )
        duration = float(result.stdout.strip())
        start = max(0, duration - seconds)

        print(f"  Playing last {seconds}s (from {start:.1f}s)...")
        subprocess.run(
            ['ffplay', '-nodisp', '-autoexit', '-ss', str(start), str(path)],
            capture_output=True, timeout=seconds + 5
        )
        return True
    except Exception as e:
        print(f"  Error playing: {e}")
        return False


def interactive_review(files: list, play_seconds: int = 10):
    """Interactive review of suspect files."""
    if not files:
        print("No files to review.")
        return

    print(f"\nInteractive review of {len(files)} files")
    print("Commands: [p]lay tail, [c]onfirmed, [f]alse positive, [s]kip, [q]uit\n")

    confirmed = []
    false_positives = []

    for i, file in enumerate(files):
        local = file['local_duration'] or 0
        canonical = file['canonical_duration'] or 0
        delta = local - canonical

        print(f"\n[{i+1}/{len(files)}] {Path(file['path']).name}")
        print(f"  Local: {local:.1f}s | Canonical: {canonical:.1f}s | Delta: {delta:+.1f}s")
        print(f"  Source: {file['canonical_duration_source']} ({file['enrichment_confidence']})")
        print(f"  Path: {file['path']}")

        while True:
            cmd = input("  > ").strip().lower()

            if cmd == 'p':
                play_tail(file['path'], play_seconds)
            elif cmd == 'c':
                confirmed.append(file['path'])
                print("  → Marked as CONFIRMED truncated")
                break
            elif cmd == 'f':
                false_positives.append(file['path'])
                print("  → Marked as FALSE POSITIVE")
                break
            elif cmd == 's':
                print("  → Skipped")
                break
            elif cmd == 'q':
                print("\nQuitting...")
                return confirmed, false_positives
            else:
                print("  Unknown command. Use: p, c, f, s, q")

    return confirmed, false_positives


def print_summary(files: list):
    """Print summary of suspect files."""
    if not files:
        print("No suspect files found.")
        return

    print(f"\n{'='*70}")
    print(f"SUSPECT FILES: {len(files)}")
    print(f"{'='*70}\n")

    for file in files[:20]:  # Show first 20
        local = file['local_duration'] or 0
        canonical = file['canonical_duration'] or 0
        delta = local - canonical
        name = Path(file['path']).name

        # Truncate name if too long
        if len(name) > 40:
            name = name[:37] + "..."

        print(f"  {delta:>+7.1f}s | {name:<40} | {file['enrichment_confidence']}")

    if len(files) > 20:
        print(f"\n  ... and {len(files) - 20} more")

    print(f"\n  Total: {len(files)} files")


def main():
    parser = argparse.ArgumentParser(description="Verify metadata health results")
    parser.add_argument('--db', required=True, help='Path to SQLite database')
    parser.add_argument('--type', choices=['truncated', 'extended', 'both'],
                        default='truncated', help='Type of suspect files to review')
    parser.add_argument('--export', type=Path, help='Export to CSV file')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='Interactive review mode')
    parser.add_argument('--play-seconds', type=int, default=10,
                        help='Seconds to play from end (default: 10)')
    parser.add_argument('--summary', action='store_true', help='Show summary only')

    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    # Get files based on type
    files = []
    if args.type in ('truncated', 'both'):
        files.extend(get_suspect_files(db_path, 'suspect_truncated'))
    if args.type in ('extended', 'both'):
        files.extend(get_suspect_files(db_path, 'suspect_extended'))

    if args.summary or (not args.export and not args.interactive):
        print_summary(files)

    if args.export:
        export_csv(files, args.export)

    if args.interactive:
        confirmed, false_positives = interactive_review(files, args.play_seconds)
        print(f"\nResults: {len(confirmed)} confirmed, {len(false_positives)} false positives")


if __name__ == '__main__':
    main()
