# today-fixes — Three targeted fixes from today's enrichment session

## Do not recreate existing files. Do not modify files not listed in scope.

## Fix 1: Enable Qobuz metadata in default activation config

### Problem
`tagslut/metadata/provider_registry.py` defaults `qobuz.metadata_enabled = False`
(line ~116). No `providers.toml` exists so this default is always used.
Qobuz is authenticated and in the provider list but never contributes metadata.

### Fix
Create `config/providers.toml` with Qobuz metadata enabled:

```toml
[qobuz]
metadata_enabled = true
download_enabled = false
trust = "secondary"

[beatport]
metadata_enabled = true
download_enabled = false
trust = "dj_primary"

[tidal]
metadata_enabled = true
download_enabled = true
trust = "secondary"
```

This file is already the expected path — `load_provider_activation_config()`
looks for it at `{repo_root}/config/providers.toml`.

---

## Fix 2: Extract ISRC from filename for no-tag files

### Problem
12 files in `/Volumes/MUSIC/staging/tidal/` log `searched: ? ?` during enrichment,
meaning `tag_artist` and `tag_title` are both None. These files have no readable
tags but their filenames contain the ISRC in brackets:

```
0064. Kylie Minogue, Sia - Dance Alone (Kito Remix) [USAT22401968].flac
0092. Avicii - Wake Me Up [SE7UQ2500010].flac
```

The ISRC is the part inside `[...]` at the end of the filename (before `.flac`).

### Fix
In `tagslut/metadata/store/db_reader.py`, in `get_eligible_files()`,
after populating `LocalFileInfo` from the DB row, add a fallback:

If `file_info.tag_isrc` is None, attempt to extract ISRC from the filename:

```python
import re as _re
_ISRC_FROM_FILENAME = _re.compile(r'\[([A-Z]{2}[A-Z0-9]{3}\d{7})\]', _re.IGNORECASE)

def _extract_isrc_from_path(path: str) -> Optional[str]:
    m = _ISRC_FROM_FILENAME.search(Path(path).stem)
    return m.group(1).upper() if m else None
```

Apply this in `get_eligible_files` after building each `LocalFileInfo`:
```python
if not info.tag_isrc:
    info.tag_isrc = _extract_isrc_from_path(info.path)
```

Also extract artist and title from the filename as fallback when both are None.
Filename schema: `{track_number}. {Artist} - {Title} [{ISRC}]`
Parse with: `re.match(r'^\d+\.\s+(.+?)\s+-\s+(.+?)(?:\s+\[.*\])?$', stem)`

---

## Fix 3: Fix library_track_key schema mismatch

### Problem
Every enrichment write logs:
`Failed to upsert source snapshot (service=X id=Y): no such column: library_track_key`

The `library_track_sources` table has column `identity_key` but
`tagslut/metadata/store/db_writer.py` references `library_track_key`.

### Fix
In `tagslut/metadata/store/db_writer.py`, replace all occurrences of
`library_track_key` with `identity_key` in any SQL that operates on
the `library_track_sources` table.

Also check `library_tracks` table for the same mismatch and fix there too.

Read the actual schema with `PRAGMA table_info(library_track_sources)`
and `PRAGMA table_info(library_tracks)` against the FRESH DB before
making changes to confirm correct column names.

---

## Scope of changes

- `config/providers.toml` — create (new file)
- `tagslut/metadata/store/db_reader.py` — ISRC + artist/title fallback from filename
- `tagslut/metadata/store/db_writer.py` — fix library_track_key → identity_key

Do not modify any other file.

## Tests

- Add to `tests/metadata/store/test_db_reader.py` (create if not exists):
  - Test ISRC extracted from filename when tag_isrc is None
  - Test artist/title extracted from filename when both are None
  - Test that well-tagged files are not affected

Run: `poetry run pytest tests/metadata/store/test_db_reader.py -v`

## Commit

```
git add -A
git commit -m "fix(enrich): enable Qobuz metadata, fix ISRC filename fallback, fix library_track_key schema"
```
