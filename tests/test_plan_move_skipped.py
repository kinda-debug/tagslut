from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_plan_move_skipped_routes_missing_tags_to_fix(tmp_path) -> None:
    source_root = tmp_path / "batch"
    source_root.mkdir()
    missing = source_root / "_UNRESOLVED" / "Artist" / "track.flac"
    missing.parent.mkdir(parents=True)
    missing.write_bytes(b"missing-tags")

    plan_csv = tmp_path / "plan.csv"
    plan_csv.write_text(
        "\n".join(
            [
                "action,path,dest_path,reason",
                f"SKIP,{missing},,missing_tags:missing required tag: albumartist",
                f"MOVE,{missing},/tmp/ignored.flac,final_library",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proc = _run(
        "tools/review/plan_move_skipped.py",
        str(plan_csv),
        "--target-root",
        str(tmp_path / "fix"),
        "--source-root",
        str(source_root),
        "--include-buckets",
        "missing_tags",
        "--output-prefix",
        "plan_move_skipped_to_fix",
        "--out-dir",
        str(tmp_path / "out"),
        "--stamp",
        "20260307_000001",
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    out_plan = tmp_path / "out" / "plan_move_skipped_to_fix_20260307_000001.csv"
    rows = list(csv.DictReader(out_plan.open(newline="", encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["reason"].startswith("missing_tags:")
    assert rows[0]["dest_path"] == str(tmp_path / "fix" / "missing_tags" / "_UNRESOLVED" / "Artist" / "track.flac")


def test_plan_move_skipped_routes_dest_exists_to_discard(tmp_path) -> None:
    source_root = tmp_path / "batch"
    source_root.mkdir()
    duplicate = source_root / "Various Artists" / "Album" / "track.flac"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_bytes(b"duplicate")

    plan_csv = tmp_path / "plan.csv"
    plan_csv.write_text(
        "\n".join(
            [
                "action,path,dest_path,reason",
                f"SKIP,{duplicate},/library/track.flac,dest_exists",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proc = _run(
        "tools/review/plan_move_skipped.py",
        str(plan_csv),
        "--target-root",
        str(tmp_path / "discard"),
        "--source-root",
        str(source_root),
        "--include-buckets",
        "dest_exists",
        "--output-prefix",
        "plan_move_skipped_to_discard",
        "--out-dir",
        str(tmp_path / "out"),
        "--stamp",
        "20260307_000002",
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    out_summary = tmp_path / "out" / "plan_move_skipped_to_discard_summary_20260307_000002.json"
    summary = json.loads(out_summary.read_text(encoding="utf-8"))
    assert summary["selected_rows"] == 1
    assert summary["bucket_counts"] == {"dest_exists": 1}

    out_plan = tmp_path / "out" / "plan_move_skipped_to_discard_20260307_000002.csv"
    rows = list(csv.DictReader(out_plan.open(newline="", encoding="utf-8")))
    assert rows[0]["dest_path"] == str(
        tmp_path / "discard" / "dest_exists" / "Various Artists" / "Album" / "track.flac"
    )
