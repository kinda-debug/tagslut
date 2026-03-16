"""P0-ish contract tests for tools/get-intake Roon M3U behavior.

Focus:
  - Inventory-backed M3U inputs must include precheck skip-row db_path values
    (existing library files), not only newly promoted files.
"""

from __future__ import annotations

import csv
import subprocess
from pathlib import Path


def _write_precheck_decisions_csv(path: Path, *, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["decision", "db_path", "title", "artist", "reason"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_roon_m3u_inputs_include_precheck_skip_db_paths(tmp_path: Path) -> None:
    promoted_file = tmp_path / "promoted_flacs.txt"
    promoted_file.write_text("", encoding="utf-8")

    existing_flac = tmp_path / "existing.flac"
    existing_flac.write_text("dummy", encoding="utf-8")

    decisions_csv = tmp_path / "precheck_decisions.csv"
    _write_precheck_decisions_csv(
        decisions_csv,
        rows=[
            {
                "decision": "skip",
                "db_path": str(existing_flac),
                "title": "Already There",
                "artist": "Test Artist",
                "reason": "same or better",
            }
        ],
    )

    out_file = tmp_path / "roon_m3u_inputs.txt"

    # Mirror the embedded python snippet in tools/get-intake.
    snippet = f"""
python - "{promoted_file}" "{decisions_csv}" "{out_file}" <<'PY'
import csv
import sys
from pathlib import Path

promoted_file = Path(sys.argv[1]).expanduser().resolve()
decisions_arg = (sys.argv[2] or "").strip()
decisions_csv = Path(decisions_arg).expanduser().resolve() if decisions_arg else None
out_file = Path(sys.argv[3]).expanduser().resolve()

seen = set()
selected = []

def add_path(text: str) -> None:
    value = (text or "").strip()
    if not value:
        return
    path = Path(value)
    if path.suffix.lower() != ".flac" or not path.exists():
        return
    resolved = str(path.expanduser().resolve())
    if resolved in seen:
        return
    seen.add(resolved)
    selected.append(resolved)

if promoted_file.exists():
    for raw in promoted_file.read_text(encoding="utf-8", errors="replace").splitlines():
        add_path(raw)

if decisions_csv and decisions_csv.exists():
    with decisions_csv.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            decision = (row.get("decision") or row.get("action") or "").strip().lower()
            if decision != "skip":
                continue
            add_path(row.get("db_path") or "")

out_file.parent.mkdir(parents=True, exist_ok=True)
out_file.write_text("\\n".join(selected) + ("\\n" if selected else ""), encoding="utf-8")
PY
"""

    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    lines = [ln.strip() for ln in out_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines == [str(existing_flac.resolve())]


def test_roon_m3u_inputs_merge_promoted_and_precheck_skip(tmp_path: Path) -> None:
    promoted_flac = tmp_path / "promoted.flac"
    promoted_flac.write_text("dummy", encoding="utf-8")

    existing_flac = tmp_path / "existing.flac"
    existing_flac.write_text("dummy", encoding="utf-8")

    promoted_file = tmp_path / "promoted_flacs.txt"
    promoted_file.write_text(f"{promoted_flac}\n", encoding="utf-8")

    decisions_csv = tmp_path / "precheck_decisions.csv"
    _write_precheck_decisions_csv(
        decisions_csv,
        rows=[
            {
                "decision": "skip",
                "db_path": str(existing_flac),
                "title": "Already There",
                "artist": "Test Artist",
                "reason": "same or better",
            }
        ],
    )

    out_file = tmp_path / "roon_m3u_inputs.txt"

    snippet = f"""
python - "{promoted_file}" "{decisions_csv}" "{out_file}" <<'PY'
import csv
import sys
from pathlib import Path

promoted_file = Path(sys.argv[1]).expanduser().resolve()
decisions_arg = (sys.argv[2] or "").strip()
decisions_csv = Path(decisions_arg).expanduser().resolve() if decisions_arg else None
out_file = Path(sys.argv[3]).expanduser().resolve()

seen = set()
selected = []

def add_path(text: str) -> None:
    value = (text or "").strip()
    if not value:
        return
    path = Path(value)
    if path.suffix.lower() != ".flac" or not path.exists():
        return
    resolved = str(path.expanduser().resolve())
    if resolved in seen:
        return
    seen.add(resolved)
    selected.append(resolved)

if promoted_file.exists():
    for raw in promoted_file.read_text(encoding="utf-8", errors="replace").splitlines():
        add_path(raw)

if decisions_csv and decisions_csv.exists():
    with decisions_csv.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            decision = (row.get("decision") or row.get("action") or "").strip().lower()
            if decision != "skip":
                continue
            add_path(row.get("db_path") or "")

out_file.parent.mkdir(parents=True, exist_ok=True)
out_file.write_text("\\n".join(selected) + ("\\n" if selected else ""), encoding="utf-8")
PY
"""

    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    lines = [ln.strip() for ln in out_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines == [str(promoted_flac.resolve()), str(existing_flac.resolve())]

