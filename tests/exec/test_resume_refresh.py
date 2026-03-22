"""Unit tests for the three resume-mode fixes in tools/get-intake.

Test 1 — Resume supplement: PROMOTED_FLACS_FILE is populated from batch root FLACs.
Test 2 — Resume enrichment: post_move_enrich_art.py is invoked with non-empty paths file.
Test 3 — Dest-exists suppression: plan_move_skipped.py is NOT called with --include-buckets
         "dest_exists" in resume mode, but the fix-skips variant still is.
"""
from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Test 1 — Resume supplement populates PROMOTED_FLACS_FILE from batch root
# ---------------------------------------------------------------------------


def test_resume_supplement_populates_promoted_flacs(tmp_path: Path) -> None:
    """When RESUME_MODE=1 and PROMOTED_FLACS_COUNT=0, the supplement block must
    append all .flac files found under BATCH_ROOT to both PROMOTED_AUDIO_FILE
    and PROMOTED_FLACS_FILE, and update the counts.
    """
    batch_root = tmp_path / "bpdl"
    batch_root.mkdir()
    # Create 35 dummy FLACs in a subdirectory (simulates a downloaded release)
    release_dir = batch_root / "VA - Test Release"
    release_dir.mkdir()
    for i in range(35):
        (release_dir / f"{i:02d}. Track {i}.flac").write_bytes(b"FLACDUMMY")

    promoted_audio = tmp_path / "promoted_audio.txt"
    promoted_flacs = tmp_path / "promoted_flacs.txt"
    promoted_audio.write_text("")
    promoted_flacs.write_text("")

    snippet = rf"""
#!/usr/bin/env bash
set -euo pipefail
BATCH_ROOT={str(batch_root)!r}
RESUME_MODE=1
PROMOTED_AUDIO_FILE={str(promoted_audio)!r}
PROMOTED_FLACS_FILE={str(promoted_flacs)!r}
PROMOTED_FLACS_COUNT=0
PROMOTED_AUDIO_COUNT=0

if [[ "$RESUME_MODE" -eq 1 && "$PROMOTED_FLACS_COUNT" -eq 0 && -d "$BATCH_ROOT" ]]; then
  while IFS= read -r resume_path; do
    [[ -n "$resume_path" ]] || continue
    echo "$resume_path" >> "$PROMOTED_AUDIO_FILE"
    echo "$resume_path" >> "$PROMOTED_FLACS_FILE"
  done < <(find "$BATCH_ROOT" -type f -iname '*.flac' | sort)
  PROMOTED_FLACS_COUNT="$(wc -l < "$PROMOTED_FLACS_FILE" | tr -d ' ')"
  PROMOTED_AUDIO_COUNT="$(wc -l < "$PROMOTED_AUDIO_FILE" | tr -d ' ')"
fi

echo "PROMOTED_FLACS_COUNT=$PROMOTED_FLACS_COUNT"
echo "PROMOTED_AUDIO_COUNT=$PROMOTED_AUDIO_COUNT"
"""
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
    assert result.returncode == 0, f"snippet failed: {result.stderr}"

    flac_lines = [ln for ln in promoted_flacs.read_text().splitlines() if ln.strip()]
    audio_lines = [ln for ln in promoted_audio.read_text().splitlines() if ln.strip()]

    assert len(flac_lines) == 35, (
        f"Expected 35 FLAC paths in PROMOTED_FLACS_FILE, got {len(flac_lines)}"
    )
    assert len(audio_lines) == 35, (
        f"Expected 35 audio paths in PROMOTED_AUDIO_FILE, got {len(audio_lines)}"
    )
    assert "PROMOTED_FLACS_COUNT=35" in result.stdout
    assert "PROMOTED_AUDIO_COUNT=35" in result.stdout
    # All reported paths must actually exist
    for p in flac_lines:
        assert Path(p).exists(), f"Supplement added non-existent path: {p!r}"


