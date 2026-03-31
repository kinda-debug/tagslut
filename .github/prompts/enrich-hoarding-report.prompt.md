# enrich-hoarding-report — Add per-field hoarding stats and undertagged list to RESULTS block

## Do not recreate existing files. Do not modify files not listed in scope.

## Goal

When `tagslut index enrich --hoarding` runs, the RESULTS block at the end should show:
1. Per-field counts of how many tracks received each hoarding field
2. A list of tracks that were "enriched" but are still missing one or more critical fields

## Current RESULTS output (hoarding mode)

```
==================================================
RESULTS
==================================================
  Total:           66
  Enriched:        61  ✓
  No match:         5
  Failed:           0
```

## Target RESULTS output (hoarding mode)

```
==================================================
RESULTS
==================================================
  Total:           66
  Enriched:        61  ✓
  No match:         5
  Failed:           0

HOARDING FIELDS (of 61 enriched):
  BPM:             58
  Key:             55
  Genre:           61
  Label:           59
  Artwork:         61

UNDERTAGGED (enriched but missing critical fields):
  Fouk - Sunday                     no BPM, no key
  Jamie xx - Loud Places            no genre
  Four Tet - Smile Around the Face  no BPM
```

A track is "undertagged" if it was enriched (matched) but is still missing one or
more of: BPM, key, genre, label. Artwork is NOT included in the undertagged check.
Show all undertagged tracks (no cap). If none, omit the UNDERTAGGED block entirely.

Recovery mode output stays unchanged (no HOARDING FIELDS or UNDERTAGGED blocks).
Both mode ("recovery + hoarding") shows both blocks.

## Scope of changes

### 1. `tagslut/metadata/pipeline/runner.py`

Add fields to `EnrichmentStats`:

```python
@dataclass
class EnrichmentStats:
    total: int = 0
    enriched: int = 0
    skipped: int = 0
    failed: int = 0
    no_match: int = 0
    no_match_files: List[str] = None
    # Hoarding field counters
    bpm_filled: int = 0
    key_filled: int = 0
    genre_filled: int = 0
    label_filled: int = 0
    artwork_filled: int = 0
    # Undertagged: enriched tracks missing one or more critical fields
    # Each entry is a tuple: (display_name: str, missing_fields: list[str])
    undertagged: List[tuple] = None
```

In `__post_init__`, initialise both `no_match_files` and `undertagged` to `[]` if None.

In `run_enrich_all`, after a successful enrichment result in hoarding mode:
- Inspect the result to count which fields were filled (non-None, non-empty)
- Read `tagslut/metadata/models/types.py` and `tagslut/metadata/store/db_writer.py`
  to find the correct attribute names — do not guess
- BPM: canonical_bpm or beatport_bpm
- Key: canonical_key or beatport_key
- Genre: canonical_genre or beatport_genre
- Label: canonical_label or beatport_label
- Artwork: artwork_url or image_url or similar
- If enriched but missing any of BPM/key/genre/label, add to `undertagged`:
  display_name = "Artist - Title" from the result or file_info
  missing_fields = list of field names that are missing, e.g. ["BPM", "key"]

### 2. `tagslut/cli/commands/index.py`

In the RESULTS block at the end of the `enrich` command, after the existing counts,
add for hoarding/both mode:

```python
if mode in ("hoarding", "both") and stats.enriched > 0:
    click.echo("")
    click.echo(f"HOARDING FIELDS (of {stats.enriched} enriched):")
    click.echo(f"  BPM:        {stats.bpm_filled:>6}")
    click.echo(f"  Key:        {stats.key_filled:>6}")
    click.echo(f"  Genre:      {stats.genre_filled:>6}")
    click.echo(f"  Label:      {stats.label_filled:>6}")
    click.echo(f"  Artwork:    {stats.artwork_filled:>6}")

if mode in ("hoarding", "both") and stats.undertagged:
    click.echo("")
    click.echo("UNDERTAGGED (enriched but missing critical fields):")
    for name, missing in stats.undertagged:
        fields_str = ", ".join(f"no {f}" for f in missing)
        click.echo(f"  {name:<45}  {fields_str}")
```

Apply to BOTH results blocks in the enrich command (there are two — one for the
inline/simple path, one for the full enricher path). Both must show the blocks
when in hoarding/both mode.

## What NOT to change

- Do not change recovery mode output
- Do not change `EnrichmentResult` model fields — only read from them
- Do not change any other command or file
- Do not change the enrichment logic itself

## Tests

Add `tests/metadata/test_enrichment_stats.py` (create if not exists):
- Test `bpm_filled` increments when BPM is present in result
- Test fields with None value do not increment counters
- Test undertagged entry added when enriched track missing BPM
- Test undertagged entry NOT added when all fields present
- Test no UNDERTAGGED block rendered when list is empty

Run: `poetry run pytest tests/metadata/test_enrichment_stats.py -v`

## Commit

```
git add -A
git commit -m "feat(enrich): add per-field hoarding stats and undertagged list to RESULTS block"
```
