# bpdl Staging Area — Cover Art Fix

<!-- Created: 2026-03-21 -->

Agent instructions: AGENT.md, CLAUDE.md, PROJECT_DIRECTIVES.md

---

## Context

The Beatport download staging area at `/Volumes/MUSIC/mdl/bpdl` has a
consistent structural problem: every artist folder contains a `.jpg` file
sitting alongside the album folder rather than inside it.

Example of the problem:
```
Andromeda Orchestra/
  Crazy Lady/          ← album folder
  Crazy Lady.jpg       ← cover sitting outside, wrong
```

Expected result after fix:
```
Andromeda Orchestra/
  Crazy Lady/
    cover.jpg          ← inside the album folder, correct
    track.flac
```

This happened because Beatport downloads were made before the cover
template was configured. The fix is the same one already applied to
the tidal staging area.

---

## Task

Scan `/Volumes/MUSIC/mdl/bpdl` and fix all misplaced cover JPEGs.

### Step 1 — Audit

Find all `.jpg` files at artist level (maxdepth 2) that are NOT
already named `cover.jpg`:

```bash
find /Volumes/MUSIC/mdl/bpdl -maxdepth 2 -name "*.jpg" ! -name "cover.jpg" | sort
```

For each one, check whether a matching album folder exists:
- Strip the `.jpg` extension from the filename
- Check if a directory with that exact name exists in the same parent folder
- Record: MATCH (folder exists) or NO_FOLDER (folder missing)

### Step 2 — Fix matches

For every MATCH: move the `.jpg` into the album folder as `cover.jpg`.

```bash
# Example logic (do not run literally — implement as a loop)
mv "Artist/Album Name.jpg" "Artist/Album Name/cover.jpg"
```

Do NOT overwrite an existing `cover.jpg` — if one already exists inside
the album folder, skip and log as SKIPPED.

### Step 3 — Report NO_FOLDER cases

For every NO_FOLDER (album folder missing — tracks not downloaded):
- Log the full path of the orphaned JPEG
- Do NOT delete them automatically
- List them in the manifest for operator review

### Step 4 — Delete confirmed orphans

After producing the manifest, delete JPEGs where:
- No album folder exists
- The artist folder contains NO other content (empty artist folder)

Do NOT delete JPEGs where the artist folder has other content —
the tracks may be incoming.

### Step 5 — Produce manifest

Write `/Volumes/MUSIC/mdl/bpdl/COVER_FIX_MANIFEST.txt` with:

```
FIXED (moved inside album folder):
  Artist/Album → Artist/Album/cover.jpg

SKIPPED (cover.jpg already existed):
  Artist/Album/cover.jpg

ORPHANED (no album folder, kept for review):
  Artist/Album Name.jpg

DELETED (no album folder, empty artist dir):
  Artist/Album Name.jpg
```

---

## Constraints

- Do NOT touch any `.flac` files
- Do NOT modify files inside album folders that already have FLACs
- Do NOT delete any file without logging it first
- Do NOT run any tagslut commands or DB operations
- This is a filesystem-only task

## Done when

- Zero `.jpg` files remain at artist level (maxdepth 2) except those
  flagged as ORPHANED in the manifest
- Every moved cover is named `cover.jpg` inside its album folder
- Manifest written to `/Volumes/MUSIC/mdl/bpdl/COVER_FIX_MANIFEST.txt`

## Commit

This task does not touch the repo. No commit needed.
Report completion by printing the manifest summary.
