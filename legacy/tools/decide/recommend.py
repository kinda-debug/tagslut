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
from dedupe.core.keeper_selection import select_keeper_for_group
from dedupe.utils.cli_helper import common_options, configure_execution
from dedupe.utils.config import get_config
from dedupe.utils.db import resolve_db_path
from dedupe.utils.zones import load_zone_manager

@click.command()
@click.option("--db", required=False, type=click.Path(dir_okay=False), help="Path to SQLite database (default: $DEDUPE_DB)")
@click.option("--output", "-o", type=click.Path(writable=True), help="Output JSON file for the plan")
@click.option("--priority", "-p", multiple=True, help="Zone priority order (e.g. -p accepted -p staging).")
@common_options
def recommend(
    db: str,
    output: str | None,
    priority: tuple[str, ...],
    verbose: bool,
    config: str | None,
) -> None:
    """
    Analyzes duplicates in the DB and produces curator-facing review guidance.
    Outputs a JSON plan.
    """
    configure_execution(verbose, config)
    logger = logging.getLogger("dedupe")

    app_config = get_config(Path(config) if config else None)
    # Load config priorities if not overridden
    priority_order: list[str]
    if priority:
        priority_order = list(priority)
    else:
        priority_order = list(
            app_config.get("decisions.zone_priority", ["accepted", "staging"])
        )

    use_metadata_tiebreaker = bool(app_config.get("decisions.metadata_tiebreaker", False))
    metadata_fields = app_config.get("decisions.metadata_fields", None)
    if not isinstance(metadata_fields, (list, tuple)) or not metadata_fields:
        metadata_fields = ("artist", "album", "title")

    logger.info(f"Using priority order: {priority_order}")

    zone_manager = load_zone_manager(config=getattr(app_config, "_data", None))
    if priority_order:
        zone_manager = zone_manager.override_priorities(priority_order)

    conn = get_connection(db, purpose="read")

    # 1. Find Duplicates
    logger.info("Searching for exact duplicates...")
    groups = list(find_exact_duplicates(conn))
    logger.info(f"Found {len(groups)} duplicate groups.")

    plan_entries: list[dict[str, Any]] = []

    # 2. Make Decisions
    for group in groups:
        selection = select_keeper_for_group(
            group,
            zone_manager=zone_manager,
            use_metadata_tiebreaker=use_metadata_tiebreaker,
            metadata_fields=metadata_fields,
        )
        decisions = selection.decisions

        # Convert Decision objects to JSON-serializable dicts
        decisions_bucket: list[dict[str, Any]] = []
        group_entry = {
            "group_id": group.group_id,
            "similarity": group.similarity,
            "explanations": selection.explanations,
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
                    "sample_rate": d.file.sample_rate,
                    "size": d.file.size,
                }
            })

        plan_entries.append(group_entry)

    # 3. Output
    summary = {
        "groups_count": len(plan_entries),
        "zone_priority": priority_order,
        "plan": plan_entries,
        "zone_config_source": zone_manager.source,
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
