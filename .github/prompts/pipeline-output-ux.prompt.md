# pipeline-output-ux — Clean progress output for enrich and get

## Do not recreate existing files. Do not modify files not listed in scope.

## Goal

Replace the current binary choice (silent vs DEBUG flood) with a clean UX:

**During run** — one line per track, printed as each completes:
```
[1/108] Fouk - Sunday                        ✓  beatport (exact)  BPM:126 Key:Am
[2/108] Robyn - Dopamine                     ✓  tidal (exact)
[3/108] Air - Sexy Boy                       ~  tidal (exact)  no genre, no label
[4/108] Avicii - Wake Me Up                  ✗  no match
[5/108] Jamie xx - Loud Places               ✓  beatport (strong)  BPM:120 Key:Fm
```

Legend:
- `✓` = enriched, all critical fields present
- `~` = enriched but missing one or more of BPM/key/genre/label (undertagged)
- `✗` = no match found

**At end** — existing RESULTS block, unchanged.

This output is the DEFAULT (no flags needed). Remove the current per-track
progress callback that only fires in `--verbose` mode. The new per-track line
replaces it entirely.

`--verbose` can remain for DEBUG-level log output (rate limiting, ISRC attempts,
etc.) but per-track lines always print regardless.

## Scope of changes

### 1. `tagslut/metadata/pipeline/runner.py`

The `run_enrich_all` function accepts a `progress_callback`. Replace the callback
mechanism with direct stdout printing after each file is processed.

After processing each file (enriched, no_match, or failed), print one line:

```python
import sys

def _format_track_line(index: int, total: int, file_info, result, stats) -> str:
    name = _display_name(file_info)  # "Artist - Title" from tags, fallback to filename stem
    
    if result is None or result.enrichment_confidence == MatchConfidence.NONE:
        status = "✗"
        detail = "no match"
    else:
        missing = []
        if not result.canonical_bpm:    missing.append("BPM")
        if not result.canonical_key:    missing.append("key")
        if not result.canonical_genre:  missing.append("genre")
        if not result.canonical_label:  missing.append("label")
        
        status = "~" if missing else "✓"
        provider = result.enrichment_providers[0] if result.enrichment_providers else "?"
        confidence = result.enrichment_confidence.value if result.enrichment_confidence else ""
        detail = f"{provider} ({confidence})"
        if result.canonical_bpm:
            detail += f"  BPM:{int(result.canonical_bpm)}"
        if result.canonical_key:
            detail += f" Key:{result.canonical_key}"
        if missing:
            detail += f"  no {', '.join(missing)}"
    
    counter = f"[{index}/{total}]"
    return f"{counter:<8} {name:<45} {status}  {detail}"

def _display_name(file_info) -> str:
    artist = file_info.tag_artist or ""
    title = file_info.tag_title or ""
    if artist and title:
        return f"{artist} - {title}"
    return Path(file_info.path).stem[:45]
```

Print this line with `print(line, flush=True)` immediately after each result.
Remove the `progress_callback` call entirely — replace it with the direct print.

### 2. `tagslut/cli/commands/index.py`

- Remove the `make_progress_cb` call and the `progress` lambda passed to `enricher.enrich_all`
- The `--verbose` option can remain but only controls the logging level (DEBUG vs WARNING)
- Do not change the RESULTS block at the end

### 3. `tagslut/cli/_progress.py` (if it exists)

Remove or no-op the progress callback helper if it only served the old verbose mode.
Do not break other commands that may use it.

## What NOT to change

- Do not change the RESULTS block format
- Do not change `EnrichmentStats` or the undertagged list
- Do not change `tools/enrich` or `tools/get`
- Do not change any migration, schema, or test fixtures

## Tests

Update any test that asserts on `progress_callback` being called — replace with
assertions on stdout output if needed, or simply remove the callback assertion.

Run: `poetry run pytest tests/metadata/ -v`

## Commit

```
git add -A
git commit -m "feat(ux): replace verbose/silent binary with per-track progress lines"
```
