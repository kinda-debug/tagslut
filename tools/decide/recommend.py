import sys
import json
import click
import logging
from pathlib import Path
from typing import List, Dict, Any

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.storage.schema import get_connection
from dedupe.core.matching import find_exact_duplicates
from dedupe.core.decisions import assess_duplicate_group
from dedupe.utils.cli_helper import common_options, configure_execution
from dedupe.utils.config import get_config

@click.command()
@click.option("--db", required=True, type=click.Path(exists=True, dir_okay=False), help="Path to SQLite database")
@click.option("--output", "-o", type=click.Path(writable=True), help="Output JSON file for the plan")
@click.option("--priority", "-p", multiple=True, help="Priority keywords (e.g. -p dotad -p sad). Order matters.")
@common_options
def recommend(db, output, priority, verbose, config):
    """
    Analyzes duplicates in the DB and recommends KEEP/DROP actions.
    Outputs a JSON plan.
    """
    configure_execution(verbose, config)
    logger = logging.getLogger("dedupe")
    
    # Load config priorities if not overridden
    if not priority:
        app_config = get_config()
        priority = app_config.get("decisions.priority_order", ["dotad", "sad", "bad"])

    logger.info(f"Using priority order: {priority}")

    conn = get_connection(Path(db))
    
    # 1. Find Duplicates
    logger.info("Searching for exact duplicates...")
    groups = list(find_exact_duplicates(conn))
    logger.info(f"Found {len(groups)} duplicate groups.")

    plan_entries = []
    
    # 2. Make Decisions
    for group in groups:
        decisions = assess_duplicate_group(group, priority_order=list(priority))
        
        # Convert Decision objects to JSON-serializable dicts
        group_entry = {
            "group_id": group.group_id,
            "similarity": group.similarity,
            "decisions": []
        }
        
        for d in decisions:
            group_entry["decisions"].append({
                "path": str(d.file.path),
                "action": d.action,
                "reason": d.reason,
                "confidence": d.confidence,
                "file_details": {
                    "flac_ok": d.file.flac_ok,
                    "bitrate": d.file.bitrate,
                    "sample_rate": d.file.sample_rate
                }
            })
        
        plan_entries.append(group_entry)

    # 3. Output
    summary = {
        "groups_count": len(plan_entries),
        "priority_order": priority,
        "plan": plan_entries
    }

    if output:
        with open(output, "w") as f:
            json.dump(summary, f, indent=2)
        click.echo(f"Plan saved to {output}")
    else:
        # Print a friendly summary to stdout
        click.echo(json.dumps(summary, indent=2))
        
    conn.close()

if __name__ == "__main__":
    recommend()