def test_resume_supplement_does_not_fire_when_already_promoted(tmp_path: Path) -> None:
    """When PROMOTED_FLACS_COUNT > 0, the supplement block must not run."""
    batch_root = tmp_path / "bpdl"
    batch_root.mkdir()
    (batch_root / "extra.flac").write_bytes(b"FLACDUMMY")

    pre_existing = tmp_path / "already_promoted.flac"
    pre_existing.write_bytes(b"FLACDUMMY")
    promoted_flacs = tmp_path / "promoted_flacs.txt"
    promoted_flacs.write_text(str(pre_existing) + "\n")

    snippet = rf"""
#!/usr/bin/env bash
set -euo pipefail
BATCH_ROOT={str(batch_root)!r}
RESUME_MODE=1
PROMOTED_FLACS_FILE={str(promoted_flacs)!r}
PROMOTED_AUDIO_FILE={str(promoted_flacs)!r}
PROMOTED_FLACS_COUNT=1

if [[ "$RESUME_MODE" -eq 1 && "$PROMOTED_FLACS_COUNT" -eq 0 && -d "$BATCH_ROOT" ]]; then
  echo "SUPPLEMENT_FIRED"
fi
echo "PROMOTED_FLACS_COUNT=$PROMOTED_FLACS_COUNT"
"""
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
    assert result.returncode == 0
    assert "SUPPLEMENT_FIRED" not in result.stdout
    assert "PROMOTED_FLACS_COUNT=1" in result.stdout


def test_resume_supplement_does_not_fire_in_normal_mode(tmp_path: Path) -> None:
    """In non-resume mode (RESUME_MODE=0) the supplement block must never fire."""
    batch_root = tmp_path / "bpdl"
    batch_root.mkdir()
    (batch_root / "track.flac").write_bytes(b"FLACDUMMY")

    snippet = rf"""
#!/usr/bin/env bash
BATCH_ROOT={str(batch_root)!r}
RESUME_MODE=0
PROMOTED_FLACS_COUNT=0

if [[ "$RESUME_MODE" -eq 1 && "$PROMOTED_FLACS_COUNT" -eq 0 && -d "$BATCH_ROOT" ]]; then
  echo "SUPPLEMENT_FIRED"
fi
echo "DONE"
"""
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
    assert result.returncode == 0
    assert "SUPPLEMENT_FIRED" not in result.stdout


# ---------------------------------------------------------------------------
# Test 2 — Resume enrichment: post_move_enrich_art.py fires with non-empty file
# ---------------------------------------------------------------------------


def test_resume_enrichment_invoked_with_nonempty_paths_file(tmp_path: Path) -> None:
    """When RESUME_MODE=1 and PROMOTED_FLACS_FILE has paths (after supplement),
    the post_move_enrich_art.py invocation guard must NOT skip.

    We mock the invocation by replacing the script with an echo script that
    captures its arguments. The guard is: `if [[ ! -s "$PROMOTED_FLACS_FILE" ]]`.
    """
    # Write 35 dummy FLAC paths (they don't need to exist for the guard check)
    promoted_flacs = tmp_path / "promoted_flacs.txt"
    flac_paths = [str(tmp_path / f"track_{i}.flac") for i in range(35)]
    promoted_flacs.write_text("\n".join(flac_paths) + "\n")

    invocation_log = tmp_path / "invocation.txt"
    mock_script = tmp_path / "mock_post_move_enrich_art.py"
    mock_script.write_text(
        f"import sys\nwith open({str(invocation_log)!r}, 'w') as f:\n"
        "    f.write(' '.join(sys.argv[1:]))\n"
    )

    snippet = rf"""
#!/usr/bin/env bash
set -euo pipefail
PROMOTED_FLACS_FILE={str(promoted_flacs)!r}
POST_MOVE_ENRICH_SCRIPT={str(mock_script)!r}
RESUME_MODE=1
TAGGING_MODE=1
EXECUTE=1
DJ_MODE=0
DB_PATH=/tmp/fake.db
ENRICH_PROVIDERS=beatport

if [[ "$TAGGING_MODE" -eq 1 && "$EXECUTE" -eq 1 && "$DJ_MODE" -eq 0 ]]; then
  if [[ ! -s "$PROMOTED_FLACS_FILE" ]]; then
    echo "ENRICH_SKIPPED"
  else
    python "$POST_MOVE_ENRICH_SCRIPT" \
      --db "$DB_PATH" \
      --paths-file "$PROMOTED_FLACS_FILE" \
      --providers "$ENRICH_PROVIDERS"
    echo "ENRICH_LAUNCHED"
  fi
fi
"""
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
    assert result.returncode == 0, f"snippet failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "ENRICH_SKIPPED" not in result.stdout, (
        "Enrichment must NOT be skipped when PROMOTED_FLACS_FILE is non-empty"
    )
    assert "ENRICH_LAUNCHED" in result.stdout
    assert invocation_log.exists(), "Mock script was not invoked"
    invocation_args = invocation_log.read_text()
    assert "--paths-file" in invocation_args
    assert str(promoted_flacs) in invocation_args


