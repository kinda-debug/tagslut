# Custom Beets plugin/module stubs needed for `tagslut` sidecar parity

These are *design stubs only* (no implementation in this repo yet). They exist because core Beets + verified external plugins still do not cover these gaps while preserving the “tagslut is authoritative” boundary.

Primary Beets plugin API references:
- https://docs.beets.io/en/stable/dev/plugins.html
- https://github.com/beetbox/beets/tree/master/beets

## 1) `tagslutsync` (required)

### Purpose

Import/sync canonical metadata produced by `tagslut` into the Beets sidecar **database** (DB-first, no file writes by default).

This is the “bridge” that makes Beets a useful UI/index for `tagslut` outputs without re-implementing provider resolution in Beets.

### Why core/external plugins do not cover it

- Beets metadata-source plugins operate at *import/matching time* and do not understand `tagslut`’s canonical result model or precedence rules.
- There is no existing maintained plugin designed to ingest `tagslut`’s enrichment outputs as the *source of truth* for downstream fields.

### Expected config surface

```yaml
tagslutsync:
  enabled: yes
  source:
    format: jsonl
    path: /config/tagslut/enrichment.jsonl
  match:
    # match precedence (first successful wins)
    - isrc
    - path
  write_files: no
  overwrite: yes
  mapping:
    # tagslut canonical -> beets fields/flex attrs
    canonical_title: ts_canonical_title
    canonical_artist: ts_canonical_artist
    canonical_album: ts_canonical_album
    canonical_isrc: ts_canonical_isrc
    canonical_year: ts_canonical_year
    canonical_release_date: ts_canonical_release_date
    canonical_duration: ts_canonical_duration
    canonical_bpm: ts_canonical_bpm
    canonical_key: ts_canonical_key
    canonical_genre: ts_canonical_genre
    canonical_sub_genre: ts_canonical_sub_genre
    canonical_label: ts_canonical_label
    canonical_catalog_number: ts_canonical_catalog_number
    canonical_mix_name: ts_canonical_mix_name
    canonical_explicit: ts_canonical_explicit
    canonical_album_art_url: ts_canonical_album_art_url
  extras:
    # provider IDs and provider-only attributes (flex attrs)
    beatport_id: ts_source_beatport_id
    tidal_id: ts_source_tidal_id
    tidal_dj_ready: ts_tidal_dj_ready
    tidal_stem_ready: ts_tidal_stem_ready
    tone_tags: ts_tone_tags
    audio_quality: ts_audio_quality
    preview_url: ts_preview_url
    waveform_url: ts_waveform_url
```

Notes:
- Storing canonical values in `ts_*` fields avoids Beets becoming a second “truth”; you can optionally add a `mirror_into_core_fields: false` knob later.
- `tone_tags` likely needs serialization (e.g., JSON string) because Beets flexible attributes are scalar in common workflows.

### Beets hook points / APIs

- Implement as a Beets plugin (`beets.plugins.BeetsPlugin`) that registers:
  - a command: `beet tagslutsync [QUERY...]` (explicit operator action)
  - optional: an import stage hook (off by default) for “sync right after import”
- Update DB via `Item.store()` / `Library.items()`; do **not** call `item.write()` unless `write_files: yes`.

### Expected input/output

Input:
- A `tagslut` export stream (recommended: JSONL with one record per audio path containing canonical fields + provider IDs).

Output:
- Beets DB fields updated (core fields where safe; flex attributes otherwise).

### Failure modes / limits

- Identity mismatch (ISRC collisions, multiple items with same path).
- Stale exports (tagslut output older than DB state).
- Partial data (some canonical fields missing; must avoid blanking fields unless explicitly allowed).
- Operator intent ambiguity (DB-only vs file-write): default to DB-only.

## 2) `camelotconverter` (required for DJ parity)

### Purpose

Derive a Camelot code (e.g., `8A`) from a musical key (Beets `initial_key`) for DJ workflows and for aligning with `tagslut`’s Camelot handling.

### Why core/external plugins do not cover it

- Beets can store key (`initial_key`) and can compute it (`keyfinder`), but there is no canonical Camelot conversion in core plugins.

### Expected config surface

```yaml
camelotconverter:
  enabled: yes
  auto: no
  source_field: initial_key
  target_field: camelot
  overwrite: no
```

### Beets hook points / APIs

- Command: `beet camelot [QUERY...]`
- Optional import stage (only if `auto: yes`)

### Expected input/output

Input:
- `initial_key` strings from Beets items (and possibly `tagslutsync`-populated keys).

Output:
- `camelot` flex attribute (string).

### Failure modes / limits

- Non-standard key spellings (enharmonics, missing major/minor, “Open Key” formats).
- Lossy mapping decisions (must be explicit; do not overwrite if ambiguous unless configured).

## 3) `genreguard` (recommended when running Beets imports)

### Purpose

Enforce the boundary that `tagslut` owns canonical genre + sub-genre, preventing “helpful” Beets sources from overriding normalized values.

In Beets terms, this usually means protecting `genre` and `style` (where `style` is the most natural built-in slot for `tagslut`’s `canonical_sub_genre`).

### Why core/external plugins do not cover it

- Beets metadata sources and plugins can set `genre` (and related fields) during import, but none know about `tagslut`’s normalization cascade and protection requirements.

### Expected config surface

```yaml
genreguard:
  enabled: yes
  protect:
    - genre
    - style
  allow_overwrite_if_source:
    - tagslutsync
  quarantine:
    genre: ts_raw_genre
    style: ts_raw_style
```

### Beets hook points / APIs

- Import stage listener (after candidate metadata assignment, before store/write).
- Optional command: `beet genreguard [QUERY...]` for post-hoc auditing.

### Expected input/output

Input:
- Candidate metadata assigned during import (MusicBrainz / Beatport4 / Bandcamp / etc.).

Output:
- If a protected field is about to be overwritten by a non-canonical source:
  - move the incoming value to a quarantine flex attribute
  - keep existing canonical value intact

### Failure modes / limits

- Requires a way to detect “canonical source” (e.g., a `tagslutsync_last_synced_at` marker, or a `tagslut_canonical: true` flag).
- If no canonical value exists yet, it should allow population but still quarantine provenance for audit.

### Input / output

Input:
- incoming provider/plugin genre values
- existing canonical sidecar values

Output:
- protected canonical `genre` / `style`
- optional quarantined raw genre field

### Failure modes

- canonical field absent when first imported
- repeated plugin runs trying to overwrite protected values
- confusing dual-field behavior if not documented clearly

## Recommendation

If you only build one custom plugin, build `tagslutsync` first.

That is the plugin that turns the sidecar from “a Beets experiment” into “a Beets layer that actually respects your architecture.”
