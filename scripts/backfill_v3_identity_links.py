#!/usr/bin/env python3
"""Backfill v3 asset/identity/link rows from the legacy files table."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from tagslut.storage.v3.backfill_identity import (
    BackfillConfig,
    backfill_v3_identity_links,
    default_artifacts_dir,
)
from tagslut.utils.db import resolve_db_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill v3 asset/identity/link rows from files rows."
    )
    parser.add_argument("--db", required=True, help="SQLite DB path")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write backfill rows (default: dry-run report only)",
    )
    parser.add_argument("--limit", type=int, help="Process at most N rows")
    parser.add_argument(
        "--resume-from-file-id",
        type=int,
        default=0,
        help="Resume from the first files.rowid greater than this value",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=500,
        help="Commit every N processed rows in execute mode (default: 500)",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=500,
        help="Write a checkpoint artifact every N processed rows (default: 500)",
    )
    parser.add_argument(
        "--busy-timeout-ms",
        type=int,
        default=5000,
        help="SQLite busy_timeout in milliseconds (default: 5000)",
    )
    parser.add_argument(
        "--abort-error-rate-per-1000",
        type=float,
        default=50.0,
        help="Abort if errors per 1000 processed rows exceed this threshold (default: 50)",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=default_artifacts_dir(),
        help="Artifact output directory (default: TAGSLUT_ARTIFACTS or ./artifacts)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print one line per processed row showing file_id, outcome, and path",
    )
    return parser.parse_args(argv)


def _verbose_printer(summary: dict, verbose: bool) -> None:
    """Print per-row outcome lines from the summary samples."""
    if not verbose:
        return
    # Collect all sampled rows and sort by file_id for readable output
    rows: list[tuple[int, str, str]] = []
    outcome_order = ("created", "reused", "merged", "skipped", "conflicted", "fuzzy_near_collision", "fingerprint_matched", "errors")
    for outcome in outcome_order:
        for sample in summary.get("samples", {}).get(outcome, []):
            file_id = sample.get("file_id", "?")
            path = sample.get("path", "?")
            extra = ""
            if outcome == "created":
                extra = f" key={sample.get('identity_key', '?')}"
            elif outcome == "reused":
                extra = f" identity_id={sample.get('identity_id', '?')}"
            elif outcome == "conflicted":
                extra = f" field={sample.get('field', '?')} value={sample.get('value', '?')}"
            elif outcome == "fingerprint_matched":
                extra = f" identity_id={sample.get('identity_id', '?')}"
            elif outcome == "errors":
                extra = f" error={sample.get('error', '?')}"
            rows.append((int(file_id) if str(file_id).isdigit() else 0, outcome, f"  [{outcome.upper():<22}] file_id={file_id} {path}{extra}"))
    rows.sort(key=lambda r: r[0])
    for _, _, line in rows:
        print(line)
    print()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    resolution = resolve_db_path(
        args.db,
        purpose="write" if args.execute else "read",
        allow_create=bool(args.execute),
        allow_repo_db=True,
    )
    db_path = resolution.path

    conn = sqlite3.connect(str(db_path))
    try:
        config = BackfillConfig(
            execute=bool(args.execute),
            resume_from_file_id=max(int(args.resume_from_file_id), 0),
            commit_every=max(int(args.commit_every), 1),
            checkpoint_every=max(int(args.checkpoint_every), 1),
            abort_error_rate_per_1000=float(args.abort_error_rate_per_1000),
            artifacts_dir=args.artifacts_dir.expanduser().resolve(),
            limit=args.limit,
            busy_timeout_ms=max(int(args.busy_timeout_ms), 1),
        )
        summary = backfill_v3_identity_links(
            conn,
            db_path=db_path,
            config=config,
        )
        _verbose_printer(summary, args.verbose)
        print(f"{summary['mode'].upper()}: processed={summary['processed']}")
        print(
            "created={created} reused={reused} merged={merged} skipped={skipped} "
            "conflicted={conflicted} fuzzy_near_collision={fuzzy_near_collision} "
            "fingerprint_matched={fingerprint_matched} errors={errors}".format(**summary)
        )
        print(f"last_file_id={summary['last_file_id']} committed_batches={summary['committed_batches']}")
        print(f"summary_artifact={summary['artifact_paths']['summary']}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
