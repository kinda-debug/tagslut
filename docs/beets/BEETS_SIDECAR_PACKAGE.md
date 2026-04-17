# Beets sidecar package for `tagslut` (bridge, not replacement)

This design pass treats Beets as a secondary index + UI layer that can optionally *augment* metadata, but never replaces `tagslut`’s provider logic, precedence rules, or genre normalization.

## Grounding: the `tagslut` metadata contract (authoritative)

The active `tagslut` enrichment model is defined in:
- `tagslut/metadata/models/types.py` (provider + canonical fields)
- `tagslut/metadata/models/precedence.py` (Beatport vs TIDAL precedence)
- `tagslut/metadata/genre_normalization.py` (genre/sub-genre normalization cascade + mapping)
- `tools/rules/library_canon.json` (cleanup policy)
- Providers: `tagslut/metadata/providers/beatport.py`, `tagslut/metadata/providers/tidal.py`

Key implications for a Beets sidecar:
- Provider precedence is explicit (see `tagslut/metadata/models/precedence.py`): Beatport wins for DJ fields (`bpm`, `key`, `genre`, `sub_genre`, `label`, `catalog_number`, duration), while TIDAL wins for identity/artwork (`title`, `artist`, `album`, artwork) and composer.
- Genre normalization is centralized (see `tagslut/metadata/genre_normalization.py`): tag cascade priority is `GENRE_PREFERRED` → `SUBGENRE` → `GENRE` → `GENRE_FULL`, then values are resolved into a controlled Beatport-hybrid taxonomy (`canonical_genres` + `style_parent_map`) with Beatport-compatible output tags (`GENRE`, `SUBGENRE`, `GENRE_PREFERRED`, `GENRE_FULL`).
- Canon cleanup policy is explicit (see `tools/rules/library_canon.json`): replaygain tags are removed (`replaygain_*` and explicit `replaygain_*_gain/peak`), and tags like `acoustid_id`/`encoder` are stripped; a small allowlist is preserved (e.g. `composer`, `comment`, `copyright`).
- Therefore: Beets must not silently “improve” genre, and any file-writing plugins must be manual-only in sidecar mode.

## Research memo (primary sources)

### Beets core docs + source
- Beets config reference: https://docs.beets.io/en/stable/reference/config.html
- Beets version baseline for this package (maintenance/risk only): PyPI `beets` `2.7.1` (2026-03-08). https://pypi.org/project/beets/
- Beets core plugins live in `beetsplug/` in `beetbox/beets`: https://github.com/beetbox/beets/tree/master/beetsplug
- Beets item/album fields (“what the DB can store”): https://docs.beets.io/en/stable/dev/library.html and `beets/library.py` / `Item._fields` (the rendered field list is easiest to cite): https://beets.readthedocs.io/en/latest/reference/library.html
- Plugin event system (hook points for custom sync): https://docs.beets.io/en/stable/dev/plugins.html

### Beets core plugin docs (relevant to `tagslut`)
- `web` plugin (sidecar UI): https://docs.beets.io/en/stable/plugins/web.html
- `fetchart` plugin (art fetching) + “cover_art_url” source: https://docs.beets.io/en/stable/plugins/fetchart.html
- `embedart` plugin (embed art): https://docs.beets.io/en/stable/plugins/embedart.html
- `replaygain` plugin: https://docs.beets.io/en/stable/plugins/replaygain.html
- `keyfinder` plugin: https://docs.beets.io/en/stable/plugins/keyfinder.html
- `autobpm` plugin: https://docs.beets.io/en/stable/plugins/autobpm.html
- `types` plugin: https://docs.beets.io/en/stable/plugins/types.html
- `zero` plugin: https://docs.beets.io/en/stable/plugins/zero.html
- `beatport` core plugin (deprecated due to Beatport API retirement): https://docs.beets.io/en/stable/plugins/beatport.html
- `musicbrainz` plugin (external IDs include `tidal`, `beatport`, `bandcamp`): https://docs.beets.io/en/stable/plugins/musicbrainz.html

