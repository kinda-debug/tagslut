# mp3-consolidate — Move all scattered MP3s into MP3_LIBRARY

## Do not modify any Python source, tests, migrations, or CLI code.
## Do not touch MASTER_LIBRARY. Do not touch any FLAC files.
## This is a filesystem operation only.

---

## Context

MP3s are scattered across multiple folders on /Volumes/MUSIC.
The target is a single canonical home: /Volumes/MUSIC/MP3_LIBRARY.

After this runs, all MP3s live under MP3_LIBRARY. The DB paths will be
updated to reflect the new locations. Rekordbox paths will break and
must be re-imported manually after consolidation.

---

## New file: `tagslut/exec/mp3_consolidate.py`

Standalone script (`python -m tagslut.exec.mp3_consolidate`).

CLI:
```
  --db PATH       database path (reads $TAGSLUT_DB env var if not provided)
  --execute       actually move files and update DB (default: dry-run)
  --verbose       print one line per file moved
```

### Source → destination mapping

Move MP3s from each source into MP3_LIBRARY with a prefix subfolder:

| Source root | Destination prefix in MP3_LIBRARY |
|---|---|
| `/Volumes/MUSIC/DJ_LIBRARY/` | `_legacy_dj/` |
| `/Volumes/MUSIC/DJ_POOL_MANUAL_MP3/` | `_legacy_manual/` |
| `/Volumes/MUSIC/imindeepshit/` | `_imindeepshit/` |
| `/Volumes/MUSIC/_work/gig_runs/` | `_gig_runs/` |
| `/Volumes/MUSIC/tmp/` | `_tmp_mp3/` |

MP3s already under `/Volumes/MUSIC/MP3_LIBRARY/` are **not moved** —
they are already in the right place.

### Per-file logic

For each MP3 file under a source root:
1. Compute `rel = path.relative_to(source_root)`
2. Compute `dest = MP3_LIBRARY / prefix / rel`
3. In dry-run: print `WOULD MOVE: {src} → {dest}`
4. In execute:
   a. `dest.parent.mkdir(parents=True, exist_ok=True)`
   b. `shutil.move(str(src), str(dest))`
   c. Update the `files` table in the DB:
      `UPDATE files SET path = ? WHERE path = ?`
      with `(str(dest), str(src))`
   d. Log result

### Collision handling

If `dest` already exists:
- Compute SHA256 of both files
- If identical: delete `src`, log as duplicate
- If different: rename dest to `dest.stem + '_conflict' + dest.suffix`,
  then move src to original dest path

### After moving

Print summary:
```
MP3 Consolidation complete:
  Sources processed: N
  Files moved:       N
  Duplicates removed:N
  Conflicts renamed: N
  DB rows updated:   N
  Failed:            N
```

If any source root is now empty after the move (excluding hidden files),
print:
```
  Empty after move (can delete): /path/to/source
```

---

## Tests

Add `tests/exec/test_mp3_consolidate.py`:
- Test: file moves from DJ_LIBRARY to correct MP3_LIBRARY/_legacy_dj/ path
- Test: DB row path is updated after move
- Test: collision with identical file → src deleted, not moved
- Test: collision with different file → dest renamed _conflict
- Test: dry-run does not move any files or update DB
- Use tmp directories and a minimal SQLite DB fixture

Run: `poetry run pytest tests/exec/test_mp3_consolidate.py -v`

---

## Commit

```
git add -A
git commit -m "feat(exec): add mp3_consolidate — move all scattered MP3s into MP3_LIBRARY"
```
