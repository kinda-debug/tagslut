# Custom Beets plugin stubs needed for real `tagslut` sidecar parity

These are design stubs only. They are included because existing core/external Beets plugins do not cover the gap cleanly.

## 1. `camelotconverter`

### Purpose

Convert a stored musical key into Camelot notation for harmonic-mixing workflows.

### Why existing plugins do not cover it

`keyfinder` can populate `initial_key`, but it does not provide a canonical Camelot layer that matches a `tagslut`-style DJ metadata model.

### Expected config surface

```yaml
camelotconverter:
  auto: yes
  source_field: initial_key
  target_field: camelot
  overwrite: no
```

### Beets hook points / APIs

- import stage listener after metadata is assigned
- optional command, e.g. `beet camelot [QUERY]`

### Input / output

Input:
- `initial_key`

Output:
- `camelot`

### Failure modes

- malformed or non-standard key strings
- ambiguous major/minor parsing
- overwrite collisions when an existing Camelot value is already present

## 2. `isrcimporter`

### Purpose

Bring ISRC into the Beets sidecar as a first-class field.

### Why existing plugins do not cover it

Beets can store arbitrary fields, but there is no stock plugin that gives you the exact identity-centric ISRC flow that `tagslut` depends on.

### Expected config surface

```yaml
isrcimporter:
  auto: yes
  source: filetags
  overwrite: no
```

Possible future extension:

```yaml
isrcimporter:
  fallback_lookup: no
  lookup_provider: null
```

### Beets hook points / APIs

- import stage file tag read path
- optional post-import reconciliation command

### Input / output

Input:
- embedded file tags
- optional external reconciliation source

Output:
- `isrc`

### Failure modes

- missing or malformed file tags
- inconsistent ISRC between file tags and sidecar DB
- accidental overwrite of a known-good ISRC

## 3. `tidalextras`

### Purpose

Populate TIDAL-specific DJ metadata fields that Beets does not know about.

### Why existing plugins do not cover it

No core or external Beets plugin currently gives you parity for TIDAL-specific enrichment such as DJ/stem readiness, tone tags, or audio quality.

### Expected config surface

```yaml
tidalextras:
  auto: no
  token_file: ~/.config/tidal/token.json
  overwrite: no
  fields:
    - tidal_dj_ready
    - tidal_stem_ready
    - tone_tags
    - audio_quality
```

### Beets hook points / APIs

- explicit command path, e.g. `beet tidalextras [QUERY]`
- optional post-import listener if credentials are present

### Input / output

Input:
- TIDAL identifier already associated with an item
- authenticated TIDAL API session

Output:
- `tidal_dj_ready`
- `tidal_stem_ready`
- `tone_tags`
- `audio_quality`

### Failure modes

- expired auth
- rate limits
- changed API schema
- missing TIDAL ID on item

## 4. `tagslutsync`

### Purpose

Sync canonical metadata produced by `tagslut` into the Beets sidecar DB without turning Beets into a competing resolver.

### Why existing plugins do not cover it

This is the central gap. Nothing in Beets understands `tagslut`'s canonical result model, provider precedence, or audit trail.

### Expected config surface

```yaml
tagslutsync:
  source_format: jsonl
  source_path: /path/to/tagslut/output
  match_on:
    - isrc
    - path
  overwrite: yes
  fields:
    - canonical_title
    - canonical_artist
    - canonical_album
    - canonical_bpm
    - canonical_key
    - canonical_genre
    - canonical_sub_genre
    - canonical_label
    - canonical_catalog_number
```
```

### Beets hook points / APIs

- dedicated command, e.g. `beet tagslutsync`
- DB update path only by default
- optional `--write` mode if the operator explicitly wants file tag writes

### Input / output

Input:
- `tagslut` export rows / JSON objects
- matching key such as ISRC or file path

Output:
- Beets flex attributes or mapped item fields

### Failure modes

- no match found in Beets DB
- conflicting identity values
- stale `tagslut` export applied to newer files
- accidental overwrite of intentionally edited sidecar fields

## 5. `genreguard`

### Purpose

Protect `tagslut`'s genre/sub-genre normalization boundary inside the Beets sidecar.

### Why existing plugins do not cover it

Beets plugins such as `lastgenre` or provider plugins can populate genre-like values, but they do not know that `tagslut` owns the canonical normalization policy.

### Expected config surface

```yaml
genreguard:
  canonical_source: tagslut
  protect_fields:
    - genre
    - sub_genre
  overwrite_from_noncanonical: no
  quarantine_field: raw_provider_genre
```

### Beets hook points / APIs

- post-import metadata filter
- post-plugin reconciliation hook

### Input / output

Input:
- incoming provider/plugin genre values
- existing canonical sidecar values

Output:
- protected canonical `genre` / `sub_genre`
- optional quarantined raw genre field

### Failure modes

- canonical field absent when first imported
- repeated plugin runs trying to overwrite protected values
- confusing dual-field behavior if not documented clearly

## Recommendation

If you only build one custom plugin, build `tagslutsync` first.

That is the plugin that turns the sidecar from “a Beets experiment” into “a Beets layer that actually respects your architecture.”