### External plugins (explicitly verified)
- Beatport v4: `Samik081/beets-beatport4` (plugin name `beatport4`): https://github.com/Samik081/beets-beatport4
  - Config keys verified in README: `singletons_with_album_metadata`, `art*`, `username/password/client_id`. https://github.com/Samik081/beets-beatport4#configuration-reference
- Bandcamp: `snejus/beetcamp` (plugin name remains `bandcamp`): https://github.com/snejus/beetcamp
  - Config keys verified in README: `include_digital_only_tracks`, `search_max`, `art`, `comments_separator`, `truncate_comments`, `exclude_extra_fields`, `genre.*`. https://github.com/snejus/beetcamp#configuration
- Audio analysis (Essentia): `adamjakab/BeetsPluginXtractor` / `beets-xtractor` (plugin name `xtractor`): https://github.com/adamjakab/BeetsPluginXtractor
  - Config keys verified in README: `auto`, `dry-run`, `write`, `threads`, `force`, `quiet`, `keep_output`, `keep_profiles`, `output_path`, `essentia_extractor`, `extractor_profile.highlevel.svm_models`. https://github.com/adamjakab/BeetsPluginXtractor#configuration
  - Essentia extractor binary + models are required (and must match): https://essentia.upf.edu/documentation/

### Bandcamp older lineage (verified as stale)
- `beets-bandcamp` package: last release April 2020 (`0.1.4`) and Python 2-era constraints are common in downstream mirrors. Example: https://pypi.org/project/beets-bandcamp/ and mirrors like https://www.piwheels.org/project/beets-bandcamp/ (release date + version).

## Beets-as-sidecar architecture for `tagslut`

Beets gives you:
1) A queryable SQLite DB + schema for core tags and flexible attributes.
2) A “metadata source plugin” pipeline for import-time matching (MusicBrainz + optional sources).
3) A web UI (`web` plugin) that fits “read-mostly, browse/search” sidecar operation.

For `tagslut`, the bridge strategy is:
- `tagslut` continues to do enrichment (Beatport + TIDAL, precedence, genre normalization).
- Beets imports *without moving or writing* and acts as a searchable UI / index.
- A *custom Beets plugin* (stubbed in `BEETS_CUSTOM_PLUGIN_STUBS.md`) syncs canonical `tagslut` outputs into Beets’ DB as item fields / flex attributes.

## Mapping `tagslut` fields to Beets storage & plugins

### Sidecar storage strategy used by this repo

This sidecar package keeps Beets from becoming a competing metadata authority by storing `tagslut`’s canonical values in *separate* flexible attributes prefixed with `ts_*` (see `config/beets/beets/config.yaml`), while leaving Beets core fields as “what Beets imported / what’s on-disk”.

### What Beets can store natively (core fields)

Beets’ library field list includes (among many others): `title`, `artist`, `album`, `year`, `length`, `genre`, `label`, `catalognum`, `isrc`, `initial_key`, and ReplayGain fields like `rg_track_gain` / `rg_album_gain`. (See Beets’ rendered library field reference.) https://beets.readthedocs.io/en/latest/reference/library.html

### Compatibility matrix (required arrow form)

Core identity
- `title` -> Beets core `title` (stored); source via import tags / MusicBrainz / external sources.
- `artist` -> Beets core `artist` (stored); source via import tags / MusicBrainz / external sources.
- `album` -> Beets core `album` (stored); source via import tags / MusicBrainz / external sources.
- `isrc` -> Beets core `isrc` (stored); best populated by `tagslutsync` custom plugin (sidecar parity) or by existing file tags if present. https://beets.readthedocs.io/en/latest/reference/library.html
- `release_date` -> Beets core is *year/month/day* oriented; `year` is first-class, but full-date parity typically needs a flex attribute (custom). https://beets.readthedocs.io/en/latest/reference/library.html
- `year` -> Beets core `year` (stored).
- `duration` -> Beets core `length` (stored, seconds).

