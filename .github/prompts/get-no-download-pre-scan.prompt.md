# get-no-download-pre-scan — Add tag-completion pre-scan before planning in --no-download mode

## Do not recreate existing files. Do not modify files not listed in scope.

## Context

`tools/get-intake --no-download --batch-root <path>` fails or produces incomplete
results when existing files in the batch root are missing tags (artist, title, ISRC).
Planning depends on these tags being present. Without them, tracks get misclassified
or dropped.

The fix: before planning runs in `--no-download` mode, scan existing files in
`BATCH_ROOT` and enrich missing tags from TIDAL/Beatport using the ISRC embedded
in the filename (schema: `{num}. {Artist} - {Title} [{ISRC}].flac`).

## Scope of changes

### 1. `tools/get-intake`

After the `--no-download` argument is parsed and `BATCH_ROOT` is confirmed to exist,
and **before** the precheck/planning block runs, add a pre-scan step:

```bash
# Pre-scan: enrich missing tags from filenames before planning
if [[ "$NO_DOWNLOAD" -eq 1 && -d "$BATCH_ROOT" ]]; then
    log "Pre-scan: checking for missing tags in batch root..."
    run_cmd poetry run python -m tagslut.exec.prescan_tag_completion \
        --batch-root "$BATCH_ROOT" \
        --db "$TAGSLUT_DB" \
        ${EXECUTE:+--execute}
fi
```

Only add this block — do not modify any existing planning or precheck logic.

### 2. New file: `tagslut/exec/prescan_tag_completion.py`

This module scans a batch root for FLAC files missing ISRC or artist/title tags,
extracts the ISRC from the filename where possible, and uses the enrichment
pipeline to fill missing tags before planning runs.

```python
"""
Pre-scan tag completion for --no-download mode.

Scans batch root for files missing ISRC or artist/title tags.
Extracts ISRC from filename schema: {num}. {Artist} - {Title} [{ISRC}].flac
Uses ISRC to fetch and write missing tags before planning runs.
"""
```

CLI interface:
```
python -m tagslut.exec.prescan_tag_completion
  --batch-root PATH   directory to scan
  --db PATH           database path
  --execute           actually write tags (default: dry-run)
```

Implementation:
1. Find all `.flac` files under `--batch-root`
2. For each file, read tags using `mutagen.flac.FLAC`
3. If ISRC tag is missing, try extracting from filename:
   `re.search(r'\[([A-Z]{2}[A-Z0-9]{3}\d{7})\]', Path(f).stem, re.IGNORECASE)`
4. If artist or title tags are missing and ISRC is known:
   - Look up ISRC via TIDAL provider (`TidalProvider.search_by_isrc`)
   - If match found with EXACT confidence: write artist, title, ISRC back to file
5. Print summary: files scanned, tags filled, files still missing tags
6. `--execute` flag required to actually write — dry-run by default

Use `TagManager` or `mutagen` directly for writes. Do not use the enrichment
runner — this is a targeted tag-write operation, not DB enrichment.

## What NOT to change

- Do not modify precheck, planning, or move logic in `tools/get-intake`
- Do not modify the enrichment runner or DB writer
- Do not modify any migration or schema

## Tests

Add `tests/exec/test_prescan_tag_completion.py`:
- Test ISRC extracted from filename when tag missing
- Test tags written when ISRC found and provider returns exact match
- Test dry-run does not write tags
- Mock TidalProvider

Run: `poetry run pytest tests/exec/test_prescan_tag_completion.py -v`

## Commit

```
git add -A
git commit -m "feat(intake): add pre-scan tag completion for --no-download mode"
```
