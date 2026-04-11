# Beets sidecar package for `tagslut`

## Position

This package treats Beets as a sidecar only. `tagslut` remains the metadata authority.

That boundary matters because `tagslut` already defines a canonical metadata model, provider precedence, and genre normalization rules. In the repo, the active provider model includes identity fields such as title, artist, album, ISRC, release date and duration; DJ fields such as BPM, key, TIDAL DJ key variants, replay gain, genre, sub-genre, label, catalog number and mix name; audio features such as danceability and loudness; and TIDAL-specific flags such as `tidal_dj_ready`, `tidal_stem_ready`, `tone_tags`, `audio_quality`, artwork and waveform/preview URLs. The resolution model then collapses those into canonical fields for the final enrichment result.

The precedence rules are also explicit. Beatport is preferred for DJ-facing fields such as BPM, key, genre, sub-genre, label and catalog number. TIDAL is preferred for identity-facing fields such as title, artist, album, artwork and composer. Genre normalization is not delegated to providers directly: `tagslut` applies its own normalization cascade and mapping logic on top of raw tags.

So the safe design is:

- `tagslut` owns canonical values.
- Beets can enrich, inspect, search and expose a UI.
- Beets must not silently replace `tagslut`'s normalized genre/sub-genre or provider precedence logic.
- Beets should run non-destructively by default: no reorganizing, no moving, no writing back to files unless explicitly requested.

## What Beets can do well for `tagslut`

### Works today with core Beets plugins

**Artwork**

`fetchart` and `embedart` are useful as sidecar helpers. They can fetch missing artwork and optionally embed it. In sidecar mode they should be configured conservatively so they only act when art is missing.

**ReplayGain**

The core `replaygain` plugin can compute track and album gain values. This is useful only as a fallback. If `tagslut` or TIDAL already provide replay gain values, Beets should not overwrite them by default.

**Key analysis**

The core `keyfinder` plugin can compute a musical key using KeyFinder or `keyfinder-cli`. This is useful as a fallback when a track has no reliable key from `tagslut`/Beatport.

**BPM analysis**

The core `autobpm` plugin can estimate BPM from audio using Librosa. Again, this is fallback-only. It is not a replacement for Beatport DJ metadata.

**Field typing and cleanup**

The `types` plugin is useful for declaring flexible fields as `float`, `bool`, or `date`, which makes the sidecar DB queryable. The `zero` plugin is useful for enforcing cleanup policy similar to `tools/rules/library_canon.json`, but it should be used carefully because it can strip tags from files if writing is enabled.

**Web/UI**

The core `web` plugin and the surrounding `beets-flask` container are useful as a browse/query layer. That fits the sidecar model well.

### Works today with external plugins

**Beatport v4: `beets-beatport4`**

This is the only Beatport plugin worth considering. The stock Beets Beatport plugin is deprecated because Beatport retired the API it relied on. `beets-beatport4` is a drop-in replacement for the old plugin, updated for Beatport API v4.

What it provides:

- plugin name: `beatport4`
- install method: `pip install beets-beatport4` or `pipx inject beets beets-beatport4`
- Beatport v4 auth support using either username/password in config or a manually pasted token JSON
- optional Beatport artwork fetching using the release image URL
- optional singleton album metadata expansion, including year, album, label, catalog number, albumartist and track number

Why it matters for `tagslut`:

- It aligns with `tagslut`'s preference for Beatport on BPM, key, genre, sub-genre, label and catalog number.
- It is useful when Beets is being used to enrich tracks that have not yet gone through `tagslut`.
- It is still only a helper. It does not implement `tagslut`'s resolution pipeline.

Risks:

- It depends on a workaround around Beatport's public docs frontend client ID.
- Credential-based auth stores Beatport credentials unencrypted in config.
- It may break if Beatport changes the auth flow or public client behavior.

**Bandcamp: `beetcamp`**

If Bandcamp metadata matters in your sidecar, use `beetcamp`, not the older `beets-bandcamp`.

What it provides:

- plugin name: `bandcamp`
- install method: `pip install beetcamp`
- modern Bandcamp metadata extraction with broader field support than the older plugin
- configurable genre extraction modes
- `cover_art_url` output that can be used by `fetchart`
- better maintenance posture than the old HTML-scraping Bandcamp plugin

Where it helps:

- Bandcamp-only material
- catalog numbers, comments, label-style info, and art URL capture

Where it does **not** help:

- BPM, key, Camelot, TIDAL-specific flags, waveform or preview parity

**Audio analysis: `beets-xtractor`**

This plugin is real, but heavy.

What it provides:

- plugin name: `xtractor`
- install method: `pip install beets-xtractor`
- Essentia-backed extraction of BPM, danceability, beats count, average loudness, gender/voice/instrumental classifiers, and several mood descriptors

Dependencies and complexity:

- requires the Essentia `streaming_extractor_music` binary
- requires matching SVM model files
- the README explicitly notes that auto mode is not implemented; you must run it manually
- only BPM is written back to file tags; the other values are flex attributes in the Beets DB

