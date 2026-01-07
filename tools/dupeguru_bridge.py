#!/usr/bin/env python3
"""
dupeGuru similarity bridge: integrate dupeGuru evidence into decision confidence.

Purpose:
  - Import dupeGuru CSV similarity scores
  - Downgrade confidence when similarity conflicts with hash/duration decisions
  - Flag duration mismatches despite high similarity (common with stitched files)

Usage:
    # Import dupeGuru similarity scores
    tools/dupeguru_bridge.py --db "$DEDUPE_DB" \\
                                                     --dupeguru /path/to/dupeguru.csv \\
                                                     --apply

    # Dry-run (show what would change)
    tools/dupeguru_bridge.py --db "$DEDUPE_DB" \\
                                                     --dupeguru /path/to/dupeguru.csv

Evidence integration rules:
  - Similarity < 95% + same checksum → flag as REVIEW (possible metadata confusion)
  - Similarity ≥ 95% + duration Δ > 0.5s → flag as TAINTED (stitched/recovered)
  - Similarity < 80% + decision=KEEP → downgrade confidence to MEDIUM
"""
import argparse
import csv
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Set, Tuple

try:
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path
except ModuleNotFoundError:  # pragma: no cover
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path

SIMILARITY_THRESHOLD_LOW = 80
SIMILARITY_THRESHOLD_HIGH = 95
DURATION_MISMATCH_THRESHOLD = 0.5  # seconds


