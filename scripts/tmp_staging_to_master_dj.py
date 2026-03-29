#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
GET_INTAKE = REPO_ROOT / "tools" / "get-intake"
POST_MOVE_ENRICH = REPO_ROOT / "tools" / "review" / "post_move_enrich_art.py"


def env_text(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def resolve_required_path(raw: str | None, label: str) -> Path:
    if not raw:
        raise SystemExit(f"Missing {label}. Pass --{label.replace('_', '-')} or set the matching env var.")
    return Path(raw).expanduser().resolve()


def run(cmd: list[str], *, env: dict[str, str]) -> None:
    print("$ " + shlex.join(cmd))
    subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=True)


def run_capture(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    print("$ " + shlex.join(cmd))
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )


def latest_file(paths: Iterable[Path], pattern: str) -> Path:
    matches = sorted(paths, key=lambda item: item.name)
    if not matches:
        raise SystemExit(f"No {pattern} file was generated.")
    return matches[-1]


def read_nonempty_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_summary_count(output: str, label: str) -> int:
    match = re.search(rf"^\s*{re.escape(label)}:\s+(\d+)", output, re.MULTILINE)
    if not match:
        raise SystemExit(f"Could not parse {label} from duplicate-check output.")
    return int(match.group(1))


def preflight_duplicate_check(*, staging_root: Path, db_path: Path, source: str, env: dict[str, str]) -> None:
    cmd = [
        "poetry",
        "run",
        "python",
        "-m",
        "tagslut",
        "index",
        "check",
        str(staging_root),
        "--db",
        str(db_path),
        "--source",
        source,
        "--strict",
        "--no-prompt",
    ]
    result = run_capture(cmd, env=env)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")

    duplicates = parse_summary_count(result.stdout, "Duplicates")
    errors = parse_summary_count(result.stdout, "Errors")
    if duplicates or errors:
        raise SystemExit(
            f"Duplicate preflight failed: duplicates={duplicates} errors={errors}. "
            "Resolve conflicts in staging before promote/enrich/export."
        )


def parse_args() -> argparse.Namespace:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(
        description=(
            "Temporary wrapper: scan a staging folder, promote FLACs into a dedicated "
            "master-library folder with full tags, then export DJ-tagged MP3 copies."
        )
    )
    parser.add_argument("--staging-root", default=env_text("STAGING_ROOT"))
    parser.add_argument("--db", default=env_text("TAGSLUT_DB"))
    parser.add_argument("--master-library", default=env_text("MASTER_LIBRARY", "LIBRARY_ROOT"))
    parser.add_argument(
        "--master-subdir",
        default="all_tags",
        help="Subfolder created inside MASTER_LIBRARY when --master-dest is not provided.",
    )
    parser.add_argument(
        "--master-dest",
        help="Override the exact dedicated FLAC destination root inside the master library.",
    )
    parser.add_argument("--dj-root", default=env_text("DJ_LIBRARY", "DJ_MP3_ROOT"))
    parser.add_argument(
        "--providers",
        default="beatport,tidal,deezer,traxsource,musicbrainz",
        help="Provider list for full FLAC enrichment/writeback.",
    )
    parser.add_argument("--source", default="ingest")
    parser.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "artifacts" / "tmp_staging_to_master_dj" / stamp),
        help="Artifact directory for promote plans, promoted lists, and DJ receipts.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if shutil.which("poetry") is None:
        raise SystemExit("poetry is required in PATH.")
    if not GET_INTAKE.exists():
        raise SystemExit(f"Missing tool: {GET_INTAKE}")
    if not POST_MOVE_ENRICH.exists():
        raise SystemExit(f"Missing tool: {POST_MOVE_ENRICH}")
    staging_root = resolve_required_path(args.staging_root, "staging_root")
    db_path = resolve_required_path(args.db, "db")
    master_library = resolve_required_path(args.master_library, "master_library")
    dj_root = resolve_required_path(args.dj_root, "dj_root")
    out_dir = Path(args.out_dir).expanduser().resolve()

    if args.master_dest:
        master_dest = Path(args.master_dest).expanduser().resolve()
    else:
        staging_name = staging_root.name or "staging"
        master_dest = (master_library / args.master_subdir / staging_name).resolve()

    if not staging_root.is_dir():
        raise SystemExit(f"Staging root does not exist: {staging_root}")
    if not master_library.is_dir():
        raise SystemExit(f"Master library does not exist: {master_library}")
    if not dj_root.is_dir():
        raise SystemExit(f"DJ root does not exist: {dj_root}")
    if not db_path.is_file():
        raise SystemExit(f"DB does not exist: {db_path}")

    master_dest.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    preflight_duplicate_check(staging_root=staging_root, db_path=db_path, source=args.source, env=env)

    intake_cmd = [
        str(GET_INTAKE),
        "--no-download",
        "--batch-root",
        str(staging_root),
        "--source",
        args.source,
        "--db",
        str(db_path),
        "--library-root",
        str(master_dest),
        "--out-dir",
        str(out_dir),
        "--execute",
        "--no-tagging",
    ]
    if args.verbose:
        intake_cmd.append("--verbose")
    run(intake_cmd, env=env)

    promoted_file = latest_file(out_dir.glob("promoted_flacs_*.txt"), "promoted_flacs_*.txt")
    promoted_paths = read_nonempty_lines(promoted_file)
    if not promoted_paths:
        print(f"No promoted FLACs found in {promoted_file}; nothing to export.")
        return 0

    enrich_cmd = [
        "poetry",
        "run",
        "python",
        str(POST_MOVE_ENRICH),
        "--db",
        str(db_path),
        "--paths-file",
        str(promoted_file),
        "--providers",
        args.providers,
    ]
    run(enrich_cmd, env=env)

    dj_cmd = [
        "poetry",
        "run",
        "python",
        "-c",
        (
            "from pathlib import Path; "
            "from tools.review.process_root import run_dj_phase; "
            f"run_dj_phase(db_path=Path({str(db_path)!r}), "
            f"root_path=Path({str(master_dest)!r}), "
            f"dj_pool_dir=Path({str(dj_root)!r}), "
            "dry_run=False)"
        ),
    ]
    run(dj_cmd, env=env)

    print(f"FLAC destination: {master_dest}")
    print(f"DJ MP3 root: {dj_root}")
    print(f"Artifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
