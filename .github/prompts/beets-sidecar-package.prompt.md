You are ChatGPT in Agent Mode working inside the local repository:

- Local repo: `/Users/georgeskhawam/Projects/tagslut`
- GitHub repo: `https://github.com/kinda-debug/tagslut`

Your task is to do a deep research-and-design pass for using **Beets as a sidecar bridge** for `tagslut`, not as a replacement. You must inspect `tagslut` first, then research Beets core plugins and credible external plugins, then generate a concrete package inside this repo.

Do not guess. Verify plugin identities, config keys, and maintenance status from primary sources.

## Goal

Produce a repo-ready Beets sidecar package that:

- maps real `tagslut` metadata needs against Beets capabilities,
- evaluates Beets core plugins under `beetbox/beets/beetsplug`,
- evaluates external plugins including:
  - Bandcamp-related plugins, including the older `unrblt/beets-bandcamp` lineage if it still matters,
  - `snejus/beetcamp` if that is the current Bandcamp path,
  - `Samik081/beets-beatport4`,
  - `adamjakab/BeetsPluginXtractor` / `beets-xtractor`,
  - any Essentia-related dependencies or wrappers needed by `xtractor`,
  - any other serious Beets plugins you find that materially help with `tagslut`’s metadata needs,
- cross-checks all of that against `tagslut`,
- writes a fully written `beets-flask-config/beets/config.yaml`,
- documents unsupported gaps and proposes custom Beets plugin stubs where needed.

## Grounding pass inside `tagslut` (read first)

Read these files before making recommendations:

- `AGENT.md`
- `tagslut/metadata/README.md`
- `tagslut/metadata/models/types.py`
- `tagslut/metadata/models/precedence.py`
- `tagslut/metadata/genre_normalization.py`
- `tools/rules/library_canon.json`
- `tagslut/metadata/providers/beatport.py`
- `tagslut/metadata/providers/tidal.py`

Treat those files as the authoritative definition of `tagslut`’s active metadata model and provider priorities.

Ignore unrelated repo areas. Do not treat `artifacts/beets_library.db` as authoritative.

## What to research

### 1. Beets core capabilities

Research the relevant Beets built-in plugins and native behaviors, especially anything related to:

- metadata sourcing and autotagging,
- Beatport support,
- Bandcamp-adjacent support if any,
- genre handling,
- lyrics,
- replay gain,
- artwork,
- flexible/custom fields,
- tag inspection and mapping,
- web/UI support,
- playlists,
- hooks/automation,
- import safety,
- non-destructive sidecar operation.

### 2. External plugins

Research and verify credible external plugins that might help cover `tagslut` needs, including but not limited to:

- Bandcamp support plugins,
- Beatport v4 support plugins,
- Essentia / xtractor-based analysis plugins,
- genre/auto-genre plugins,
- ID3/custom tag extraction plugins,
- web/router/UI plugins that complement `beets-flask`,
- any other mature plugin that directly helps preserve or expose `tagslut` metadata.

If a plugin identity is ambiguous, verify it before using it. If a plugin appears abandoned, incompatible, or weakly maintained, say so explicitly with evidence.

## `tagslut` metadata needs to map against

Build your compatibility analysis against at least these fields and behaviors:

### Core identity

- `title`
- `artist`
- `album`
- `isrc`
- `release_date`
- `year`
- `duration`

### DJ metadata

- `bpm`
- `key`
- Camelot-compatible key handling
- `genre`
- `sub_genre`
- `mix_name`
- `label`
- `catalog_number`

### Extended metadata worth preserving or exposing

- `explicit`
- artwork / cover URLs or local artwork handling
- `composer`
- `lyrics_available` / lyrics support
- `replay_gain_track`
- `replay_gain_album`
- `audio_quality`
- `tone_tags`
- `tidal_dj_ready`
- `tidal_stem_ready`
- waveform / preview URLs if feasible

### Tag-policy constraints already present in `tagslut`

- genre and sub-genre normalization logic
- canon cleanup behavior from `tools/rules/library_canon.json`
- Beatport/TIDAL precedence assumptions already encoded in `tagslut`

## Required deliverables

Write these files in the repo:

1. `docs/beets/BEETS_SIDECAR_PACKAGE.md`
2. `docs/beets/BEETS_CUSTOM_PLUGIN_STUBS.md`
3. `beets-flask-config/beets/config.yaml`

### `docs/beets/BEETS_SIDECAR_PACKAGE.md` must include

- a research memo with links to official Beets docs, source, and primary plugin repos,
- a compatibility matrix in this form:
  - `tagslut field -> Beets core plugin / external plugin / unsupported / custom extension needed`,
- a recommended plugin stack,
- maintenance/risk notes for each recommended external plugin,
- Beets-version compatibility notes where you can verify them,
- install notes for the recommended stack,
- a section that separates:
  - works today,
  - works with external plugin,
  - needs custom extension,
  - not realistically supported at parity.

### `docs/beets/BEETS_CUSTOM_PLUGIN_STUBS.md` must include

- only the custom Beets plugin/module stubs that are actually needed after research,
- for each stub:
  - purpose,
  - why core/external plugins do not fully cover it,
  - expected config surface,
  - Beets hook points or plugin APIs to use,
  - expected input/output fields,
  - failure modes and limits.

Do not fully implement custom plugins. Design them clearly enough that an engineer could implement them next.

### `beets-flask-config/beets/config.yaml` must be

- fully written, not pseudo-config,
- consistent with Beets and cited plugin docs/source,
- aligned with **sidecar** use rather than replacement,
- conservative and non-destructive by default unless you justify otherwise,
- explicit about plugin configuration and custom field handling,
- suitable for use with `beets-flask`.

If some config section depends on an external plugin, include it only if you verified the plugin and the config keys. If a desired behavior is unsupported, document the gap instead of inventing config.

## Sidecar constraints

Design for `tagslut` remaining the source of truth.

That means:

- prefer non-destructive behavior,
- do not assume Beets should reorganize or rename the canonical library by default,
- do not assume Beets should replace `tagslut` provider logic,
- do not silently collapse `tagslut`’s genre/sub-genre specificity,
- preserve high-value DJ metadata wherever Beets can realistically store or surface it.

If you think a destructive Beets behavior is warranted, mark it as a recommendation that differs from the default sidecar posture and justify it explicitly.

## Research standards

- Prefer official Beets docs, Beets source, and primary plugin repositories.
- Use PyPI only as supporting evidence for packaging/versioning, not as your only source.
- Mark anything speculative as speculative.
- Do not invent config keys, undocumented auth flows, or unsupported plugin behavior.
- Verify whether a plugin is core, external, deprecated, stale, or superseded.
- When Bandcamp plugin history is confusing, explain the lineage clearly instead of collapsing names together.

## Validation requirements

Before you finish:

- confirm every enabled plugin and config section exists in Beets or the cited plugin source,
- check that `beets-flask-config/beets/config.yaml` is valid YAML,
- check config-key plausibility against docs/source,
- confirm that high-priority `tagslut` fields are either covered or explicitly flagged as gaps,
- explicitly call out fields Beets cannot realistically preserve or source at parity with current `tagslut` metadata.

## Output style

- Be concrete and opinionated.
- Cite sources with direct links.
- Distinguish facts from recommendations.
- Avoid generic Beets setup advice that is not tied to `tagslut`.
- Do not stop at a narrative summary; write the files above.

## Stop conditions

You are done only when all three output files are written and the documentation clearly explains:

- what Beets can do for `tagslut` today,
- which plugins are worth adopting,
- which gaps remain,
- what the exact sidecar config should be,
- what custom Beets extensions would still be needed.