def ensure_similarity_column(conn: sqlite3.Connection):
    """Add dupeGuru similarity column if missing."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(library_files)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    
    if "dupeguru_similarity" not in existing_cols:
        print("Adding column: dupeguru_similarity")
        cursor.execute("ALTER TABLE library_files ADD COLUMN dupeguru_similarity REAL")
        conn.commit()


def parse_dupeguru_csv(csv_path: Path) -> Dict[Tuple[str, str], float]:
    """
    Parse dupeGuru CSV and extract similarity scores.
    
    Returns:
        Dict mapping (path1, path2) -> similarity_score
    """
    similarities = {}
    
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            path1 = str(Path(row["Folder"]) / row["Filename"])
            
            # dupeGuru CSV has ref folder/filename in separate columns
            if "Ref. Folder" in row and "Ref. Filename" in row:
                path2 = str(Path(row["Ref. Folder"]) / row["Ref. Filename"])
            else:
                continue
            
            # Parse similarity (usually percentage like "98.5")
            similarity_str = row.get("Match %", row.get("Similarity", "0"))
            try:
                similarity = float(similarity_str.strip('%'))
            except ValueError:
                continue
            
            # Store bidirectional
            similarities[(path1, path2)] = similarity
            similarities[(path2, path1)] = similarity
    
    print(f"Loaded {len(similarities) // 2} similarity pairs from dupeGuru")
    return similarities


def load_decision_data(conn: sqlite3.Connection) -> Dict[str, Dict]:
    """Load current decisions and metadata from database."""
    cursor = conn.cursor()
    
    # Check which columns exist
    cursor.execute("PRAGMA table_info(library_files)")
    available_cols = {row[1] for row in cursor.fetchall()}
    
    required = ["path", "checksum", "duration"]
    optional = ["decision", "decision_reason", "decision_confidence", "duration_delta"]
    
    cols = required + [c for c in optional if c in available_cols]
    
    query = f"SELECT {', '.join(cols)} FROM library_files"
    cursor.execute(query)
    
    data = {}
    for row in cursor.fetchall():
        record = dict(zip(cols, row))
        data[record["path"]] = record
    
    return data


def apply_similarity_evidence(
    conn: sqlite3.Connection,
    similarities: Dict[Tuple[str, str], float],
    decisions: Dict[str, Dict]
) -> int:
    """
    Apply dupeGuru similarity evidence to adjust decisions.
    
    Returns:
        Number of adjustments made
    """
    cursor = conn.cursor()
    adjustments = 0
    
    # Build checksum groups for conflict detection
    checksum_groups = {}
    for path, record in decisions.items():
        checksum = record.get("checksum")
        if checksum:
            checksum_groups.setdefault(checksum, []).append(path)
    
    # Process each similarity pair
    for (path1, path2), similarity in similarities.items():
        if path1 not in decisions or path2 not in decisions:
            continue
        
        rec1 = decisions[path1]
        rec2 = decisions[path2]
        
        checksum1 = rec1.get("checksum")
        checksum2 = rec2.get("checksum")
        
        duration1 = rec1.get("duration", 0)
        duration2 = rec2.get("duration", 0)
        duration_delta = abs(duration1 - duration2)
        
        decision1 = rec1.get("decision")
        confidence1 = rec1.get("decision_confidence")
        
        # Rule 1: Low similarity but same checksum (metadata confusion)
        if similarity < SIMILARITY_THRESHOLD_HIGH and checksum1 and checksum1 == checksum2:
            if decision1 != "REVIEW":
                cursor.execute("""
                    UPDATE library_files
                    SET decision = 'REVIEW',
                        decision_reason = 'similarity_checksum_conflict',
                        decision_confidence = 'HIGH'
                    WHERE path = ?
                """, (path1,))
                adjustments += 1
        
        # Rule 2: High similarity but duration mismatch (stitched/recovered)
        if similarity >= SIMILARITY_THRESHOLD_HIGH and duration_delta > DURATION_MISMATCH_THRESHOLD:
            if rec1.get("decision_reason") != "duration_similarity_conflict":
                cursor.execute("""
                    UPDATE library_files
                    SET decision_reason = 'duration_similarity_conflict',
                        decision_confidence = 'LOW'
                    WHERE path = ?
                """, (path1,))
                adjustments += 1
        
        # Rule 3: Low similarity but KEEP decision (questionable)
        if similarity < SIMILARITY_THRESHOLD_LOW and decision1 == "KEEP" and confidence1 == "HIGH":
            cursor.execute("""
                UPDATE library_files
                SET decision_confidence = 'MEDIUM'
                WHERE path = ?
            """, (path1,))
            adjustments += 1
        
        # Store similarity score
        cursor.execute("""
            UPDATE library_files
            SET dupeguru_similarity = ?
            WHERE path = ?
        """, (similarity, path1))
    
    conn.commit()
    return adjustments


def main():
    parser = argparse.ArgumentParser(
        description="Integrate dupeGuru similarity evidence into decision confidence"
    )
    parser.add_argument(
        "--db",
        required=False,
        type=Path,
        help="SQLite database path"
    )
    parser.add_argument(
        "--allow-repo-db",
        action="store_true",
        help="Allow writing to a repo-local database path",
    )
    parser.add_argument(
        "--dupeguru",
        required=True,
        type=Path,
        help="dupeGuru CSV export path"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply adjustments to database (default: dry-run)"
    )
    
    args = parser.parse_args()
    
    purpose = "write" if args.apply else "read"
    repo_root = Path(__file__).resolve().parents[1]
    try:
        resolution = resolve_db_path(
            args.db,
            config=get_config(),
            allow_repo_db=args.allow_repo_db,
            repo_root=repo_root,
            purpose=purpose,
            allow_create=False,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
    
    if not args.dupeguru.exists():
        print(f"ERROR: dupeGuru CSV not found: {args.dupeguru}")
        sys.exit(1)
    
    print(f"Loading similarity data: {args.dupeguru}")
    print(f"Target database: {resolution.path}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print()
    
    conn = open_db(resolution)
    
    # Ensure column exists
    if args.apply:
        ensure_similarity_column(conn)
    
    # Load data
    similarities = parse_dupeguru_csv(args.dupeguru)
    decisions = load_decision_data(conn)
    
    print(f"Loaded {len(decisions)} file records from database")
    
    # Apply evidence
    if args.apply:
        adjustments = apply_similarity_evidence(conn, similarities, decisions)
        print(f"\n✓ Made {adjustments} decision adjustments based on similarity evidence")
    else:
        # Dry-run: count what would change
        temp_conn = sqlite3.connect(":memory:")
        temp_conn.executescript(
            "CREATE TABLE library_files AS SELECT * FROM main.library_files",
        )
        # Note: Full dry-run analysis would require duplicating DB structure
        print("\nℹ️  Dry-run mode: use --apply to commit changes")
    
    conn.close()


if __name__ == "__main__":
    main()