DJ metadata
- `bpm` -> Beets can store `bpm`; for `tagslut` canonical BPM (float), prefer syncing to a separate field (e.g. `ts_canonical_bpm`) via `tagslutsync` and treat `beatport4`/`autobpm`/`xtractor` as fallback helpers only.
- `key` -> Beets core `initial_key` (stored); sourced by `beatport4` (import-time, when Beatport candidate chosen) or `keyfinder` fallback. https://beets.readthedocs.io/en/latest/reference/library.html
- `Camelot-compatible key` -> unsupported in core; needs custom extension (`camelotconverter`) to derive/store e.g. `camelot` flex attr from `initial_key`.
- `genre` -> Beets core `genre` (stored); **must be protected from “lastgenre”-style auto-genre** to preserve `tagslut` normalization boundary. The stored value should already be one of the controlled Beatport-hybrid canonical genres, not an arbitrary raw provider string.
- `sub_genre` -> closest Beets core slot is `style`; recommended mapping: `tagslut.canonical_sub_genre` -> Beets `style`. This remains the secondary controlled field under the same Beatport-hybrid taxonomy; do not let Beets invent parallel style labels.
- `mix_name` -> no strong standard field; store as flex attribute (custom) if needed.
- `label` -> Beets core `label` (stored); sources include `beatport4` and/or Bandcamp via `beetcamp`. https://beets.readthedocs.io/en/latest/reference/library.html
- `catalog_number` -> Beets core `catalognum` (stored); sources include `beatport4` (and sometimes Bandcamp). https://beets.readthedocs.io/en/latest/reference/library.html

Extended metadata worth preserving/exposing
- `explicit` -> no first-class Beets field; store as flex attribute `explicit` (bool) populated by `tagslutsync`.
- `artwork / cover URLs` -> Beets supports local art files + embedding; Beets also supports using a flex attribute `cover_art_url` as a fetchart source. https://docs.beets.io/en/stable/plugins/fetchart.html
- `composer` -> Beets core `composer` exists; populate from tagslut if present. https://beets.readthedocs.io/en/latest/reference/library.html
- `lyrics_available` -> Beets core can store lyrics (and has a `lyrics` plugin), but `tagslut` semantics are “availability” not a lyrics corpus; recommended: store as `lyrics_available` flex attribute; do not auto-fetch lyrics by default.
- `replay_gain_track` / `replay_gain_album` -> map to Beets’ `rg_track_gain` / `rg_album_gain` (and/or `r128_*` depending on your policy); source should remain `tagslut`/TIDAL unless you explicitly run `replaygain`. https://beets.readthedocs.io/en/latest/reference/library.html and https://docs.beets.io/en/stable/plugins/replaygain.html
- `audio_quality` -> flex attribute (custom), populated from `tagslut` (TIDAL media tags); no Beets core parity plugin.
- `tone_tags` -> flex attribute (custom), populated from `tagslut`; no Beets core parity plugin.
- `tidal_dj_ready` / `tidal_stem_ready` -> flex attributes (custom), populated from `tagslut`; no Beets core parity plugin.
- `waveform_url` / `preview_url` -> flex attributes (custom) if you want to surface them in the Beets web JSON API; no Beets core parity UI.

### Compatibility matrix (required table form)

