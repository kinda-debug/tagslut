# Dual-Source TIDAL ↔ Beatport Metadata Flow

The existing workflow is **one-way**: we export a stable TIDAL playlist seed CSV and then enrich it with Beatport metadata. The goal now is to generalize this into a **bidirectional** enrichment process where *any* seed row (Tidal or Beatport) can be enriched by the other vendor.  We will join tracks primarily by ISRC, falling back to title/artist if needed, and preserve all raw vendor fields in separate blocks. Canonical (“shared”) fields like `title` or `bpm` will not be introduced yet – raw values stay in their original columns, and any derived canonical values will be handled later.

Below is a summary of the current state and the proposed design, supported by the tagslut code and external references where appropriate.

## Current One-Way Workflow

- **Seed CSV (TIDAL-only)**: We start with a TIDAL seed CSV, generated from a playlist. In code, the `TidalProvider.export_playlist_seed_rows` method returns `TidalSeedRow` objects and writes out CSV columns as defined by `TIDAL_SEED_COLUMNS`【17†L219-L227】【35†L209-L218】. These columns are currently:
  ```
  tidal_playlist_id, tidal_track_id, tidal_url, title, artist, isrc
  ```
  (See `TidalSeedRow` in types.py【17†L219-L227】.)

- **Merged CSV (TIDAL + Beatport)**: The enrichment command (`beatport-enrich`) uses `BeatportProvider.enrich_tidal_seed_row`. For each TIDAL seed row it produces a `TidalBeatportMergedRow` dataclass【37†L549-L558】. Its columns are:
  ```
  tidal_playlist_id, tidal_track_id, tidal_url, title, artist, isrc,
  beatport_track_id, beatport_release_id, beatport_url, beatport_bpm,
  beatport_key, beatport_genre, beatport_subgenre, beatport_label,
  beatport_catalog_number, beatport_upc, beatport_release_date,
  match_method, match_confidence, last_synced_at
  ```
  (See `TidalBeatportMergedRow` in types.py【17†L231-L240】 and the columns listed in **docs/tidal_beatport_enrichment.md**【1†L49-L58】【1†L59-L67】.)

- **Match Logic (Current)**:  By default it looks up Beatport matches for each row **in this order**【1†L74-L81】【37†L554-L562】:
  1. **ISRC search** on Beatport (the code uses Beatport V4 API if authenticated).
  2. If no ISRC result, **artist+title search** as a fallback.
  3. If neither yields a match, the row is marked “no_match”. 

  Match metadata are recorded as `match_method` and `match_confidence`.  The current hard-coded values are: 
  - `match_method=isrc`, `match_confidence=1.0` for an ISRC match【1†L79-L82】【37†L554-L562】.
  - `match_method=title_artist_fallback`, `match_confidence=0.6` for a fallback match【1†L79-L82】【37†L554-L562】.
  - `match_method=no_match`, `match_confidence=0.0` if nothing found【1†L79-L82】【37†L554-L562】.

  In practice, the Beatport code computes a confidence rank (EXACT/STRONG/etc.) via `classify_match_confidence`【37†L473-L482】, but currently the merged row always uses 1.0 or 0.6 as above. (In future, we may map the rank to a numeric value, but for now it’s fixed.)

- **CSV Output Behavior**: Unmatched rows are preserved (Beatport fields empty), and no existing TIDAL data is lost.  The code explicitly *copies* the Tidal fields from the seed and then fills Beatport fields【37†L499-L507】【37†L520-L528】.  For example, in `_merged_row_from_match`, the `tidal_*` fields are set from the `seed_row`, and only `beatport_*` fields are written from the match【37†L499-L507】【37†L520-L528】. This ensures **provenance**: raw TIDAL data is never overwritten by Beatport, and vice versa. 

- **Provider Details**:
  - The **TidalProvider** uses Tidal’s v1 API: it supports lookups by track ID and text search, but has no dedicated ISRC endpoint【18†L27-L34】.  (TidalProvider’s code even notes “ISRC search: client-side filtering on text search results.”【18†L27-L34】.)  In practice, we rely on the Tidal search API (`/search?types=TRACKS`) to find tracks by keyword if needed.
  - The **BeatportProvider** supports an authenticated V4 API which can search by ISRC or by artist/title【10†L74-L81】.  It also has web-scraping fallbacks if no token is present. By default `supports_isrc_search = True`【10†L74-L81】, meaning it can do `GET /v4/catalog/tracks?isrc=...`.

