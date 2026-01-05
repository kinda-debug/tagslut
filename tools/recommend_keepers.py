#!/usr/bin/env python3
"""
Deterministic KEEP/REVIEW decision engine for duplicate audio files.

Decision hierarchy (locked in):
  1. Identity layer: AcoustID recording ID conflicts → REVIEW
  2. Duration authority: ±0.2s from reference → VALID/TAINTED
  3. Technical quality: bit depth > sample rate > decode health
  4. Metadata: tie-breaker only

Core constraint: "Longer never wins" (recovered files usually too long)

Usage:
  # Dry-run (report only)
  tools/recommend_keepers.py --db /Volumes/COMMUNE/20_ACCEPTED/commune_hash.sqlite \\
                             --group-field checksum \\
                             --out /tmp/commune_recommendations.csv

  # Apply decisions to DB
  tools/recommend_keepers.py --db /Volumes/COMMUNE/20_ACCEPTED/commune_hash.sqlite \\
                             --group-field checksum \\
                             --out /tmp/commune_recommendations.csv \\
                             --apply
"""
import argparse
import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


# Decision constants
DURATION_TOLERANCE = 0.2  # seconds
CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"

DECISION_KEEP = "KEEP"
DECISION_DROP = "DROP"
DECISION_REVIEW = "REVIEW"


