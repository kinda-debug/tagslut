# register-mp3-only — Register DJ_LIBRARY MP3s with no FLAC master into the DB

## Do not recreate existing files. Do not modify files not listed in scope.
## Do not modify any migration, schema, or existing register command behavior.

---

## Context

`/Volumes/MUSIC/DJ_LIBRARY` contains ~2,004 MP3 files. Many of these are
tiddl downloads that landed as MP3 directly — no FLAC counterpart exists in
`MASTER_LIBRARY`. These files are invisible to `tagslut index register` (which
only scans `*.flac`) and are therefore absent from the DB and unreachable by
the enrichment pipeline.

The goal: register these MP3-only files into the `files` table so they are
enrichable (BPM, key, genre, label via Beatport/TIDAL/Qobuz) and can
participate in the DJ pool M3U workflow.

The `files` schema has no `format` column — it was designed for FLACs but
accepts any path. `flac_ok = NULL` means "unchecked", which is already
eligible for enrichment (confirmed by the existing eligibility query:
`WHERE flac_ok = 1 OR flac_ok IS NULL`).

---

## Scope

### New file: `tagslut/exec/register_mp3_only.py`

A standalone script (also runnable as `python -m tagslut.exec.register_mp3_only`)
that scans a directory for MP3 files, filters out any whose path is already in
the `files` table, and inserts the rest.

CLI:
```
python -m tagslut.exec.register_mp3_only
  --root PATH      directory to scan (default: /Volumes/MUSIC/DJ_LIBRARY)
  --db PATH        database path (reads $TAGSLUT_DB env var if not provided)
  --source TEXT    download_source label to write (default: "legacy_mp3")
  --zone TEXT      zone to assign (default: "accepted")
  --execute        actually insert (default: dry-run)
  --verbose        print one line per file processed
```

Implementation:

1. Walk `--root` recursively, collect all `*.mp3` files (case-insensitive suffix).
2. Load existing paths from `files` table into a set for O(1) lookup.
3. For each MP3 not already in the DB:
   a. Read ID3 tags using `mutagen.mp3.MP3` and `mutagen.id3.ID3`.
   b. Extract: `artist` (TPE1), `title` (TIT2), `album` (TALB), `date` (TDRC),
      `tracknumber` (TRCK), `isrc` (TSRC), `bpm` (TBPM), `key` (TKEY),
      `genre` (TCON), `label` (TPUB).
   c. If artist and title are both missing, try parsing from filename using the
      tiddl schema: `Artist – (Year) Album – NN Title.mp3`
      Regex: `^(.+?) – \((\d{4})\) (.+?) – \d+ (.+?)\.mp3$`
      If that fails, leave artist/title as None.
   d. Build `metadata_json` dict with all extracted tags (skip None values).
   e. Try to read duration in seconds using `mutagen.mp3.MP3(path).info.length`.
   f. Extract ISRC from filename if tag missing:
      `re.search(r'\[([A-Z]{2}[A-Z0-9]{3}\d{7})\]', Path(path).stem, re.IGNORECASE)`
   g. In `--execute` mode: INSERT into `files` with:
      - `path` = absolute path string
      - `zone` = `--zone` value
      - `download_source` = `--source` value
      - `flac_ok` = NULL (unchecked — makes it eligible for enrichment)
      - `duration` = measured duration in seconds (integer), or NULL if unreadable
      - `metadata_json` = JSON string of extracted tags
      - `canonical_isrc` = ISRC if found in tag or filename, else NULL
      - `ingested_at` = current UTC ISO timestamp
      - `ingestion_method` = "legacy_mp3_register"
      - `ingestion_source` = absolute path string
      - `ingestion_confidence` = "uncertain"
      Use `INSERT OR IGNORE` to be idempotent on path.

4. Print summary: total scanned, already in DB (skipped), inserted, failed.

**Do not** attempt FLAC conversion, checksum computation, or any API calls.
**Do not** touch `track_identity` — identity linking happens via enrichment.
**Do not** modify the existing `index register` command.

### New CLI entry point: `tagslut/cli/commands/index.py`

Add a new subcommand `register-mp3` that wraps `register_mp3_only.main()`:

```python
@index.command("register-mp3")
@click.option("--root", default="/Volumes/MUSIC/DJ_LIBRARY", show_default=True)
@click.option("--db", "db_path", envvar="TAGSLUT_DB", required=False)
@click.option("--source", default="legacy_mp3", show_default=True)
@click.option("--zone", default="accepted", show_default=True)
@click.option("--execute", is_flag=True)
@click.option("--verbose", "-v", is_flag=True)
def index_register_mp3(root, db_path, source, zone, execute, verbose):
    """Register MP3-only files (no FLAC master) into the inventory."""
    from tagslut.exec.register_mp3_only import register_mp3_only
    register_mp3_only(
        root=Path(root),
        db_path=Path(db_path) if db_path else None,
        source=source,
        zone=zone,
        execute=execute,
        verbose=verbose,
    )
```

---

## Tests

Add `tests/exec/test_register_mp3_only.py`:

- Test: MP3 with full ID3 tags → correct `metadata_json` and `canonical_isrc`
- Test: MP3 with empty tags but tiddl-schema filename → artist/title parsed from filename
- Test: MP3 with ISRC in filename `[GBAYE0000817]` → `canonical_isrc` populated
- Test: MP3 already in DB → skipped (INSERT OR IGNORE)
- Test: dry-run does not insert any rows
- Use a temp SQLite DB with the `files` table schema (create minimal schema inline).
- Use `mutagen`-writable temp MP3 files or mock mutagen.

Run: `poetry run pytest tests/exec/test_register_mp3_only.py -v`

---

## Commit

```
git add -A
git commit -m "feat(index): add register-mp3 command for MP3-only DJ files with no FLAC master"
```