## Proposed Dual-Source (Bidirectional) Model

We want to **generalize** this so that *either* vendor can be the seed source:

- An **input row** may originate from Tidal or Beatport.  It will have:
  - A shared identifier `isrc` (if known).
  - Zero or more Tidal fields (e.g. `tidal_track_id`, `tidal_url`, `tidal_title`, `tidal_artist`).
  - Zero or more Beatport fields (`beatport_track_id`, `beatport_release_id`, `beatport_url`, `beatport_bpm`, `beatport_key`, `beatport_genre`, `beatport_subgenre`, `beatport_label`, `beatport_catalog_number`, `beatport_upc`, `beatport_release_date`).
  
  For Tidal-origin rows, the Tidal fields will be filled (as in `TidalSeedRow`).  For Beatport-origin rows, the Beatport fields would be filled (for example, from a Beatport “seed” process if we have one).  Rows may also come from *local tracks* with only an ISRC and one vendor known.

- The **output merged row** will include all of the above fields (tidal_* block and beatport_* block) plus match metadata (`match_method`, `match_confidence`, `last_synced_at`).  Crucially, we **do not** introduce common canonical fields yet; each vendor block stays separate.  Any shared field (like `title`) will be split into `tidal_title` vs `beatport_title` to keep provenance clear.

- **CSV Header Definition**: We will define the exact header order as fixed constants (not relying on dataclass introspection) to ensure stability.  For example, something like:
  ```
  INPUT CSV headers:
    isrc,
    [tidal_track_id, tidal_url, tidal_title, tidal_artist],
    [beatport_track_id, beatport_release_id, beatport_url, beatport_bpm, beatport_key, 
     beatport_genre, beatport_subgenre, beatport_label, beatport_catalog_number, 
     beatport_upc, beatport_release_date]
  
  OUTPUT CSV headers: 
    same vendor-specific fields as input (TIDAL_* and BEATPORT_*),
    plus match_method, match_confidence, last_synced_at.
  ```
  (This expands the old `TidalBeatportMergedRow`【17†L231-L240】 to include vendor prefixes on the Tidal fields and all Beatport fields.)

## Enrichment Orchestration

We will orchestrate enrichment in two directions:

- **TIDAL-origin rows**:  (This is basically the existing path.) Given a row with Tidal data, we do:
  1. Look up Beatport by ISRC (if `isrc` is present and a Beatport API token is available) via `BeatportProvider.search_by_isrc`【37†L554-L562】.
  2. If no ISRC match (or no ISRC), run Beatport `search_by_artist_and_title`【37†L469-L478】 using the Tidal title/artist. Pick the best match using the existing confidence classifier【37†L473-L482】.
  3. Fill the Beatport fields of the output row from the chosen match (using `normalize_beatport_track` as now)【37†L514-L523】.  Leave the Tidal fields untouched.
  4. Set `match_method` to `"isrc"` or `"title_artist_fallback"` or `"no_match"`, and `match_confidence` to 1.0, 0.6, or 0.0 respectively【37†L554-L562】【1†L79-L82】.  Include the current timestamp in `last_synced_at`.

- **Beatport-origin rows**:  We will symmetrically enrich Tidal data from a Beatport seed row.  Tidal has no ISRC endpoint, so we do:
  1. If the row has an `isrc`, we can try a Tidal search by combining artist/title or even track ID if we had it (Tidal API does not search by ISRC directly). Likely we’ll fall back to text search on Tidal using `TidalProvider.search(artist + title)`.
  2. If that fails or if no ISRC, skip (we have nothing better to try because TidalProvider doesn’t support a safe “client-side” ISRC filter on bulk search easily).
  3. If we find a Tidal match, fill the Tidal fields (`tidal_track_id`, `tidal_url`, `tidal_title`, `tidal_artist`) from the Tidal track info (similar to how we do playlist export) and set `match_method`/`match_confidence` analogously.  Otherwise leave Tidal block empty.

  *Note:* The current code has no dedicated “enrich_beatport_seed” method.  We would implement a small helper (probably in `TidalProvider` or a similar spot) that mimics `BeatportProvider.enrich_tidal_seed_row` but in reverse. It would use `TidalProvider.fetch_by_id` or `TidalProvider.search` to find a track and then populate a merged row struct.