| `tagslut` field | Beets core field(s) | Core / external plugins | Status | Notes |
|---|---|---|---|---|
| title / artist / album | `title` / `artist` / `album` | core | Core | Store natively; sidecar source should be `tagslutsync` or existing file tags. |
| isrc | `isrc` | core | Core | Store natively; match/sync strategy is the gap (see `tagslutsync`). |
| release_date | `year`/`month`/`day` (+ optional flex for full string) | core | Partial | Full-date parity typically needs a flex attribute (`ts_canonical_release_date`) if you care. |
| year | `year` | core | Core |  |
| duration | `length` | core | Core | Stored as seconds. |
| bpm | `bpm` | `beatport4`, `autobpm`, `xtractor` | Partial | Keep `tagslut` canonical BPM in a separate flex attribute (`ts_canonical_bpm`) to avoid silent drift. |
| key | `initial_key` | `beatport4`, `keyfinder` | Partial | `tagslut` key strings vs Beets `initial_key` formatting must be normalized if you want parity. |
| Camelot | (flex) `camelot` | custom (`camelotconverter`) | Custom | Compute from `initial_key` or from synced `tagslut` fields. |
| genre | `genre` | core (+ optional source plugins) | Partial | Must not enable auto-genre plugins (e.g. `lastgenre`) by default; `tagslut` owns normalization. |
| sub_genre | `style` (recommended) or flex `sub_genre` | custom sync | Partial / custom | Beatport4 does not document Beatport sub-genre support; treat Beatport sub-genre as a `tagslut`-only field today. |
| mix_name | (flex) `mix_name` | custom sync | Custom | Beatport4 appends mix to the title; `tagslut` tracks mix separately. |
| label | `label` | `beatport4`, `bandcamp` | Core / external | Straight mapping. |
| catalog_number | `catalognum` | `beatport4`, `bandcamp` | Core / external | Straight mapping. |
| explicit | (flex) `ts_canonical_explicit` | custom sync | Custom | No Beets core field. |
| artwork | album `artpath` (+ embedded art) | `fetchart`, `embedart`, `beatport4`(art), `bandcamp`(art source) | Core / external | Sidecar-safe default is `auto: no` because art operations write files. |
| composer | `composer` | core | Core | Store natively. |
| lyrics availability | (flex) `lyrics_available` | custom sync | Custom | `lyrics` plugin fetches lyrics text, not “availability”; do not auto-fetch by default. |
| replay gain (track/album) | `rg_track_gain` / `rg_album_gain` | `replaygain` | Core | `tools/rules/library_canon.json` explicitly strips replaygain tags; keep Beets replaygain manual-only. |
| audio_quality | (flex) `audio_quality` | custom sync | Custom | No Beets parity for TIDAL media tags. |
| tone_tags | (flex) `tone_tags` | custom sync | Custom | No Beets parity. |
| tidal_dj_ready / tidal_stem_ready | (flex) `tidal_*` | custom sync | Custom | No Beets parity. |
| waveform_url / preview_url | (flex) `waveform_url` / `preview_url` | custom sync | Custom | Beets can store + expose via `web`, but cannot fetch these natively. |

## Beets core plugins: evaluation against `tagslut`

### Sidecar-safe core plugin stack (recommended baseline)

UI / inspection
- `web`: makes Beets a browse/search API/UI. Config keys: `host`, `port`, `readonly`, `include_paths`. https://docs.beets.io/en/stable/plugins/web.html

Non-destructive helpers (kept “manual” by default)
- `types`: declare types for numeric/boolean/date *flex attributes* you add for the sidecar (e.g. `ts_*` fields produced by a future `tagslutsync`). https://docs.beets.io/en/stable/plugins/types.html
- `zero`: can strip unwanted fields in DB and (if you choose) file tags; keep `auto: no` in sidecar mode. Config keys: `fields`, `tags`, `keep_fields`, `update_database`. https://docs.beets.io/en/stable/plugins/zero.html
- `fetchart` / `embedart`: useful, but they *write files* (art files and/or embedded tags). Keep `auto: no` in sidecar defaults. https://docs.beets.io/en/stable/plugins/fetchart.html and https://docs.beets.io/en/stable/plugins/embedart.html

Fallback-only analysis (keep off by default)
- `keyfinder`: compute `initial_key` when missing; keep `auto: no` and `overwrite: no`. https://docs.beets.io/en/stable/plugins/keyfinder.html
- `autobpm`: compute `bpm` when missing; keep `auto: no` and `overwrite: no`. https://docs.beets.io/en/stable/plugins/autobpm.html
- `replaygain`: compute `rg_*` values when missing; keep `auto: no`. https://docs.beets.io/en/stable/plugins/replaygain.html

