# inject-history

Build a standalone Go CLI tool at `~/inject-history/` that pre-populates
SpotiFLAC-Next's download history from the tagslut SQLite DB, so SpotiFLAC-Next
skips tracks that are already in the library.

---

## Do not recreate existing files

If `~/inject-history/main.go` or `~/inject-history/go.mod` already exist and
are correct, do not overwrite them. Only create or update what is missing or
broken.

---

## Background: SpotiFLAC-Next storage format

SpotiFLAC-Next uses **bbolt** (go.etcd.io/bbolt) for two files under
`~/.spotiflac-next/`:

### `isrc_cache.db`
- Bucket: `SpotifyTrackISRC`
- Key: Spotify track ID (e.g. `2hH2vHiviZsXYxTXcdBynD`)
- Value: JSON `{"track_id":"...","isrc":"AUDCB1701791","updated_at":1776087637}`

### `history.db`
- Bucket: `DownloadHistory`
- Key: timestamp-based string ID (e.g. `1776087643666461000-69`)
- Value: JSON object with at minimum:
  `{"id":"<key>","spotify_id":"<spotify_id>","title":"...","artists":"...","album":"...","duration_str":"...","cover_url":"...","quality":"320kbps/44.1kHz","format":"MP3","path":"...","source":"tagslut","timestamp":<unix_seconds>}`

SpotiFLAC-Next deduplicates by `spotify_id` — it skips a download if any
`DownloadHistory` entry contains that `spotify_id`.

---

## What the tool must do

1. Open tagslut's SQLite DB (path from `--tagslut` flag, default `$TAGSLUT_DB`).
2. Query all known ISRCs:
   ```sql
   SELECT DISTINCT isrc FROM track_identity WHERE isrc IS NOT NULL AND isrc != ''
   UNION
   SELECT DISTINCT isrc FROM files WHERE isrc IS NOT NULL AND isrc != ''
   ```
3. Open `~/.spotiflac-next/isrc_cache.db` (read-only). Scan the
   `SpotifyTrackISRC` bucket. Build a map of `isrc → spotify_id` for all
   entries whose ISRC matches one from step 2.
4. Open `~/.spotiflac-next/history.db` (read-write). Scan the
   `DownloadHistory` bucket. Build a set of already-known `spotify_id` values.
5. For each `spotify_id` from step 3 not already in step 4, write a synthetic
   `DownloadHistory` entry. Key format: `<unix_nano>-<counter>`. Value: minimal
   JSON as shown above, with `"source":"tagslut"`.
6. Print a summary: `injected N entries, skipped M already present, Q ISRCs
   had no Spotify ID in cache`.
7. Exit 0 on success, non-zero on any hard error.

---

## CLI interface

```
inject-history [flags]

Flags:
  --tagslut string      Path to tagslut SQLite DB (default: $TAGSLUT_DB env var)
  --history-db string   Path to history.db (default: ~/.spotiflac-next/history.db)
  --isrc-cache string   Path to isrc_cache.db (default: ~/.spotiflac-next/isrc_cache.db)
  --dry-run             Parse and print what would be injected; write nothing
  --verbose             Log each injected spotify_id
```

---

## Project layout

```
~/inject-history/
  go.mod          module inject-history, go 1.21+
  main.go         all logic in one file
```

Dependencies (add to go.mod):
- `go.etcd.io/bbolt` — bbolt read/write
- `github.com/mattn/go-sqlite3` — SQLite via CGO

---

## Build and verify

After writing the files, run:

```bash
cd ~/inject-history && go mod tidy && go build -o inject-history .
```

The binary must build cleanly. Run a dry-run smoke test:

```bash
TAGSLUT_DB=/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db \
  ./inject-history --dry-run --verbose
```

Expected: prints ISRCs found, spotify_ids resolved, entries that would be
injected. No writes to history.db.

---

## Shell wrapper (install after binary is built)

After a successful build, install the wrapper so injection runs automatically
on every SpotiFLAC-Next launch:

```bash
APP=/Applications/SpotiFLAC-Next.app/Contents/MacOS

# Only rename if not already renamed
if [ ! -f "$APP/SpotiFLAC-Next-bin" ]; then
  mv "$APP/SpotiFLAC-Next" "$APP/SpotiFLAC-Next-bin"
fi

cat > "$APP/SpotiFLAC-Next" << 'EOF'
#!/bin/bash
/Users/georgeskhawam/inject-history/inject-history \
  --tagslut /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db \
  >> /Users/georgeskhawam/inject-history/inject.log 2>&1
exec "$(dirname "$0")/SpotiFLAC-Next-bin" "$@"
EOF

chmod +x "$APP/SpotiFLAC-Next"
codesign --remove-signature /Applications/SpotiFLAC-Next.app
codesign -s - /Applications/SpotiFLAC-Next.app
```

---

## Commit

```
feat(inject-history): Go CLI to pre-populate SpotiFLAC-Next download history from tagslut DB
```

Commit only files under `~/inject-history/`. Do not touch the tagslut repo.
