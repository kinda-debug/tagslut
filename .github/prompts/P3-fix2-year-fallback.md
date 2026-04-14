# P3-fix2 — Fix missing year in resolve_unresolved.py

## Do not recreate existing files. Do not run the full test suite.

---

## Problem

230 files fail with `missing_required_fields:year`. The `date` and `year`
Vorbis tags exist on the files but contain empty strings. The script
correctly reads them but treats empty string the same as missing, then
fails instead of falling back.

`track_identity.canonical_year` is also empty for these rows.

## Fix — update `tools/resolve_unresolved.py` in-place

In the path derivation logic, after attempting to read `year` from both
`track_identity` and file tags: if year is still empty or None, use `"0000"`
as the fallback value (not a failure). Add `year_fallback=True` to the notes
column so these moves are distinguishable in the report.

The folder template becomes: `{artist}/(0000) {album}/...`

This matches the existing convention already used in MASTER_LIBRARY (a folder
named `(0000)` already exists there).

Do not treat missing year as `missing_required_fields`. Only fail on missing
`artist`, `title`, `album`, `tracknumber`.

## Verification

```
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python3 tools/resolve_unresolved.py --dry-run
```

Expected: `Moved: ~230` (the files with empty year now fall back to 0000).

## Commit

```
fix(tools): use 0000 year fallback in resolve_unresolved when year tag is empty
```