Genre policy
- Avoid `lastgenre` in the default stack: it will conflict with `tagslut`’s normalization policy and create hard-to-audit drift between “canonical tagslut” and “beets UI”.

Beatport core plugin (do not use)
- Beets’ built-in `beatport` plugin is deprecated because Beatport retired the API it relied on. https://beets.readthedocs.io/en/latest/plugins/beatport.html

### MusicBrainz external IDs (useful sidecar glue)

Beets’ `musicbrainz` plugin can store third-party IDs found via MusicBrainz relationships (including `tidal`, `beatport`, `bandcamp`) into fields such as `tidal_album_id` / `beatport_album_id` / `bandcamp_album_id`. https://docs.beets.io/en/stable/plugins/musicbrainz.html

This does **not** fetch TIDAL/Beatport metadata. It is only an ID bridge that can help correlate Beets items with `tagslut` provider IDs.

## External plugins: evaluation against `tagslut`

### Beatport v4 (`Samik081/beets-beatport4`)

Fit:
- Directly aligned with `tagslut`’s Beatport-first stance for DJ metadata (BPM/key/genre/label/catalog number).
- Practical way for Beets to import/identify electronic releases when MusicBrainz/Discogs are weak.

Plugin identity (verified):
- Plugin name used in `plugins:` is `beatport4`. https://github.com/Samik081/beets-beatport4
- Install: `pip install beets-beatport4`. https://pypi.org/project/beets-beatport4/

Auth model (verified in plugin docs):
- Two supported approaches: (1) username/password in config, or (2) manually copy/paste the Beatport `/token` JSON from browser devtools. https://github.com/Samik081/beets-beatport4
- The plugin documents that it uses a workaround relying on the public API client ID from Beatport’s docs frontend; the `client_id` can be scraped automatically or set manually. https://github.com/Samik081/beets-beatport4

Verified config surface:
- `beatport4.art`, `beatport4.art_overwrite`, `beatport4.art_width`, `beatport4.art_height` (plugin-managed artwork fetching/embedding). https://github.com/Samik081/beets-beatport4#configuration-reference
- `beatport4.singletons_with_album_metadata.*` (optional fill of album-level fields for singleton imports). https://github.com/Samik081/beets-beatport4#configuration-reference
- `beatport4.username`, `beatport4.password`, `beatport4.client_id`. https://github.com/Samik081/beets-beatport4#configuration-reference

Operational risk / fragility:
- Scraping the Beatport docs frontend for `client_id` is a known fragility (it will break if Beatport changes `/v4/docs/` and its scripts). https://github.com/Samik081/beets-beatport4

Maintenance signal (as of 2026-04-13):
- PyPI lists `beets-beatport4` `1.1.0` published `2026-03-08`. https://pypi.org/project/beets-beatport4/

Sidecar posture:
- Keep `art: no` (avoid file writes).
- Keep `singletons_with_album_metadata.enabled: no` by default (extra API calls + title drift risk via mix-name appending).
- Treat Beatport4-derived values as vendor raw unless/until `tagslutsync` overwrites them with canonical `tagslut` values.

### Bandcamp (`snejus/beetcamp`)

Fit:
- Good for Bandcamp-only content and for capturing “cover art URL” into `cover_art_url` (which `fetchart` can then use as an art source). https://docs.beets.io/en/stable/plugins/fetchart.html

Plugin identity (verified):
- Plugin name used in `plugins:` is `bandcamp`. https://github.com/snejus/beetcamp
- Install: `pip install beetcamp`. https://pypi.org/project/beetcamp/

Verified config surface:
- See `beetcamp` README `bandcamp:` configuration block. https://github.com/snejus/beetcamp#configuration

Maintenance signal (as of 2026-04-13):
- PyPI lists `beetcamp` `0.24.0` published “last month”. https://pypi.org/project/beetcamp/

