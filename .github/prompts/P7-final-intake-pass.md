# P7 — Final Intake and Promotion Pass

## Do not recreate existing files. Do not run the full test suite.

---

## Context

After P2-P6, these files remain unprocessed:

1. `staging/SpotiFLACnext`: 25 FLAC + 5 M4A originals not in DB — newer batches
   (Portal, Cerrone, etc.) that P6 skipped because `track_identity` had no row
   for their ISRCs. They need intake first, then promotion.

2. `staging/SpotiFLAC`: 24 FLACs not in DB — intake_sweep_v2 ran but these
   batches reported `summary_unparsed`. Run intake directly.

3. `mp3_library_spotiflac_next`: 72 MP3s still in `_spotiflac_next` subfolder.
   Re-run P4 after new FLACs are promoted.

---

## Step 1 — Intake remaining staging batches

### SpotiFLACnext batches with no .txt

For each `.m3u8` (non-`_converted`) in `staging/SpotiFLACnext` whose originals
are not yet in DB (check `asset_file` by path), run:

```bash
poetry run tagslut intake spotiflac \
  --base-dir /Volumes/MUSIC/staging/SpotiFLACnext \
  <m3u8_path>
```

The CLI accepts `.m3u8` as the anchor when no `.txt` exists.
If the CLI does not accept `.m3u8` directly, create a minimal synthetic `.txt`
in the same directory with just `Download Report - auto\n` as the header, then
pass that as the anchor with `--base-dir`.

### SpotiFLAC batches

For each `.txt` in `staging/SpotiFLAC` (excluding `_Failed` files):

```bash
poetry run tagslut intake spotiflac \
  --base-dir /Volumes/MUSIC/staging/SpotiFLAC \
  <txt_path>
```

---

## Step 2 — Re-run promote_staging.py

```bash
poetry run python3 tools/promote_staging.py
```

This picks up any newly-ingested staging files and promotes them to
MASTER_LIBRARY.

---

## Step 3 — Re-run mp3_consolidation.py

```bash
poetry run python3 tools/mp3_consolidation.py
```

Now that more FLACs are in MASTER_LIBRARY, more MP3s from `mp3_library_spotiflac_next`
and `mp3_leftovers` should find their master and be moved.

---

## Step 4 — Final audit

```bash
poetry run python3 tools/final_audit.py
```

---

## Write as `tools/final_intake_pass.py`

Automate steps 1-4 in sequence. Print a summary after each step.

```
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python3 tools/final_intake_pass.py
```

---

## What will remain after this (accept as permanent manual backlog)

- `master_unresolved`: FLACs with no ISRC — no automated resolution possible
- `master_unresolved_from_library`: FLACs with no ISRC — same
- `mp3_leftovers`: MP3s whose master FLACs don't exist in the library — accept
- Fuzzy-match pending (67 files from P3) — manual review via the TSV

These are logged in `/Volumes/MUSIC/logs/` and require human decision.
Do not attempt to resolve them programmatically.

---

## Commit

```
feat(tools): add final_intake_pass.py for remaining staging batches
```