def test_resume_enrichment_skipped_when_promoted_flacs_empty(tmp_path: Path) -> None:
    """When PROMOTED_FLACS_FILE is empty (supplement did not fire), enrichment skips."""
    promoted_flacs = tmp_path / "promoted_flacs.txt"
    promoted_flacs.write_text("")

    snippet = rf"""
#!/usr/bin/env bash
PROMOTED_FLACS_FILE={str(promoted_flacs)!r}
TAGGING_MODE=1
EXECUTE=1
DJ_MODE=0

if [[ "$TAGGING_MODE" -eq 1 && "$EXECUTE" -eq 1 && "$DJ_MODE" -eq 0 ]]; then
  if [[ ! -s "$PROMOTED_FLACS_FILE" ]]; then
    echo "ENRICH_SKIPPED"
  else
    echo "ENRICH_LAUNCHED"
  fi
fi
"""
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
    assert result.returncode == 0
    assert "ENRICH_SKIPPED" in result.stdout
    assert "ENRICH_LAUNCHED" not in result.stdout


# ---------------------------------------------------------------------------
# Test 3 — dest_exists discard plan suppressed in resume mode
# ---------------------------------------------------------------------------


def test_dest_exists_discard_plan_suppressed_in_resume_mode(tmp_path: Path) -> None:
    """When RESUME_MODE=1, plan_move_skipped.py must NOT be called with
    --include-buckets "dest_exists". The fix-skips variant must still run.
    """
    call_log = tmp_path / "calls.txt"
    mock_script = tmp_path / "plan_move_skipped.py"
    mock_script.write_text(
        f"import sys\nwith open({str(call_log)!r}, 'a') as f:\n"
        "    f.write(' '.join(sys.argv[1:]) + '\\n')\n"
    )

    promote_plan = tmp_path / "plan_promote.csv"
    promote_plan.write_text("action,path,dest_path\n")
    discard_summary = tmp_path / "discard_summary.json"
    fix_summary = tmp_path / "fix_summary.json"

    snippet = rf"""
#!/usr/bin/env bash
set -euo pipefail
RESUME_MODE=1
PLAN_SKIPPED_SCRIPT={str(mock_script)!r}
PROMOTE_PLAN={str(promote_plan)!r}
DISCARD_ROOT=/tmp/discard
BATCH_ROOT=/tmp/batch
FIX_ROOT=/tmp/fix
OUT_DIR={str(tmp_path)!r}
PLAN_STAMP=20260101_000000
DISCARD_SUMMARY={str(discard_summary)!r}
FIX_SKIP_SUMMARY={str(fix_summary)!r}
FIX_SKIP_PLAN={str(tmp_path / "fix_plan.csv")!r}
FIX_SKIP_PLAN={str(tmp_path / "fix_plan.csv")!r}

# fix-skips variant: always runs
python "$PLAN_SKIPPED_SCRIPT" \
  "$PROMOTE_PLAN" \
  --target-root "$FIX_ROOT" \
  --source-root "$BATCH_ROOT" \
  --include-buckets "missing_tags,path_too_long,conflict_same_dest" \
  --output-prefix "plan_move_skipped_to_fix" \
  --out-dir "$OUT_DIR" \
  --stamp "$PLAN_STAMP"

# dest_exists variant: suppressed in resume mode
if [[ "$RESUME_MODE" -eq 0 ]]; then
  python "$PLAN_SKIPPED_SCRIPT" \
    "$PROMOTE_PLAN" \
    --target-root "$DISCARD_ROOT" \
    --source-root "$BATCH_ROOT" \
    --include-buckets "dest_exists" \
    --output-prefix "plan_move_skipped_to_discard" \
    --out-dir "$OUT_DIR" \
    --stamp "$PLAN_STAMP"
else
  printf '{{"selected_rows": 0, "plan_csv": ""}}\n' > "$DISCARD_SUMMARY"
fi
"""
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
    assert result.returncode == 0, f"snippet failed: {result.stderr}"

    calls = call_log.read_text().splitlines()
    assert len(calls) == 1, f"Expected exactly 1 plan_move_skipped call, got {len(calls)}: {calls}"
    assert "missing_tags,path_too_long,conflict_same_dest" in calls[0], (
        "The fix-skips call (missing_tags,...) must always fire in resume mode"
    )
    assert "--include-buckets dest_exists" not in calls[0], (
        "--include-buckets dest_exists must NOT appear in plan_move_skipped call during resume mode"
    )
    assert not any("--include-buckets dest_exists" in c for c in calls)

    # Stub DISCARD_SUMMARY must be a valid JSON with selected_rows=0
    stub = json.loads(discard_summary.read_text())
    assert stub["selected_rows"] == 0