Lineage note:
- The older `beets-bandcamp` project exists but is stale by release history (`0.1.4`, published 2020-04-12). Prefer `beetcamp`. https://pypi.org/project/beets-bandcamp/

### Essentia analysis (`adamjakab/BeetsPluginXtractor` / `beets-xtractor`)

Fit:
- Useful for optional “audio feature research” fields (danceability / mood / loudness-ish descriptors).
- Not a replacement for Beatport/TIDAL DJ metadata. Treat it as opt-in analysis.

Plugin identity (verified):
- Plugin name used in `plugins:` is `xtractor`. https://github.com/adamjakab/BeetsPluginXtractor
- Install: `pip install beets-xtractor`. https://pypi.org/project/beets-xtractor/

Runtime dependencies (verified):
- Requires Essentia’s `streaming_extractor_music` binary and a set of matching SVM model files. https://github.com/adamjakab/BeetsPluginXtractor and https://essentia.upf.edu/documentation/

Operational constraints (verified):
- `auto` mode is not implemented; you must run it manually (e.g. `beet xtractor`). https://github.com/adamjakab/BeetsPluginXtractor#configuration

Extracted fields (verified):
- Extracts a set of flex attributes including `danceability`, `beats_count`, `average_loudness`, mood classifiers, etc. (See PyPI project description for the current list.) https://pypi.org/project/beets-xtractor/

Tag-writing behavior (verified in plugin docs):
- Only BPM is written back to file tags when writeback is enabled; the rest stays in the Beets DB as flex attributes. https://github.com/adamjakab/BeetsPluginXtractor#configuration

Maintenance signal (as of 2026-04-13):
- PyPI lists `beets-xtractor` `0.4.2` published ~`1.9 years` ago. https://pypi.org/project/beets-xtractor/0.4.2/

Sidecar posture:
- Keep disabled by default; use only on explicit batches and avoid writing tags in sidecar mode.

## Recommended plugin stack (opinionated)

Works today (sidecar-safe defaults)
- Core: `web`, `types`, `zero` (manual), `musicbrainz` (genres disabled)
- External: `beatport4` (metadata source, no art, singleton album expansion off)

Works with external plugin (optional)
- Bandcamp: `bandcamp` (via `beetcamp`) if you have Bandcamp-heavy intake
- Analysis: `keyfinder`, `autobpm`, `replaygain`, `xtractor` as deliberate fallback tooling

Needs custom extension (to reach meaningful `tagslut` parity in Beets DB)
- `tagslutsync` (sync canonical `tagslut` output -> Beets DB, DB-only by default)
- `camelotconverter` (derive Camelot code from `initial_key`, consistent with `tagslut`’s Camelot expectations)
- Optional: `genreguard` (enforce “tagslut owns genre/sub-genre” boundary inside Beets workflows)

Not realistically supported at parity
- Native TIDAL enrichment inside Beets matching `tagslut`’s TIDAL fields (DJ/stem readiness, tone tags, audio quality) without calling into `tagslut` or building a new TIDAL plugin.
- Beatport/TIDAL merged resolution with audit trail identical to `tagslut`’s match logging.

## Install notes (minimal, tied to this sidecar stack)

- Beets itself: install per Beets docs. https://docs.beets.io/en/stable/
- Beatport v4 plugin: `pip install beets-beatport4` (or `pipx inject beets beets-beatport4`). https://github.com/Samik081/beets-beatport4#installation
- Bandcamp plugin (optional): `pip install beetcamp`. https://github.com/snejus/beetcamp#installation
- Xtractor (optional): `pip install beets-xtractor` + Essentia extractor + models. https://github.com/adamjakab/BeetsPluginXtractor#installation and https://essentia.upf.edu/documentation/

## Repo-ready config

Use `config/beets/beets/config.yaml` as the baseline sidecar configuration. It is intentionally conservative (no file writes; web UI read-only).