- **General Rules**:
  - In either flow, if *only one side resolves*, we output that side’s block and leave the other block blank.  For example, a Tidal row with no Beatport match still outputs the Tidal fields and has empty Beatport columns.
  - Do **not** overwrite raw fields.  The merged row always copies vendor-specific fields into their own columns【37†L499-L507】【37†L520-L528】.
  - Count or log ambiguous cases. For example, if Beatport returns multiple ISRC matches (rare for ISRC, but possible), or if the artist/title fallback yields ties, we should record that. (Current code just picks the first highest-ranked match【37†L473-L482】, but we will **expose** any multi-candidate situations in logs or extra columns for diagnostics.)
  
The net effect is a merged CSV where each row has both the Tidal side and the Beatport side, as available. The enrichment commands might be structured as two new CLI operations or one that auto-detects which side is present. For now, we might keep `tidal-seed` unchanged, optionally add a `beatport-seed` if needed, and provide a single `dual-enrich` command that reads the combined-seed CSV and writes the merged CSV.

## Confidence and Matching Rules

By plan, we standardize confidences to numeric values in the output.  We will follow the existing convention (0.0, 0.6, 1.0) for now, but frame them as stable rules:

- **ISRC match → confidence 1.0**: When we match by ISRC, that is an exact identifier match【1†L74-L81】【37†L554-L562】.
- **Title/artist match → confidence ~~0.6~~ (or mapped rank)**: Currently we use 0.6 for a fallback match【1†L79-L81】【37†L554-L562】.  We may revisit this to scale with the classifier rank (e.g. strong vs weak), but 0.6 is our fixed starting point.
- **No match → confidence 0.0**【1†L79-L81】【37†L554-L562】.
- (Any new match methods would get their own settings, but these cover our two cases.)

We should document these explicitly.  The Beatport code already shows this logic in `_merged_row_from_match` and in the CLI summary【1†L74-L81】【37†L554-L562】.  We will preserve that mapping in the new workflow.

## CSV Schema and Headers

To avoid fragile ordering, we will define the input and output headers as literal tuples (in code) rather than relying on dataclass field ordering.  For example:

```python
INPUT_COLUMNS = (
  "isrc",
  # TIDAL fields (any or none present)
  "tidal_track_id", "tidal_url", "tidal_title", "tidal_artist",
  # BEATPORT fields (any or none present)
  "beatport_track_id", "beatport_release_id", "beatport_url",
  "beatport_bpm", "beatport_key", "beatport_genre",
  "beatport_subgenre", "beatport_label", "beatport_catalog_number",
  "beatport_upc", "beatport_release_date"
)

OUTPUT_COLUMNS = (
  # All vendor-specific fields
  "isrc",
  "tidal_track_id", "tidal_url", "tidal_title", "tidal_artist",
  "beatport_track_id", "beatport_release_id", "beatport_url",
  "beatport_bpm", "beatport_key", "beatport_genre",
  "beatport_subgenre", "beatport_label", "beatport_catalog_number",
  "beatport_upc", "beatport_release_date",
  # Match metadata
  "match_method", "match_confidence", "last_synced_at"
)
```

These would replace the old `TIDAL_SEED_COLUMNS` and `TIDAL_BEATPORT_MERGED_COLUMNS`【17†L231-L240】【21†L1-L3】.  The key is to keep the ordering fixed even if we rearrange dataclass fields later.

## Ambiguity and Telemetry

Where the current pipeline silently collapses multiple candidates, we will explicitly **count and expose** them. For instance:

- If a track’s ISRC query returns more than one Beatport result (unlikely but possible if ISRC is malformed), log how many hits were returned.
- If the title/artist search yields ties in confidence, log that event. 
- Add counters in logs or summary output (e.g. CLI echo) for:
  - Number of rows with multiple ISRC candidates.
  - Number of rows with multiple title/artist candidates.
  - Number of skipped or malformed input rows.

The CLI in `beatport-enrich` already tallies total, ISRC matches, fallbacks, and no-matches【28†L215-L223】.  We will extend that to include “multiple-match” counts and any other diagnostics.  This helps us diagnose ambiguity instead of hiding it.