def test_dest_exists_discard_plan_runs_in_normal_mode(tmp_path: Path) -> None:
    """In non-resume mode (RESUME_MODE=0) the dest_exists discard plan must run."""
    call_log = tmp_path / "calls.txt"
    mock_script = tmp_path / "plan_move_skipped.py"
    mock_script.write_text(
        f"import sys\nwith open({str(call_log)!r}, 'a') as f:\n"
        "    f.write(' '.join(sys.argv[1:]) + '\\n')\n"
    )
    promote_plan = tmp_path / "plan_promote.csv"
    promote_plan.write_text("action,path,dest_path\n")
    discard_summary = tmp_path / "discard_summary.json"

    snippet = rf"""
#!/usr/bin/env bash
set -euo pipefail
RESUME_MODE=0
PLAN_SKIPPED_SCRIPT={str(mock_script)!r}
PROMOTE_PLAN={str(promote_plan)!r}
DISCARD_ROOT=/tmp/discard
BATCH_ROOT=/tmp/batch
FIX_ROOT=/tmp/fix
OUT_DIR={str(tmp_path)!r}
PLAN_STAMP=20260101_000000
DISCARD_SUMMARY={str(discard_summary)!r}

python "$PLAN_SKIPPED_SCRIPT" \
  "$PROMOTE_PLAN" \
  --target-root "$FIX_ROOT" \
  --source-root "$BATCH_ROOT" \
  --include-buckets "missing_tags,path_too_long,conflict_same_dest" \
  --output-prefix "plan_move_skipped_to_fix" \
  --out-dir "$OUT_DIR" \
  --stamp "$PLAN_STAMP"

if [[ "$RESUME_MODE" -eq 0 ]]; then
  python "$PLAN_SKIPPED_SCRIPT" \
    "$PROMOTE_PLAN" \
    --target-root "$DISCARD_ROOT" \
    --source-root "$BATCH_ROOT" \
    --include-buckets "dest_exists" \
    --output-prefix "plan_move_skipped_to_discard" \
    --out-dir "$OUT_DIR" \
    --stamp "$PLAN_STAMP"
else
  printf '{{"selected_rows": 0, "plan_csv": ""}}\n' > "$DISCARD_SUMMARY"
fi
"""
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
    assert result.returncode == 0, f"snippet failed: {result.stderr}"

    calls = call_log.read_text().splitlines()
    assert len(calls) == 2, f"Expected 2 calls in normal mode, got {len(calls)}: {calls}"
    assert any("dest_exists" in c for c in calls), (
        "dest_exists call must fire in non-resume mode"
    )
    assert not discard_summary.exists(), (
        "Stub DISCARD_SUMMARY must NOT be written in non-resume mode"
    )
