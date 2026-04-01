# Fix: Unicode NFD/NFC path normalization in mp3_reconcile

**COMMIT ALL CHANGES BEFORE EXITING. If you do not commit, the work is lost.**

**CRITICAL**: Only touch the files listed below. Do not modify schema, migrations,
or any other module.

---

## Problem

On macOS HFS+, filenames with accented characters (É, à, ü, etc.) are stored in
NFD normalization. Python strings from the DB are NFC. When `mp3 reconcile` scans
DJ_LIBRARY and tries to open files using DB-stored paths, it gets:

```
Cannot read tags ([Errno 2] No such file or directory: '/Volumes/MUSIC/DJ_LIBRARY/Étienne...')
```

The file exists but the path string doesn't match because of NFC vs NFD mismatch.

---

## Fix

### 1. Add a path normalization utility

In `tagslut/utils/fs.py` (create if it doesn't exist, add to if it does):

```python
import unicodedata
from pathlib import Path

def normalize_path(p: str | Path) -> Path:
    """Normalize a filesystem path to NFC to match macOS HFS+ behavior."""
    return Path(unicodedata.normalize('NFC', str(p)))
```

### 2. Apply normalization in mp3_reconcile.py

In `tagslut/exec/mp3_reconcile.py`, find every place where a file path from the
DB or from a scan is opened or passed to a tag-reading function. Wrap each with
`normalize_path()` before use.

Specifically look for:
- Any call to `mutagen` or tag-reading libraries with a path argument
- Any `open(path)` or `Path(path).exists()` checks
- The scan loop where filesystem paths are collected

Import `normalize_path` from `tagslut.utils.fs` and apply it to every path before
filesystem access. Do NOT change the path stored in the DB — only normalize at
the point of filesystem access.

### 3. Apply the same fix in mp3_build.py

Same pattern — any place a FLAC path from the DB is opened for reading or passed
to ffmpeg/mutagen, normalize it first.

---

## Verification

```bash
poetry run pytest tests/exec/ -v --tb=short -q
tagslut mp3 reconcile --mp3-root /Volumes/MUSIC/DJ_LIBRARY --execute -v 2>&1 | grep -c "Cannot read tags"
```

The grep count must be 0 or significantly reduced (only genuinely missing files
should remain, not NFD/NFC mismatches).

---

## Commit message

```
fix(fs): normalize unicode paths to NFC before filesystem access in mp3 build/reconcile
```