## Provider Usage (No New Abstractions)

We will **reuse the existing providers and auth**:

- **TidalProvider**: Still fetches playlist items and normalizes tracks. We likely **do not** change its auth flow or add new layers; we’ll just use its search/fetch methods in reverse. If needed, we can add a helper like `fetch_by_title_artist` that uses `search` under the hood.
- **BeatportProvider**: Remains as is for Beatport lookups (including ISRC). No change in auth flow. It already tries the v4 API when a token is present, and falls back to web search【37†L605-L613】【10†L87-L96】. We note that Beatport *does not require* a token for its web-search fallback (the code uses `search` with `_make_request_no_auth` if no token) – but for ISRC-specific calls it needs auth【37†L615-L624】【37†L627-L634】. This matches the plan’s “use existing token flow” note.
- **Enricher**: We may adapt `Enricher.enrich_tidal_seed_csv` to a more general method.  Currently it hard-codes provider `beatport` and TidalSeedRow reading【35†L228-L238】. We could either add a new method (e.g. `enrich_vendor_seed_csv`) or detect columns to pick providers dynamically. In any case, the core orchestration (looping rows, calling provider methods, writing CSV) is already present.

We will not introduce a whole new client abstraction – using the providers directly is fine.  TidalPlaylist export and Beatport lookup remain responsible for their side.

## Test Plan (Key Cases)

To validate the new flow, we should cover:

- **Header stability**: Ensure exact input/output CSV headers as per the contract above. The order should never change even if we refactor code (so use constants, not auto-fields).
- **TIDAL-origin flow**:
  - Tidal row *with ISRC*: should resolve a Beatport match (if it exists) with `match_method=isrc` and `match_confidence=1.0`【1†L74-L81】.
  - Tidal row *without ISRC*: should use title/artist fallback if available, yielding `match_method=title_artist_fallback` and `match_confidence=0.6`【1†L79-L82】.
  - Tidal row with no match: should output the row with empty Beatport fields and `match_method=no_match`.
- **Beatport-origin flow**:
  - Beatport row *with ISRC*: (since Beatport has isrc) we attempt a Tidal lookup. If Tidal finds it, set method=`isrc` and confidence=1.0; else fall back similarly.
  - Beatport row *unmatched*: output row with empty Tidal fields.
- **Ambiguity cases**:
  - Simulate (or mock) a Tidal or Beatport search that returns multiple good candidates. Verify that the code picks one (first-wins) but also increments a counter or log. For example, if two tracks have the same title/artist and equal rank, ensure we count it.
  - Multiple ISRC matches (even if unlikely) should be logged/counted.
- **Malformations**:
  - A row missing required fields (like missing `isrc` and one vendor block entirely): the code should skip or log it (like `_load_tidal_seed_rows` skips incomplete rows【34†L139-L148】). We should count how many input rows are discarded.
- **Provenance safety**:
  - After enrichment, original vendor columns are unchanged. E.g. Tidal columns in output must equal input. The code’s logic in `_merged_row_from_match` already ensures this【37†L499-L507】.
  - No cross-writes: e.g. the Tidal title from input should not be replaced by a Beatport title.
  - Verify via tests that, for example, a Tidal seed’s title appears only in the Tidal block of output, and the Beatport block gets its own data.

If all tests pass, we will have confidence the new model behaves correctly.

## References

- The current one-way workflow and CSV format are documented in *docs/tidal_beatport_enrichment.md*【1†L49-L58】【1†L59-L67】 and implemented by `TidalSeedRow`/`TidalBeatportMergedRow` dataclasses【17†L219-L227】【17†L231-L240】. 
- The Beatport provider code shows the matching logic and merged row construction【37†L549-L558】【37†L514-L523】. 
- Tidal provider capabilities (no ISRC API) are noted in its docstring【18†L27-L34】.
- We will rely on the providers’ existing auth and request code (no change to Beatport’s web-scraping fallback or Tidal’s device auth flow).
- Industry practice is to use ISRC as the cross-vendor join key (ISRC = unique recording ID【42†L134-L142】). We also include title/artist as a weaker secondary key.

By following the above design and testing each scenario, we can build the dual-source metadata pipeline in a robust, auditable way.  


