# beets-sidecar-research — Beets as sidecar bridge for tagslut

## Do not recreate existing deliverables

The following files have already been produced by a prior run. Do not overwrite them
unless instructed. Read them first to understand what has been decided, then proceed
only to the gap-filling tasks noted at the end of this prompt.

- `docs/beets/BEETS_SIDECAR_PACKAGE.md`
- `docs/beets/BEETS_CUSTOM_PLUGIN_STUBS.md`
- `beets-flask-config/beets/config.yaml`

If any of these files are missing from the repo, create them per the spec below.

---

## Goal

Produce a repo-ready Beets sidecar package that:

- maps real `tagslut` metadata needs against Beets capabilities,
- evaluates Beets core plugins under `beetbox/beets/beetsplug`,
- evaluates external plugins including:
  - Bandcamp-related plugins and their lineage,
  - `Samik081/beets-beatport4`,
  - `adamjakab/BeetsPluginXtractor` (`beets-xtractor`),
  - Essentia dependencies required by xtractor,
  - any other serious Beets plugins that materially help with `tagslut` metadata needs,
- cross-checks all of that against `tagslut`,
- writes a fully written `beets-flask-config/beets/config.yaml`,
- documents unsupported gaps and proposes custom Beets plugin stubs where needed.

---

## Grounding pass inside `tagslut` (read first, no shortcuts)

Read these files before making any external recommendations:

- `AGENT.md`
- `tagslut/metadata/README.md`
- `tagslut/metadata/models/types.py`
- `tagslut/metadata/models/precedence.py`
- `tagslut/metadata/genre_normalization.py`
- `tools/rules/library_canon.json`
- `tagslut/metadata/providers/beatport.py`
- `tagslut/metadata/providers/tidal.py`

If any of these files do not exist, stop and report which are missing. Do not
proceed on assumptions.

From these files, extract:

- active metadata fields,
- provider precedence logic,
- normalization rules (especially genre/sub-genre),
- canon cleanup constraints,
- assumptions about Beatport vs TIDAL,
- any behavior that must not be overridden by Beets.

Treat these files as the authoritative definition of `tagslut`'s metadata model.

Ignore unrelated repo areas. Do not treat `artifacts/beets_library.db` as authoritative.

---

## Mandatory deep-read external plugins

Treat the following as mandatory deep-read candidates:

- `Samik081/beets-beatport4`
- `adamjakab/BeetsPluginXtractor`

For each, verify from the primary repository:

- plugin name used in `plugins:`
- installation method
- config keys and structure
- runtime dependencies
- auth model (if any)
- fields provided or modified
- maintenance signals (commits, releases, issues)
- operational complexity and fragility

### For `beets-beatport4`

Explicitly inspect:

- Beatport v4 API handling
- credential/token model
- artwork behavior
- singleton album behavior
- compatibility with existing `tagslut` Beatport logic

### For `BeetsPluginXtractor`

Explicitly inspect:

- Essentia dependency requirements
- required binaries and model files
- extracted features (bpm, danceability, mood, etc.)
- tag-writing behavior
- alignment vs divergence from `tagslut` metadata

Do not recommend these plugins unless the writeup demonstrates actual inspection.

---

## What to research

### 1. Beets core capabilities

Research relevant built-in plugins and native behaviors:

- autotagging and metadata sourcing
- Beatport support (and its current state)
- genre handling
- lyrics
- replay gain
- artwork
- flexible/custom fields
- tag mapping and inspection
- playlists
- hooks and automation
- import safety
- web/UI support (`beets-flask`)
- non-destructive operation patterns

### 2. External plugins (bounded)

Only include external plugins that materially support:

- a `tagslut` metadata field,
- sidecar-safe enrichment,
- or preservation of DJ-relevant metadata.

Do not include plugins for general completeness.

If plugin identity is ambiguous, resolve it.
If a plugin appears stale, incompatible, or weakly maintained, state it explicitly
with evidence.

---

## `tagslut` metadata needs to map against

### Core identity

- `title`, `artist`, `album`, `isrc`, `release_date`, `year`, `duration`

### DJ metadata

- `bpm`, `key`, Camelot compatibility, `genre`, `sub_genre`, `mix_name`,
  `label`, `catalog_number`

### Extended metadata

- `explicit`, artwork / cover handling, `composer`, lyrics availability,
  replay gain (track + album), `audio_quality`, `tone_tags`,
  `tidal_dj_ready`, `tidal_stem_ready`, waveform / preview data (if realistic)

### Policy constraints

- genre normalization logic
- canon cleanup rules
- Beatport/TIDAL precedence rules

---

## Required deliverables

Write these files inside the repo:

1. `docs/beets/BEETS_SIDECAR_PACKAGE.md`
2. `docs/beets/BEETS_CUSTOM_PLUGIN_STUBS.md`
3. `beets-flask-config/beets/config.yaml`

---

### `BEETS_SIDECAR_PACKAGE.md` must include

- research memo with direct source links
- compatibility matrix: `tagslut field -> core / external / partial / custom / unsupported`
- recommended plugin stack
- maintenance and risk notes per plugin
- version compatibility notes (only where verified)
- install notes
- clear separation of:
  - works today
  - works with external plugin
  - needs custom extension
  - not realistically supported at parity

---

### `BEETS_CUSTOM_PLUGIN_STUBS.md` must include

Only include stubs that are actually needed.

For each:

- purpose
- why existing plugins do not cover it
- expected config surface
- Beets hook points or APIs
- input/output fields
- failure modes

Do not implement. Design only.

---

### `config.yaml` must be

- fully written (no pseudo-config)
- valid YAML
- sidecar-oriented (non-destructive by default)
- explicit about plugin usage
- aligned with verified plugin behavior
- preserving `tagslut` metadata, not replacing it

Do not invent config keys. If something is unsupported, document the gap instead.

---

## Sidecar constraints

- `tagslut` remains source of truth
- no default library reorganization
- no silent metadata overwrites
- preserve genre/sub-genre fidelity
- preserve DJ-relevant metadata

Any deviation must be explicitly justified.

---

## Research standards

Evidence hierarchy:

1. `tagslut` repo
2. official Beets docs
3. Beets source code
4. primary plugin repos
5. PyPI (supporting only)

Rules:

- mark speculation explicitly
- do not invent config or behavior
- verify plugin status (core vs external vs stale)
- explain plugin lineage where relevant (e.g. Bandcamp ecosystem)

---

## Validation before completion

- every plugin in config exists
- config keys are plausible
- YAML is valid
- all priority fields are mapped or flagged
- gaps are explicitly documented
- external plugins are justified, not listed

---

## Output style

- concrete and opinionated
- no generic Beets advice
- distinguish facts from recommendations
- prefer explicit gaps over fake completeness

---

## Stop condition

Done only when:

- all three files are written (or confirmed already correct),
- the system clearly explains:
  - what Beets can do for `tagslut` today,
  - which plugins are worth using,
  - which gaps remain,
  - what exact sidecar config to use,
  - what custom extensions are still needed.
