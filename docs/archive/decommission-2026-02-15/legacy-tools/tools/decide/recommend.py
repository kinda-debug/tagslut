import sys
import json
import click
import logging
from pathlib import Path
from typing import List, Dict, Any

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parents[2]))

from tagslut.storage.schema import get_connection
from tagslut.core.matching import find_exact_duplicates
from tagslut.core.keeper_selection import select_keeper_for_group
from tagslut.utils.cli_helper import common_options, configure_execution
from tagslut.utils.config import get_config
from tagslut.utils.db import resolve_db_path
from tagslut.zones import load_zone_manager
from tagslut.storage.models import DuplicateGroup
from tagslut.storage.queries import _row_to_audiofile

@click.command()
@click.option("--db", required=False, type=click.Path(dir_okay=False), help="Path to SQLite database (default: $TAGSLUT_DB)")
@click.option("--output", "-o", type=click.Path(writable=True), help="Output JSON file for the plan")
@click.option("--priority", "-p", multiple=True, help="Zone priority order (e.g. -p accepted -p staging).")
@click.option(
    "--mode",
    type=click.Choice(["checksum", "streaminfo"], case_sensitive=False),
    default="checksum",
    show_default=True,
    help="Duplicate grouping mode: exact checksum or streaminfo_md5 (audio-identical).",
)
@common_options
def recommend(
    db: str,
    output: str | None,
    priority: tuple[str, ...],
    mode: str,
    verbose: bool,
    config: str | None,
) -> None:
    """
    Analyzes duplicates in the DB and produces curator-facing review guidance.
    Outputs a JSON plan.
    """
    configure_execution(verbose, config)
    logger = logging.getLogger("tagslut")

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
    mode = mode.lower().strip()
    if mode == "streaminfo":
        logger.info("Searching for streaminfo_md5 (audio-identical) duplicates...")
        groups = list(find_streaminfo_duplicates(conn))
    else:
        logger.info("Searching for exact checksum duplicates...")
        groups = list(find_exact_duplicates(conn))
    logger.info(f"Found {len(groups)} duplicate groups.")

    plan_entries: list[dict[str, Any]] = []
    duration_tolerance_s = float(app_config.get("decisions.duration_tolerance_s", 2.0))

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
        durations = [float(f.duration or 0.0) for f in group.files if f.duration]
        duration_spread = (max(durations) - min(durations)) if len(durations) > 1 else 0.0
        has_corrupt = any(
            getattr(f, "integrity_state", None) == "corrupt" or (f.flac_ok is False)
            for f in group.files
        )
        group_flags: list[str] = []
        if duration_spread > duration_tolerance_s:
            group_flags.append(f"duration_spread_gt_{duration_tolerance_s}s")
        if has_corrupt:
            group_flags.append("has_corrupt_files")
        review_only = mode == "streaminfo"
        if review_only:
            group_flags.append("review_only")

        group_entry = {
            "group_id": group.group_id,
            "similarity": group.similarity,
            "duration_spread_s": round(duration_spread, 3),
            "flags": group_flags,
            "explanations": selection.explanations,
            "decisions": decisions_bucket,
        }

        for d in decisions:
            action = d.action
            confidence = d.confidence
            reason = d.reason
            if review_only and action == "DROP":
                action = "REVIEW"
                confidence = "LOW"
                reason = "streaminfo match (manual review)"
            decisions_bucket.append({
                "path": str(d.file.path),
                "library": d.file.library,
                "zone": d.file.zone,
                "hash": d.file.checksum,
                "action": action,
                "reason": reason,
                "confidence": confidence,
                "evidence": d.evidence,
                "file_details": {
                    "library": d.file.library,
                    "zone": d.file.zone,
                    "checksum": d.file.checksum,
                    "flac_ok": d.file.flac_ok,
                    "integrity_state": d.file.integrity_state,
                    "duration": d.file.duration,
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
        "match_mode": mode,
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


def find_streaminfo_duplicates(conn):
    """
    Yield DuplicateGroup objects grouped by streaminfo_md5.
    These flag audio-identical files even when bitwise checksums differ.
    """
    query_hashes = """
        SELECT streaminfo_md5, COUNT(*) as cnt
        FROM files
        WHERE streaminfo_md5 IS NOT NULL
          AND streaminfo_md5 != ''
          AND streaminfo_md5 != 'NOT_SCANNED'
          AND streaminfo_md5 != '00000000000000000000000000000000'
        GROUP BY streaminfo_md5
        HAVING cnt > 1
    """
    cursor = conn.execute(query_hashes)
    hashes = [row["streaminfo_md5"] for row in cursor.fetchall()]
    for stream_hash in hashes:
        files_cursor = conn.execute(
            "SELECT * FROM files WHERE streaminfo_md5 = ?",
            (stream_hash,),
        )
        files = [_row_to_audiofile(row) for row in files_cursor.fetchall()]
        if len(files) > 1:
            yield DuplicateGroup(
                group_id=f"streaminfo:{stream_hash}",
                files=files,
                similarity=1.0,
                source="checksum",
            )

if __name__ == "__main__":
    recommend()
