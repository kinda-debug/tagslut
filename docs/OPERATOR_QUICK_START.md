# Operator Quick Start

## Daily Startup

```bash
cd /Users/georgeskhawam/Projects/tagslut
source START_HERE.sh
```

## Token refresh (run before any download or enrichment session)

```bash
ts-auth
```

If Qobuz session is expired (ts-auth will tell you):
```bash
poetry run python -m tagslut auth login qobuz --email YOUR_EMAIL --force
```

If Beatport token is expired, launch beatportdl once to refresh:
```bash
cd ~/Projects/beatportdl && ./beatportdl-darwin-arm64
# Ctrl+C after the "Enter url" prompt appears
cd ~/Projects/tagslut && ts-auth beatport
```

## Download

```bash
ts-get <url>           # Spotify, TIDAL, Qobuz, or Beatport URL
ts-get <url> --dj      # download + add to DJ pool M3U
```

## Enrich metadata

```bash
ts-enrich              # BPM, key, genre, label for all unenriched tracks
```

## DJ pool — Rekordbox

Build the clean lossy Rekordbox import root first. This is the cleanliness step,
not the historical DJ relevance step:

```bash
/Users/georgeskhawam/Projects/tagslut/tools/centralize_lossy_pool \
  --source-root /Volumes/MUSIC \
  --dest-root /Volumes/MUSIC/MP3_LIBRARY_CLEAN \
  --archive-root "/Volumes/MUSIC/_archive_lossy_pool/MP3_LIBRARY_CLEAN_$(date +%Y%m%d_%H%M%S)" \
  --dry-run
```

Execute the reviewed run:

```bash
/Users/georgeskhawam/Projects/tagslut/tools/centralize_lossy_pool \
  --source-root /Volumes/MUSIC \
  --dest-root /Volumes/MUSIC/MP3_LIBRARY_CLEAN \
  --archive-root /Volumes/MUSIC/_archive_lossy_pool/MP3_LIBRARY_CLEAN_<STAMP> \
  --execute
```

If an execute run is interrupted, continue it with the same roots:

```bash
/Users/georgeskhawam/Projects/tagslut/tools/centralize_lossy_pool \
  --source-root /Volumes/MUSIC \
  --dest-root /Volumes/MUSIC/MP3_LIBRARY_CLEAN \
  --archive-root /Volumes/MUSIC/_archive_lossy_pool/MP3_LIBRARY_CLEAN_<STAMP> \
  --execute --resume --verbose
```

Notes:
- Import only `/Volumes/MUSIC/MP3_LIBRARY_CLEAN` into Rekordbox.
- To reconstruct a practical starting DJ seed from prior approved Rekordbox
  material, run `tools/build_dj_seed_from_tree_rbx` after the clean pool exists.
- `tools/build_dj_seed_from_tree_rbx` is read-only outside its
  `--output-dir`. It does not write DB truth, retag files, transcode, move, or
  delete anything.
- It matches historical rows from `tree_rbx.js` onto
  `/Volumes/MUSIC/MP3_LIBRARY_CLEAN` and writes:
  `dj_seed_from_tree_rbx.m3u`, `dj_seed_missing.csv`,
  `dj_seed_ambiguous.csv`, `dj_seed_match_manifest.jsonl`.
- Use the emitted M3U as a reviewable DJ seed starting point, then inspect the
  missing and ambiguous reports before broader Rekordbox curation.
- Review unresolved `conflict_isrc_duration` rows in the run audit manifest before any destructive cleanup.
- Directory names starting with `.` are skipped intentionally. A literal folder such as `...` must be renamed before running the pool builder.

Example historical-seed reconstruction run:

```bash
/Users/georgeskhawam/Projects/tagslut/tools/build_dj_seed_from_tree_rbx \
  --tree-js /Users/georgeskhawam/Projects/tagslut/tree_rbx.js \
  --pool-root /Volumes/MUSIC/MP3_LIBRARY_CLEAN \
  --output-dir /Users/georgeskhawam/Music/dj_seed_from_tree_rbx
```

## Database stats

```bash
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*) FROM files;"
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*), SUM(CASE WHEN canonical_genre IS NOT NULL THEN 1 ELSE 0 END) FROM track_identity;"
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*), SUM(CASE WHEN tidal_bpm IS NOT NULL THEN 1 ELSE 0 END) FROM track_identity;"
```