def ensure_decision_columns(conn: sqlite3.Connection):
    """Add decision columns if they don't exist."""
    cursor = conn.cursor()
    
    # Check existing columns
    cursor.execute("PRAGMA table_info(library_files)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    
    new_cols = {
        "acoustid_id": "TEXT",
        "acoustid_duration": "REAL",
        "duration_delta": "REAL",
        "decision": "TEXT",
        "decision_reason": "TEXT",
        "decision_confidence": "TEXT"
    }
    
    for col, dtype in new_cols.items():
        if col not in existing_cols:
            print(f"Adding column: {col}")
            cursor.execute(f"ALTER TABLE library_files ADD COLUMN {col} {dtype}")
    
    conn.commit()


def load_duplicate_groups(conn: sqlite3.Connection, group_field: str) -> Dict[str, List[Dict]]:
    """Load all duplicate groups from DB."""
    cursor = conn.cursor()
    
    # Build query dynamically based on available columns
    cursor.execute("PRAGMA table_info(library_files)")
    available_cols = {row[1] for row in cursor.fetchall()}
    
    base_cols = ["path", group_field, "duration", "extra_json"]
    optional_cols = [
        "acoustid_id",
        "acoustid_duration",
        "bit_depth",
        "sample_rate",
        "bitrate",
        "flac_ok",
        "integrity_state",
    ]
    
    cols = base_cols + [c for c in optional_cols if c in available_cols]
    
    query = f"""
        SELECT {', '.join(cols)}
        FROM library_files
        WHERE {group_field} IS NOT NULL
        ORDER BY {group_field}, path
    """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    groups = defaultdict(list)
    for row in rows:
        record = dict(zip(cols, row))
        group_id = record[group_field]
        groups[group_id].append(record)
    
    # Filter to only actual duplicates (2+ files)
    return {k: v for k, v in groups.items() if len(v) > 1}


def compute_duration_delta(file_duration: float, reference_duration: float = None) -> Tuple[float, bool]:
    """
    Compute duration delta and validity.
    
    Returns:
        (delta, is_valid) where delta is absolute difference and is_valid means within tolerance
    """
    if reference_duration is None:
        return 0.0, True  # No reference = assume valid
    
    delta = abs(file_duration - reference_duration)
    is_valid = delta <= DURATION_TOLERANCE
    return delta, is_valid


def extract_technical_quality(record: Dict) -> Tuple[int, int, int]:
    """
    Extract technical quality metrics for comparison.
    
    Returns:
        (bit_depth, sample_rate, bitrate) tuple
    """
    bit_depth = record.get("bit_depth") or 16
    sample_rate = record.get("sample_rate") or 44100
    bitrate = record.get("bitrate") or 0
    
    return (bit_depth, sample_rate, bitrate)


def decide_keeper(group: List[Dict], group_id: str) -> List[Tuple[Dict, str, str, str]]:
    """
    Decide KEEP/REVIEW for a duplicate group.
    
    Returns:
        List of (record, decision, reason, confidence) tuples
    """
    # Integrity gate: flag non-valid files for review
    integrity_results = []
    for record in group:
        integrity_state = record.get("integrity_state")
        flac_ok = record.get("flac_ok")
        if integrity_state in {"recoverable", "corrupt"}:
            integrity_results.append((record, DECISION_DROP, f"flac_{integrity_state}", CONFIDENCE_HIGH))
        elif flac_ok is not None and flac_ok == 0:
            integrity_results.append((record, DECISION_DROP, "flac_corrupt", CONFIDENCE_HIGH))
    
    # If all files corrupt, return early
    if len(integrity_results) == len(group):
        return integrity_results
    
    # Filter out corrupt files for further evaluation
    valid_group = [
        r
        for r in group
        if r.get("integrity_state") in (None, "valid")
        and r.get("flac_ok") != 0
    ]
    
    # Identity layer: check AcoustID conflicts
    acoustid_ids = {r.get("acoustid_id") for r in valid_group if r.get("acoustid_id")}
    if len(acoustid_ids) > 1:
        # Multiple distinct recording IDs = identity conflict
        return integrity_results + [(r, DECISION_REVIEW, "identity_conflict", CONFIDENCE_HIGH) for r in valid_group]
    
    # Duration authority: establish reference
    acoustid_durations = [r.get("acoustid_duration") for r in valid_group if r.get("acoustid_duration")]
    if acoustid_durations:
        ref_duration = acoustid_durations[0]  # Use AcoustID if available
    else:
        # Fallback: median of actual durations
        durations = sorted([r["duration"] for r in valid_group if r.get("duration")])
        ref_duration = durations[len(durations) // 2] if durations else None
    
    # Compute validity for each file
    validity_data = []
    for record in valid_group:
        delta, is_valid = compute_duration_delta(record.get("duration"), ref_duration)
        record["duration_delta"] = delta
        validity_data.append((record, is_valid, delta))
    
    # Filter to VALID files only
    valid_files = [(r, d) for r, is_valid, d in validity_data if is_valid]
    
    if len(valid_files) == 0:
        # No valid files: pick smallest delta, mark LOW confidence
        best = min(validity_data, key=lambda x: x[2])
        decisions = []
        for record, is_valid, delta in validity_data:
            if record == best[0]:
                decisions.append((record, DECISION_KEEP, "least_duration_delta", CONFIDENCE_LOW))
            else:
                decisions.append((record, DECISION_DROP, "duration_mismatch", CONFIDENCE_MEDIUM))
        return integrity_results + decisions
    
    if len(valid_files) == 1:
        # Exactly one valid: automatic KEEP
        keeper = valid_files[0][0]
        decisions = []
        for record, is_valid, delta in validity_data:
            if record == keeper:
                decisions.append((record, DECISION_KEEP, "only_valid_duration", CONFIDENCE_HIGH))
            else:
                decisions.append((record, DECISION_DROP, "duration_mismatch", CONFIDENCE_HIGH))
        return integrity_results + decisions
    
    # Multiple valid: technical quality comparison
    scored = []
    for record, delta in valid_files:
        quality = extract_technical_quality(record)
        scored.append((record, quality, delta))
    
    # Sort by: bit_depth desc, sample_rate desc, bitrate desc, delta asc
    scored.sort(key=lambda x: (-x[1][0], -x[1][1], -x[1][2], x[2]))
    
    keeper = scored[0][0]
    best_quality = scored[0][1]
    
    # Check if there's a tie (same quality)
    tied = [r for r, q, d in scored if q == best_quality]
    confidence = CONFIDENCE_HIGH if len(tied) == 1 else CONFIDENCE_MEDIUM
    
    decisions = []
    for record, is_valid, delta in validity_data:
        if record == keeper:
            decisions.append((record, DECISION_KEEP, "best_quality", confidence))
        elif is_valid:
            decisions.append((record, DECISION_DROP, "lower_quality", confidence))
        else:
            decisions.append((record, DECISION_DROP, "duration_mismatch", CONFIDENCE_HIGH))
    
    softened = []
    for record, decision, reason, confidence in integrity_results + decisions:
        if decision == DECISION_DROP:
            softened.append((record, DECISION_REVIEW, f"review_{reason}", confidence))
        else:
            softened.append((record, decision, reason, confidence))
    return softened


def write_report(decisions: List[Tuple[str, str, str, str, float]], out_path: Path):
    """Write CSV report of all decisions."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["path", "decision", "reason", "confidence", "duration_delta"])
        
        for path, decision, reason, confidence, delta in decisions:
            writer.writerow([path, decision, reason, confidence, f"{delta:.3f}"])
    
    print(f"\n✓ Report written: {out_path}")


def apply_decisions(conn: sqlite3.Connection, decisions: List[Tuple[str, str, str, str, float]]):
    """Apply decisions to database."""
    cursor = conn.cursor()
    
    for path, decision, reason, confidence, delta in decisions:
        cursor.execute("""
            UPDATE library_files
            SET decision = ?,
                decision_reason = ?,
                decision_confidence = ?,
                duration_delta = ?
            WHERE path = ?
        """, (decision, reason, confidence, delta, path))
    
    conn.commit()
    print(f"✓ Applied {len(decisions)} decisions to database")


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic KEEP/REVIEW decision engine"
    )
    parser.add_argument(
        "--db",
        required=True,
        type=Path,
        help="SQLite database path"
    )
    parser.add_argument(
        "--group-field",
        default="checksum",
        help="Field to group duplicates by (default: checksum)"
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output CSV report path"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply decisions to database (default: dry-run)"
    )
    parser.add_argument(
        "--duration-tolerance",
        type=float,
        default=DURATION_TOLERANCE,
        help=f"Duration tolerance in seconds (default: {DURATION_TOLERANCE})"
    )
    
    args = parser.parse_args()
    
    if not args.db.exists():
        print(f"ERROR: Database not found: {args.db}")
        sys.exit(1)
    
    print(f"Loading duplicate groups from: {args.db}")
    print(f"Grouping by: {args.group_field}")
    print(f"Duration tolerance: ±{args.duration_tolerance}s")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print()
    
    conn = sqlite3.connect(args.db)
    
    # Ensure columns exist
    if args.apply:
        ensure_decision_columns(conn)
    
    # Load groups
    groups = load_duplicate_groups(conn, args.group_field)
    print(f"Found {len(groups)} duplicate groups")
    
    # Process all groups
    all_decisions = []
    stats = defaultdict(int)
    
    for group_id, files in groups.items():
        decisions = decide_keeper(files, group_id)
        
        for record, decision, reason, confidence in decisions:
            path = record["path"]
            delta = record.get("duration_delta", 0.0)
            all_decisions.append((path, decision, reason, confidence, delta))
            stats[decision] += 1
            stats[f"{decision}_{confidence}"] += 1
    
    # Write report
    write_report(all_decisions, args.out)
    
    # Apply if requested
    if args.apply:
        apply_decisions(conn, all_decisions)
    
    # Print summary
    print("\n" + "="*60)
    print("DECISION SUMMARY")
    print("="*60)
    print(f"KEEP:   {stats[DECISION_KEEP]:6d}  (HIGH: {stats.get(f'{DECISION_KEEP}_{CONFIDENCE_HIGH}', 0)}, "
          f"MED: {stats.get(f'{DECISION_KEEP}_{CONFIDENCE_MEDIUM}', 0)}, "
          f"LOW: {stats.get(f'{DECISION_KEEP}_{CONFIDENCE_LOW}', 0)})")
    print(f"DROP:   {stats[DECISION_DROP]:6d}  (HIGH: {stats.get(f'{DECISION_DROP}_{CONFIDENCE_HIGH}', 0)}, "
          f"MED: {stats.get(f'{DECISION_DROP}_{CONFIDENCE_MEDIUM}', 0)}, "
          f"LOW: {stats.get(f'{DECISION_DROP}_{CONFIDENCE_LOW}', 0)})")
    print(f"REVIEW: {stats[DECISION_REVIEW]:6d}  (HIGH: {stats.get(f'{DECISION_REVIEW}_{CONFIDENCE_HIGH}', 0)}, "
          f"MED: {stats.get(f'{DECISION_REVIEW}_{CONFIDENCE_MEDIUM}', 0)}, "
          f"LOW: {stats.get(f'{DECISION_REVIEW}_{CONFIDENCE_LOW}', 0)})")
    print(f"TOTAL:  {sum(stats[d] for d in [DECISION_KEEP, DECISION_DROP, DECISION_REVIEW]):6d}")
    print("="*60)
    
    if not args.apply:
        print("\nℹ️  Dry-run mode: no changes written to database")
        print("   Add --apply to commit decisions")
    
    conn.close()


if __name__ == "__main__":
    main()
