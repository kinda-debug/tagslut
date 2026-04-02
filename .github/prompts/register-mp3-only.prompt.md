# register-mp3-only — Register DJ_LIBRARY MP3s with no FLAC master into the DB

## Do not recreate existing files. Do not modify files not listed in scope.
## Do not modify any migration, schema, or existing register command behavior.
## Run AFTER fix-mp3-tags-from-filenames has been applied (tags must be readable).

---

## Context

`/Volumes/MUSIC/DJ_LIBRARY` contains ~2,004 MP3 files. These are invisible to
`tagslut index register` (which only scans `*.flac`) and absent from the DB.

After `fix_mp3_tags_from_filenames` runs with `--execute`, these files will have
readable ID3 tags. This script registers them into the `files` table so they are
enrichable (BPM, key, genre, label) and participate in the DJ pool M3U workflow.

The `files` schema has no `format` column. `flac_ok = NULL` means "unchecked",
which is already eligible for enrichment:
  `WHERE flac_ok = 1 OR flac_ok IS NULL`

The enrichment pipeline reads tags from `metadata_json` stored in the DB row,
not from the file — so `metadata_json` must be populated at insert time.

---

## Scope

### New file: `tagslut/exec/register_mp3_only.py`

Standalone script (also `python -m tagslut.exec.register_mp3_only`).

CLI:
```
  --root PATH      directory to scan recursively (default: /Volumes/MUSIC/DJ_LIBRARY)
  --db PATH        database path (reads $TAGSLUT_DB env var if not provided)
  --source TEXT    download_source label (default: "legacy_mp3")
  --zone TEXT      zone to assign (default: "accepted")
  --execute        actually insert (default: dry-run)
  --verbose        print one line per file
```

Implementation:

1. Resolve `--db` from argument or `$TAGSLUT_DB` env var. Fail clearly if neither.
2. Walk `--root` recursively for `*.mp3` files (case-insensitive suffix).
3. Load all existing `path` values from `files` table into a set.
4. For each MP3 not already in the DB:
   a. Read ID3 tags: `mutagen.id3.ID3(path)` with `ID3NoHeaderError` handled.
   b. Extract tags (each via `str(tags.get('FRAME', ['']))[0:1] or ''`):
      - artist    : TPE1
      - title     : TIT2
      - album     : TALB
      - date      : TDRC
      - tracknumber: TRCK
      - isrc      : TSRC
      - bpm       : TBPM
      - key       : TKEY
      - genre     : TCON
      - label     : TPUB
   c. If artist and title still empty, try parsing from filename (same regexes
      as fix_mp3_tags_from_filenames — Schema A tiddl, Schema B flat).
   d. Build `metadata_json` dict from all non-empty tag values.
   e. Measure duration: `mutagen.mp3.MP3(path).info.length` → integer seconds.
      If unreadable, use NULL.
   f. Extract ISRC from filename if tag missing:
      `re.search(r'\[([A-Z]{2}[A-Z0-9]{3}\d{7})\]', Path(path).stem, re.IGNORECASE)`
   g. In `--execute` mode: `INSERT OR IGNORE INTO files` with:
      - path                 = absolute path string
      - zone                 = --zone value
      - download_source      = --source value
      - flac_ok              = NULL
      - duration             = integer seconds or NULL
      - metadata_json        = JSON.dumps(metadata dict)
      - canonical_isrc       = ISRC if found, else NULL
      - ingestion_method     = "legacy_mp3_register"
      - ingestion_source     = absolute path string
      - ingestion_confidence = "uncertain"
      (ingested_at is handled by DB default or omitted — check schema for default)

5. Print summary: scanned, already in DB (skipped), inserted, failed.

Use `INSERT OR IGNORE` — idempotent on path primary key.

### New CLI subcommand in `tagslut/cli/commands/index.py`

Add under the `index` group:

```python
@index.command("register-mp3")
@click.option("--root", default="/Volumes/MUSIC/DJ_LIBRARY", show_default=True,
              help="Directory to scan for MP3 files")
@click.option("--db", "db_path", envvar="TAGSLUT_DB", required=False,
              help="Database path (auto-reads $TAGSLUT_DB)")
@click.option("--source", default="legacy_mp3", show_default=True)
@click.option("--zone", default="accepted", show_default=True)
@click.option("--execute", is_flag=True, help="Actually insert (default: dry-run)")
@click.option("--verbose", "-v", is_flag=True)
def index_register_mp3(root, db_path, source, zone, execute, verbose):
    """Register MP3-only DJ files (no FLAC master) into the inventory."""
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

- Test: MP3 with full ID3 tags → correct `metadata_json` built, row inserted
- Test: MP3 with empty tags but tiddl-schema filename → artist/title parsed
- Test: MP3 with ISRC in filename `[GBAYE0000817]` → `canonical_isrc` populated
- Test: MP3 already in DB → INSERT OR IGNORE, counted as skipped
- Test: dry-run mode → zero rows inserted
- Use a temp SQLite DB with minimal `files` table (create inline in fixture).
- Mock `mutagen.id3.ID3`, `mutagen.mp3.MP3`.

Run: `poetry run pytest tests/exec/test_register_mp3_only.py -v`

---

## Commit

```
git add -A
git commit -m "feat(index): add register-mp3 command for MP3-only DJ files with no FLAC master"
```
