# dj-pool-m3u — Redesign --dj to write M3U playlists instead of DJ_LIBRARY pipeline

## Do not recreate existing files. Do not modify files not listed in scope.

## Context

The current `--dj` flag in `tagslut intake url` drives a 4-stage pipeline that:
- Builds MP3s into a separate `DJ_LIBRARY` folder
- Runs `dj backfill`, `dj validate`, `dj xml emit`
- Maintains a `dj_admission` DB table

This is being replaced. The new model:

- `--dj` = download to `MP3_LIBRARY` (same as `--mp3`) + write two M3U playlist files
- No separate `DJ_LIBRARY` folder
- No DB admission gate
- No XML emit triggered by `--dj`
- DJ tags (BPM, key, genre, label) are embedded on ALL tracks, not just `--dj` tracks

## New --dj behaviour

When `tools/get <url> --dj` is called:

1. Download tracks normally (TIDAL → tiddl, Qobuz → streamrip)
2. Build MP3s into `MP3_LIBRARY` (same as `--mp3`)
3. Embed full DJ tags on all built MP3s via the normal enrich path
4. Write two M3U files (see below)

## M3U output — two files per --dj run

### M3U 1 — batch playlist (per download)
- Location: common parent directory of all MP3s built in this batch, inside `MP3_LIBRARY`
- Filename: `dj_pool.m3u`
- Contains: all MP3 paths from this batch only
- Behaviour: overwrite if exists (it's per-batch, not accumulating)
- Example: `/Volumes/MUSIC/MP3_LIBRARY/Fouk/(2024) Sundays EP/dj_pool.m3u`

### M3U 2 — global DJ pool (accumulating)
- Location: `MP3_LIBRARY` root
- Filename: `dj_pool.m3u`
- Contains: ALL tracks ever added with `--dj`, grows over time
- Behaviour: append new paths only — skip any path already present in the file
- Example: `/Volumes/MUSIC/MP3_LIBRARY/dj_pool.m3u`

### M3U format

Both files use absolute paths. Format:
```
#EXTM3U
#EXTINF:214,Fouk - Sunday
/Volumes/MUSIC/MP3_LIBRARY/Fouk/(2024) Sundays EP/Fouk – (2024) Sundays EP – 01 Sunday.mp3
```

- Duration: integer seconds, read from the MP3 file using `mutagen.mp3.MP3(path).info.length`
- Artist and Title: from ID3 tags TPE1 and TIT2 via `mutagen.id3.ID3`
- Fall back to filename parsing if tags are missing

## Scope of changes

### 1. `tagslut/cli/commands/intake.py`

- Remove `--dj-root` option entirely
- Change `--dj` help text to: "Build MP3s into MP3_LIBRARY and add tracks to DJ pool M3U playlists."
- Remove all validation that requires `--dj-root`
- Remove the chain to `dj backfill` / `dj validate` / `dj xml emit` when `--dj` is active
- After MP3 build completes, call `write_dj_pool_m3u` with the list of built MP3 paths and `mp3_root`

### 2. New file: `tagslut/exec/dj_pool_m3u.py`

Create this module with one public function:

```python
from pathlib import Path

def write_dj_pool_m3u(mp3_paths: list[Path], mp3_root: Path) -> tuple[Path, Path]:
    """
    Write batch and global dj_pool.m3u files.

    Args:
        mp3_paths: absolute paths to MP3 files built in this batch
        mp3_root: root of MP3_LIBRARY (e.g. /Volumes/MUSIC/MP3_LIBRARY)

    Returns:
        (batch_m3u_path, global_m3u_path)
    """
```

Implementation notes:
- Determine batch folder as the common parent of all `mp3_paths`
- Write batch `dj_pool.m3u` to that folder (overwrite)
- Read existing global `dj_pool.m3u` paths into a set, append only new entries
- Use `mutagen.mp3.MP3` for duration, `mutagen.id3.ID3` for TPE1/TIT2 tags
- If mutagen raises, fall back: duration = -1, artist/title parsed from filename

### 3. `tools/get`

- Remove `DJ_ROOT_ARG` variable and all references to it
- Remove `--dj-root` from the `--dj` block in URL routing
- `--dj` now passes only `--mp3-root` to `tagslut intake url`
- Update usage/help text to reflect new behaviour

### 4. `env_exports.sh`

- Remove `DJ_LIBRARY` export if it is only used as the `--dj-root` default
- Keep `MP3_LIBRARY` export unchanged

## What NOT to change

- Do not touch `tagslut/dj/` module — leave backfill, validate, xml emit intact
- Do not drop `dj_admission` table or any migrations
- Do not change `tagslut mp3 build` or `tagslut mp3 reconcile`
- Do not change Qobuz routing in `tools/get`
- Do not change `tagslut index enrich` or enrichment pipeline
- Do not modify any file not listed in scope above

## Tests

Add `tests/exec/test_dj_pool_m3u.py`:
- Test batch M3U is written to the correct folder (common parent of mp3_paths)
- Test global M3U appends new entries and skips duplicates
- Test EXTINF line format: correct duration, artist, title
- Use `tmp_path` fixture with fake MP3 stubs (mock mutagen)
- Targeted only: `poetry run pytest tests/exec/test_dj_pool_m3u.py -v`

## Commit

After all changes verified:
```
git add -A
git commit -m "feat(dj): replace --dj DJ_LIBRARY pipeline with M3U pool writer"
```
