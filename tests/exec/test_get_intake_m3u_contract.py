"""P0-ish contract tests for tools/get-intake Roon M3U behavior.

Focus:
  - Inventory-backed M3U inputs must include precheck skip-row db_path values
    (existing library files), not only newly promoted files.
  - M3U inputs must preserve promoted audio paths even when they are not FLAC.
  - Lossless source containers converted to FLAC in-batch should have the original
    .m4a/.mp4 file pruned after registration.
"""

from __future__ import annotations

import csv
import sqlite3
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
    promoted_file = tmp_path / "promoted_audio.txt"
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
    if not path.exists() or not path.is_file():
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

    promoted_file = tmp_path / "promoted_audio.txt"
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
    if not path.exists() or not path.is_file():
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


def test_roon_m3u_inputs_preserve_non_flac_audio_paths(tmp_path: Path) -> None:
    promoted_m4a = tmp_path / "promoted.m4a"
    promoted_m4a.write_text("dummy", encoding="utf-8")

    existing_m4a = tmp_path / "existing.m4a"
    existing_m4a.write_text("dummy", encoding="utf-8")

    promoted_file = tmp_path / "promoted_audio.txt"
    promoted_file.write_text(f"{promoted_m4a}\n", encoding="utf-8")

    decisions_csv = tmp_path / "precheck_decisions.csv"
    _write_precheck_decisions_csv(
        decisions_csv,
        rows=[
            {
                "decision": "skip",
                "db_path": str(existing_m4a),
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
    if not path.exists() or not path.is_file():
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
    assert lines == [str(promoted_m4a.resolve()), str(existing_m4a.resolve())]


def test_converted_lossless_originals_are_pruned_after_registration(tmp_path: Path) -> None:
    batch_root = tmp_path / "batch"
    batch_root.mkdir()

    converted_flac = batch_root / "Track.flac"
    converted_flac.write_text("flac", encoding="utf-8")
    original_m4a = batch_root / "Track.m4a"
    original_m4a.write_text("m4a", encoding="utf-8")

    untouched_original = batch_root / "Untouched.m4a"
    untouched_original.write_text("m4a", encoding="utf-8")

    db_path = tmp_path / "scan.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE files(path TEXT, original_path TEXT)")
        conn.execute(
            "INSERT INTO files(path, original_path) VALUES (?, ?)",
            (str(converted_flac.resolve()), str(original_m4a.resolve())),
        )
        conn.execute(
            "INSERT INTO files(path, original_path) VALUES (?, ?)",
            (str(batch_root / 'Other.flac'), str(untouched_original.resolve())),
        )
        conn.commit()
    finally:
        conn.close()

    out_file = tmp_path / "converted_lossless_originals.txt"

    snippet = f"""
python - "{db_path}" "{batch_root}" "{out_file}" <<'PY'
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1]).expanduser().resolve()
batch_root = Path(sys.argv[2]).expanduser().resolve()
out_file = Path(sys.argv[3]).expanduser().resolve()

removed = []
seen = set()

conn = sqlite3.connect(str(db_path))
try:
    rows = conn.execute(
        '''
        SELECT path, original_path
        FROM files
        WHERE path LIKE ?
          AND original_path IS NOT NULL
          AND original_path != ''
        ''',
        (f"{{batch_root}}%",),
    ).fetchall()
finally:
    conn.close()

for path_text, original_text in rows:
    current_path = Path(str(path_text)).expanduser().resolve()
    original_path = Path(str(original_text)).expanduser().resolve()
    if current_path.suffix.lower() != ".flac":
        continue
    if original_path.suffix.lower() not in {{".m4a", ".mp4"}}:
        continue
    if current_path == original_path:
        continue
    if original_path in seen:
        continue
    try:
        current_path.relative_to(batch_root)
        original_path.relative_to(batch_root)
    except ValueError:
        continue
    if not current_path.exists() or not original_path.exists():
        continue
    original_path.unlink(missing_ok=True)
    if original_path.exists():
        continue
    seen.add(original_path)
    removed.append(str(original_path))

out_file.parent.mkdir(parents=True, exist_ok=True)
out_file.write_text("\\n".join(removed) + ("\\n" if removed else ""), encoding="utf-8")
PY
"""

    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    removed = [ln.strip() for ln in out_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert removed == [str(original_m4a.resolve())]
    assert not original_m4a.exists()
    assert untouched_original.exists()
