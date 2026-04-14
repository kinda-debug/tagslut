# P3-fix — Fix resolve_unresolved.py column names and file-tag fallback

## Do not recreate existing files. Do not run the full test suite.

---

## Problem 1 — Wrong column names in track_identity queries

`tools/resolve_unresolved.py` references columns `album`, `year`, `disc`,
`track` on `track_identity`. These do not exist. The correct columns are:

| Wrong | Correct |
|-------|---------|
| `album` | `canonical_album` |
| `year` | `canonical_year` |
| `disc` | (no disc column — derive from file tags only) |
| `track` | (no track column — derive from file tags only) |
| `title` | `canonical_title` (or `title_norm`) |
| `artist` | `canonical_artist` (or `artist_norm`) |

Fix every query and dict access in `resolve_unresolved.py` that uses the
wrong column names.

## Problem 2 — File-tag fallback not triggering

The file-tag fallback was added but is not triggering because the error
`identity missing required fields` is being raised before the fallback code
runs. The fallback must run whenever ANY required field is None/empty in
`track_identity`, not only when the identity itself is missing.

Required path fields and their sources (in priority order):

| Path field | track_identity column | file tag (mutagen) |
|------------|----------------------|--------------------|
| artist | `canonical_artist` or `artist_norm` | `ARTIST` / `©ART` |
| year | `canonical_year` | `DATE` / `©day` |
| album | `canonical_album` or `album_norm` | `ALBUM` / `©alb` |
| disc | (none) | `DISCNUMBER` / `disk` |
| track | (none) | `TRACKNUMBER` / `trkn` |
| title | `canonical_title` or `title_norm` | `TITLE` / `©nam` |

For each field: use `track_identity` value if non-empty, else use file tag.
If both are empty → `unmatched` with note `missing_required_fields:{field}`.

## Problem 3 — ISRCs not found (6 files)

For the 6 files with `notes=isrc_not_found`: these ISRCs are genuinely absent
from `track_identity`. No fix needed in this script — they need a separate
intake run. Leave them as `unmatched`.

## Problem 4 — inventory script path comparison

The inventory script (`tools/inventory_all.py`) reports `in_asset_file=0` for
files that ARE in the DB. Fix: when loading paths from `asset_file`, normalise
both sides with `os.path.normpath` before comparison.

---

## Changes required

### `tools/resolve_unresolved.py`

1. Fix all `track_identity` column name references (see table above).
2. Fix path derivation to use file tags as fallback for any missing field.
3. For disc/track: parse Vorbis `DISCNUMBER`/`TRACKNUMBER` (format may be
   `"1"` or `"1/2"` — take the part before `/`). For M4A: `disk` and `trkn`
   are tuples `(number, total)` — take `[0]`.

### `tools/inventory_all.py`

4. Normalise paths with `os.path.normpath` when building the asset_file
   path set and when comparing.

---

## Verification

```
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python3 tools/resolve_unresolved.py --dry-run
```

Expected: `Moved: N > 0` where N is at least the 230 files that had
`matched_isrc_but_no_destination` in the previous run.

```
poetry run python3 tools/inventory_all.py
```

Expected: staging_spotiflacnext shows significantly fewer `not in DB` files.

---

## Commit

```
fix(tools): correct track_identity column names and file-tag fallback in resolve_unresolved
fix(tools): normalise paths in inventory_all
```