Fit for `tagslut`:

- useful only as optional research enrichment
- not appropriate as a routine mandatory part of the sidecar unless you specifically want those descriptors
- does not replace `tagslut` for canonical DJ metadata

### Plugins that are real but should stay secondary

**`keyfinder`**

Good fallback. Do not let it overwrite trusted Beatport/TIDAL keys by default.

**`autobpm`**

Good fallback. Do not let it overwrite trusted Beatport BPM by default.

**`replaygain`**

Useful for files missing replay gain. Keep `auto: false` unless you explicitly want batch analysis.

**`lastgenre`**

Technically usable, strategically wrong here. It conflicts with `tagslut`'s own genre normalization and should not be part of the default sidecar stack.

**`lyrics`**

Also real, but not part of the default sidecar stack. `tagslut` tracks lyrics availability, not a Beets-managed lyrics corpus.

## What Beets cannot do at parity

These are the real gaps.

### Needs custom extension

**ISRC ingestion as a first-class sidecar identity field**

Beets can store arbitrary fields, but there is no default sidecar-aware plugin that solves your exact `tagslut` identity flow around ISRC matching and sync.

**Camelot compatibility**

Beets can store key values, and keyfinder can generate keys, but there is no built-in canonical Camelot conversion/plugin that matches `tagslut` expectations.

**TIDAL-specific DJ fields**

No core/external Beets plugin gives you:

- `tidal_dj_ready`
- `tidal_stem_ready`
- `tone_tags`
- `audio_quality`
- TIDAL waveform/preview parity

**Direct sync from `tagslut` canonical output into Beets**

Nothing in Beets natively understands `tagslut`'s canonical result model and precedence logic.

### Not realistically supported at parity right now

- full TIDAL enrichment parity
- Beatport/TIDAL merged resolution with explicit canonical audit trail
- native preservation of `tagslut`'s exact genre/sub-genre normalization path
- waveform/preview parity as a normal Beets enrichment path

## Compatibility matrix

| `tagslut` field | Beets support status | Notes |
|---|---|---|
| title / artist / album | Partial | Core Beets can store them; source metadata may come from Beatport4 / Bandcamp / import tags |
| isrc | Partial / custom | Needs a dedicated sync/import strategy for parity with `tagslut` |
| release_date / year | Partial | Available from metadata sources including Beatport4 / Bandcamp |
| duration | Yes | Core item model already supports it |
| bpm | Partial | Beatport4 preferred; Autobpm/Xtractor only fallback |
| key | Partial | Beatport4 preferred; Keyfinder only fallback |
| Camelot | Custom | Needs custom converter layer |
| genre | Partial | Must not override `tagslut` normalization |
| sub_genre | Partial | Beatport4 can help, but normalization policy remains in `tagslut` |
| mix_name | Weak | Not a strong Beets-side story |
| label | Partial | Beatport4 / Bandcamp can provide it |
| catalog_number | Partial | Beatport4 / Bandcamp can provide it |
| explicit | Weak | Storage is possible; source parity is inconsistent |
| artwork | Yes | `fetchart` / `embedart`, conservative mode only |
| composer | Weak | Can be stored; source parity depends on importer/provider |
| lyrics availability | Weak | `lyrics` plugin exists but does not map cleanly to `tagslut`'s semantics |
| replay gain | Yes | `replaygain` plugin, fallback use only |
| audio_quality | Custom / unsupported | No TIDAL parity plugin |
| tone_tags | Custom | No existing plugin |
| tidal_dj_ready | Custom | No existing plugin |
| tidal_stem_ready | Custom | No existing plugin |
| waveform / preview | Unsupported | No realistic parity path in stock Beets |

## Recommended default stack

Default means: worth enabling in the sidecar immediately.

- `beatport4`
- `fetchart`
- `embedart`
- `types`
- `zero`

Optional, enable only when you truly need them:

- `bandcamp`
- `keyfinder`
- `autobpm`
- `replaygain`
- `web`
- `xtractor`

Not recommended in the default stack:

- `lastgenre`
- `lyrics`
- old `beets-bandcamp`

## Operational recommendation

Use Beets in one of two ways only:

### Mode A: browse/query sidecar

- ingest files without moving or copying
- do not write tags back to files
- use Beets DB + web/flask for inspection and filtering
- keep canonical values owned by `tagslut`

### Mode B: selective enrichment sidecar

Same as Mode A, plus:

- allow Beatport4 lookups when helpful
- allow fallback key/BPM analysis only on tracks missing trusted values
- allow optional research-grade analysis with Xtractor on explicit batches

Do **not** let it become a third competing metadata authority.

## Bottom line

A Beets sidecar for `tagslut` is viable, but only within a hard boundary.

It is good for:

- enrichment helpers
- a searchable local DB
- a lightweight web UI
- fallback analysis for missing values

It is not good for:

- canonical metadata resolution
- genre/sub-genre normalization authority
- Beatport/TIDAL precedence authority
- TIDAL DJ metadata parity

So the right architecture is simple:

`tagslut` decides. Beets assists.
