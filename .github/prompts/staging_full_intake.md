# Staging Full Intake

Do not recreate existing files. Do not modify schema.py without a migration.
Do not write to $MASTER_LIBRARY or $DJ_LIBRARY directly — only via intake pipeline.

## Goal

Empty `/Volumes/MUSIC/staging` by running intake on every queue it contains.

---

## Step 1: Delete M4A duplicates in `tidal/` root

In `/Volumes/MUSIC/staging/tidal/` there are paired files where both a `.flac` and
a `.m4a` exist with the same stem (e.g. `0-01. Dor Danino - Find Your Rose.flac` +
`0-01. Dor Danino - Find Your Rose.m4a`). Delete every `.m4a` at the root of that
folder where a same-stem `.flac` already exists. Do not touch subdirectories.

```python
import os
from pathlib import Path

root = Path("/Volumes/MUSIC/staging/tidal")
for m4a in list(root.glob("*.m4a")):
    flac = m4a.with_suffix(".flac")
    if flac.exists():
        m4a.unlink()
        print(f"deleted: {m4a.name}")
```

Run this as a standalone script. Confirm count deleted before proceeding.

---

## Step 2: Transcode SpotiFLACnext M4As → FLAC (lossless only)

Run the transcode script in-place (no --output-dir, so output lands beside source):

```bash
cd /Users/georgeskhawam/Projects/tagslut
bash scripts/transcode_m4a_to_flac_lossless.sh \
  --scan-path /Volumes/MUSIC/staging/SpotiFLACnext
```

The script skips AAC M4As automatically (lossless ALAC/FLAC-in-M4A only).
Do not delete source M4As after transcode — the script does not delete them and
`process-root` will ignore the M4As and pick up the FLACs.

---

## Step 3: Run intake process-root on all folder queues

For each folder below, run:

```bash
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run tagslut intake process-root --root <FOLDER>
```

Run sequentially. Folders:

1. `/Volumes/MUSIC/staging/bpdl`
2. `/Volumes/MUSIC/staging/tidal`
3. `/Volumes/MUSIC/staging/StreamripDownloads`
4. `/Volumes/MUSIC/staging/SpotiFLACnext`
5. `/Volumes/MUSIC/staging/Apple/Apple`
6. `/Volumes/MUSIC/staging/Apple/Apple Music`
7. `/Volumes/MUSIC/staging/Deep & Minimal`
8. `/Volumes/MUSIC/staging/Groove It Out EP`
9. `/Volumes/MUSIC/staging/Pareidolia (feat. Amanda Zamolo) [Frazer Ray Remix]`
10. `/Volumes/MUSIC/staging/Sounds Of Blue (Gui Boratto Remix)`
11. `/Volumes/MUSIC/staging/This Is bbno$`
12. `/Volumes/MUSIC/staging/mp3_to_sort_intake`

Log stdout+stderr for each run to `/Volumes/MUSIC/staging/logs/intake_<folder_slug>_<timestamp>.log`.

---

## Step 4: Run SpotiFLAC log-based intake

```bash
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"

poetry run tagslut intake spotiflac \
  /Volumes/MUSIC/staging/SpotiFLAC/SpotiFLAC_20260403_015329.txt \
  --base-dir /Volumes/MUSIC/staging/SpotiFLAC

poetry run tagslut intake spotiflac \
  /Volumes/MUSIC/staging/SpotiFLAC/spotiflac_20260403_170006.txt \
  --base-dir /Volumes/MUSIC/staging/SpotiFLAC
```

Skip the `_Failed.txt` files — those are failure logs, not success manifests.

---

## Step 5: Commit

```
chore(staging): full intake run — empty staging queue
```

Do not run the full test suite. Targeted only if a specific failure needs diagnosis.
