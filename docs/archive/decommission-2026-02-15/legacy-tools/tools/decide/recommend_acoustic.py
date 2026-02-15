#!/usr/bin/env python3
import sys
import json
import click
import logging
import sqlite3
from pathlib import Path
from typing import Any

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parents[2]))

from tagslut.storage.schema import get_connection
from tagslut.core.decisions import assess_duplicate_group
from tagslut.utils.cli_helper import common_options, configure_execution
from tagslut.utils.config import get_config

class MockFile:
    def __init__(self, row: sqlite3.Row):
        self.path = Path(row['path'])
        self.library = row['library']
        self.zone = row['zone']
        # Use streaminfo_md5 as the checksum for decision logic
        self.checksum = row['streaminfo_md5']
        self.flac_ok = row['flac_ok']
        self.integrity_state = row['integrity_state']
        
        # Handle optional columns gracefully
        keys = row.keys()
        self.bitrate = row['bitrate'] if 'bitrate' in keys else 0
        self.sample_rate = row['sample_rate'] if 'sample_rate' in keys else 0
        self.bit_depth = row['bit_depth'] if 'bit_depth' in keys else 0
        self.duration = row['duration'] if 'duration' in keys else 0.0

        self.metadata = {}
        if 'metadata_json' in keys and row['metadata_json']:
            try:
                self.metadata = json.loads(row['metadata_json'])
            except (json.JSONDecodeError, TypeError):
                pass

class MockGroup(list):
    def __init__(self, group_id: str, files: list[MockFile]):
        super().__init__(files)
        self.group_id = group_id
        self.files = files
        self.similarity = "acoustic"
        self.source = "streaminfo_md5"

def find_acoustic_duplicates(conn: sqlite3.Connection):
    cursor = conn.cursor()
    
    # 1. Find hashes with duplicates
    query_hashes = """
        SELECT streaminfo_md5
        FROM files
        WHERE streaminfo_md5 IS NOT NULL 
          AND streaminfo_md5 != '' 
          AND streaminfo_md5 != 'NOT_SCANNED'
        GROUP BY streaminfo_md5
        HAVING COUNT(*) > 1
    """
    hashes = [r[0] for r in cursor.execute(query_hashes).fetchall()]
    
    # 2. Yield groups
    for i, h in enumerate(hashes, 1):
        cursor.execute("SELECT * FROM files WHERE streaminfo_md5 = ?", (h,))
        rows = cursor.fetchall()
        files = [MockFile(row) for row in rows]
        yield MockGroup(f"acoustic-{i:05d}", files)

@click.command()
@click.option("--db", required=True, type=click.Path(exists=True, dir_okay=False), help="Path to SQLite database")
@click.option("--output", "-o", type=click.Path(writable=True), help="Output JSON file for the plan")
@click.option("--priority", "-p", multiple=True, help="Zone priority order (e.g. -p accepted -p staging).")
@common_options
def main(
    db: str,
    output: str | None,
    priority: tuple[str, ...],
    verbose: bool,
    config: str | None,
) -> None:
    """
    Analyzes ACOUSTIC duplicates (streaminfo_md5) and produces curator-facing review guidance.
    """
    configure_execution(verbose, config)
    logger = logging.getLogger("tagslut")

    app_config = get_config(Path(config) if config else None)
    priority_order = list(priority) if priority else list(
        app_config.get("decisions.zone_priority", ["accepted", "staging"])
    )

    use_metadata_tiebreaker = bool(app_config.get("decisions.metadata_tiebreaker", False))
    metadata_fields = app_config.get("decisions.metadata_fields", ("artist", "album", "title"))

    logger.info(f"Using priority order: {priority_order}")

    # Connect with row_factory=sqlite3.Row
    conn = get_connection(Path(db), purpose="read")
    conn.row_factory = sqlite3.Row

    logger.info("Searching for acoustic duplicates (streaminfo_md5)...")
    groups = list(find_acoustic_duplicates(conn))
    logger.info(f"Found {len(groups)} duplicate groups.")

    plan_entries: list[dict[str, Any]] = []
    
    for group in groups:
        decisions = assess_duplicate_group(
            group,
            priority_order=priority_order,
            use_metadata_tiebreaker=use_metadata_tiebreaker,
            metadata_fields=metadata_fields,
        )
        
        decisions_bucket: list[dict[str, Any]] = []
        group_entry = {
            "group_id": group.group_id,
            "similarity": group.similarity,
            "decisions": decisions_bucket,
        }

        for d in decisions:
            decisions_bucket.append({
                "path": str(d.file.path),
                "library": d.file.library,
                "zone": d.file.zone,
                "hash": d.file.checksum,
                "action": d.action,
                "reason": d.reason,
                "confidence": d.confidence,
                "evidence": d.evidence,
                "file_details": {
                    "library": d.file.library,
                    "zone": d.file.zone,
                    "checksum": d.file.checksum,
                    "flac_ok": d.file.flac_ok,
                    "integrity_state": d.file.integrity_state,
                    "bitrate": d.file.bitrate,
                    "sample_rate": d.file.sample_rate
                }
            })
        
        plan_entries.append(group_entry)

    summary = {
        "groups_count": len(plan_entries),
        "zone_priority": priority_order,
        "plan": plan_entries
    }

    if output:
        with open(output, "w") as f:
            json.dump(summary, f, indent=2)
        click.echo(f"Plan saved to {output}")
    else:
        click.echo(json.dumps(summary, indent=2))
        
    conn.close()

if __name__ == "__main__":
    main()