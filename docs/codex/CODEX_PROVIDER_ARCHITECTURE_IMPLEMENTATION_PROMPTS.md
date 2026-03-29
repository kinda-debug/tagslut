# Codex Prompts: Provider Architecture Implementation

These prompts are sequenced to implement the provider-architecture work incrementally and safely.

They are anchored to the current repo reality:
- active metadata runtime is dual-provider only: Beatport + TIDAL
- active contracts are dual-provider only
- credential source of truth is `TokenManager` + `~/.config/tagslut/tokens.json`
- end-state target is a capability-registry model, landed in stages

---

## Prompt 1 — Phase 0: contract freeze and stale-surface correction

```text
You are an expert Python architect working in the tagslut repository.

Goal:
Land Phase 0 only: contract freeze and stale-surface correction, with NO behavior change.

Why:
The active repo contracts and runtime are dual-provider only (Beatport + TIDAL), while several docs and legacy scripts still imply broader active provider support. This doc drift will corrupt later implementation work if not corrected first.

Read first:
1. docs/contracts/metadata_architecture.md
2. docs/contracts/provider_matching.md
3. docs/CREDENTIAL_MANAGEMENT.md
4. tagslut/metadata/enricher.py
5. tagslut/metadata/auth.py
6. tagslut/metadata/providers/__init__.py
7. tagslut/metadata/README.md
8. tagslut/metadata/__init__.py
9. dj-download.sh

Repository facts to preserve:
- Active metadata runtime is Beatport + TIDAL only.
- Enricher currently instantiates only beatport and tidal.
- credentials source of truth is TokenManager + ~/.config/tagslut/tokens.json
- no runtime behavior changes in this PR

Tasks:
1. Audit and correct stale wording in:
   - tagslut/metadata/README.md
   - tagslut/metadata/__init__.py
   - dj-download.sh
2. In each file, distinguish clearly between:
   - active supported surfaces
   - legacy/historical references
   - future/provider-expansion aspirations
3. Do not invent new architecture docs yet.
4. Do not modify provider behavior, auth logic, CLI behavior, or DB schema.
5. If dj-download.sh is clearly stale relative to current supported entrypoints, either:
   - rewrite its messaging to state it is legacy and unsupported, or
   - move it toward archival status with minimal safe edits
6. Add concise notes where needed to prevent future agents from treating stale surfaces as normative.

Deliverables:
- corrected docs/scripts only
- zero code-path behavior changes
- concise summary of every stale claim corrected

Verification:
Run any lightweight tests or commands needed to confirm nothing behavioral changed.
At minimum:
- python -m compileall tagslut
- if there are existing help surfaces tied to changed files, run them and note no behavioral delta

Commit message:
docs(metadata): align provider surfaces with active dual-provider contract
```

---

## Prompt 2 — Phase 1: metadata ProviderRegistry + activation config

```text
You are an expert Python engineer working in the tagslut repository.

Goal:
Implement Phase 1: introduce a metadata ProviderRegistry plus provider activation config, without changing default behavior.

This is the first real architecture step.
Do NOT implement full capability routing yet.
Do NOT add Qobuz yet.
Do NOT change identity-service behavior.

Read first:
1. docs/contracts/metadata_architecture.md
2. docs/contracts/provider_matching.md
3. docs/CREDENTIAL_MANAGEMENT.md
4. tagslut/metadata/enricher.py
5. tagslut/metadata/auth.py
6. tagslut/metadata/providers/__init__.py
7. tagslut/cli/commands/index.py

Current-state facts:
- Enricher hard-codes beatport and tidal instantiation.
- index enrich already accepts --providers ordering.
- credentials live in TokenManager/tokens.json, but activation policy does not exist yet.
- defaults must remain current behavior.

Implement:
1. New metadata registry module, for example:
   - tagslut/metadata/provider_registry.py
2. Registry responsibilities:
   - centralize metadata provider definitions
   - map provider name -> factory
   - expose active default metadata providers
   - reject unknown providers deterministically
3. New config loader for provider activation policy, for example:
   - ~/.config/tagslut/providers.toml
   - file optional; absence must preserve current defaults
4. Initial config scope for this PR:
   - metadata only
   - no download role yet
   - only beatport and tidal entries
5. Example activation semantics for this PR:
   - if no providers.toml exists, both beatport and tidal are considered enabled
   - if config exists, disabled providers are filtered out before Enricher provider creation
   - --providers ordering still applies, but only across enabled providers
6. Refactor Enricher._get_provider to use the registry.
7. Keep TokenManager unchanged except for tiny integration helpers if strictly needed.
8. Do not add CLI commands yet.
9. Do not add capability-state objects yet.
10. Keep behavior backward-compatible by default.

Tests required:
1. registry returns beatport/tidal by default
2. unknown provider name fails deterministically
3. missing config preserves current behavior
4. disabled provider in config is filtered out
5. --providers order still respected after filtering
6. existing Beatport/TIDAL runs require zero new config

Verification:
Run targeted tests you add, plus any existing metadata tests impacted by Enricher/provider loading.

Deliverables:
- provider_registry module
- providers.toml loader
- Enricher refactor
- tests
- small doc note describing providers.toml and default fallback behavior

Commit message:
feat(metadata): add provider registry and activation config for metadata
```

---

## Prompt 3 — Provider state model + status reporting

```text
You are an expert Python engineer working in the tagslut repository.

Goal:
Implement provider state reporting for metadata providers.
This PR is about visibility and contract clarity, not routing complexity.

Read first:
1. docs/contracts/metadata_architecture.md
2. docs/contracts/provider_matching.md
3. docs/CREDENTIAL_MANAGEMENT.md
4. tagslut/metadata/auth.py
5. tagslut/metadata/enricher.py
6. tagslut/cli/commands/index.py
7. the new provider registry/config code from the previous PR

Context:
The repo currently conflates “credentials exist” with “provider usable”.
We need a stable state model layered above tokens.json.

Implement:
1. New provider-state module, for example:
   - tagslut/metadata/provider_state.py
2. Define exact metadata-provider states:
   - disabled
   - enabled_unconfigured
   - enabled_configured_unauthenticated
   - enabled_authenticated
   - enabled_expired_refreshable
   - enabled_expired_unrefreshable
   - enabled_degraded_public_only
3. State resolution must combine:
   - activation config
   - TokenManager status
   - provider-specific public fallback knowledge where applicable
4. For this PR, support only Beatport and TIDAL.
5. Beatport expected logic:
   - if disabled in config => disabled
   - if enabled and token missing but public fallback exists => enabled_degraded_public_only
   - if enabled and valid auth present => enabled_authenticated
   - if enabled and token expired and refresh impossible, but fallback remains possible => enabled_degraded_public_only or enabled_expired_unrefreshable, whichever is more truthful to current code
6. TIDAL expected logic:
   - if disabled in config => disabled
   - if enabled with no usable auth => enabled_unconfigured or enabled_configured_unauthenticated
   - if enabled with valid token => enabled_authenticated
   - if expired but refreshable => enabled_expired_refreshable
   - if expired and not refreshable => enabled_expired_unrefreshable
7. Add a read-only status surface.
Preferred:
   - a new CLI command such as `tagslut provider status`
If that is too invasive, add a narrow helper callable first and wire CLI in the same PR.
8. Output must explain for each provider:
   - enabled/disabled by policy
   - auth presence/absence
   - resolved state
   - whether metadata routing is currently usable

Do not:
- add Qobuz
- add download role
- change enrichment matching behavior
- redesign TokenManager storage

Tests required:
1. state resolution for each provider with missing config
2. disabled provider state
3. valid token state
4. expired token state
5. Beatport no-token public-fallback state
6. status output snapshot or deterministic assertions

Verification:
Run targeted tests and manually exercise:
- tagslut provider status
- tagslut auth status
Ensure outputs are consistent, not contradictory.

Commit message:
feat(metadata): add provider state model and status reporting
```

---

## Prompt 4 — Capability-aware metadata routing

```text
You are an expert Python architect working in the tagslut repository.

Goal:
Implement metadata capability declarations and activation-aware routing, while preserving current default behavior.

This is the step that starts moving from simple registry to capability-aware metadata routing.
Still metadata-only. Still no Qobuz. Still no download-role modeling.

Read first:
1. docs/contracts/provider_matching.md
2. docs/contracts/metadata_architecture.md
3. tagslut/metadata/providers/base.py
4. tagslut/metadata/providers/beatport.py
5. tagslut/metadata/providers/tidal.py
6. tagslut/metadata/provider_registry.py
7. tagslut/metadata/provider_state.py
8. tagslut/metadata/enricher.py
9. tagslut/cli/commands/index.py

Implement:
1. Introduce a typed metadata capability layer.
Minimum capabilities:
   - metadata.fetch_track_by_id
   - metadata.search_by_isrc
   - metadata.search_by_text
   - metadata.export_playlist_seed
2. Each provider must declare which capabilities it supports in principle.
3. Availability must be resolved dynamically from provider state.
Examples:
   - Beatport search_by_isrc requires catalog auth
   - Beatport search_by_text can still be available in degraded/public mode
   - TIDAL export_playlist_seed requires auth
4. Add a metadata router that:
   - takes requested providers in order
   - filters by activation state
   - routes per capability
   - fails with explicit reason when a capability is unavailable everywhere
5. Refactor relevant enrichment paths to use capability-aware routing instead of assuming all providers are equally usable for all operations.
6. Preserve current default outcomes:
   - Beatport + TIDAL remain default metadata providers
   - provider ordering still matters
   - no changes to identity key derivation
7. Improve warnings/logging:
   - do not silently skip unavailable capabilities
   - say exactly why a provider was skipped for a capability

Do not:
- add Qobuz
- add download role
- modify DB schema
- change track_identity rules

Tests required:
1. Beatport search_by_text available in degraded/public mode
2. Beatport search_by_isrc unavailable without auth
3. TIDAL export_playlist_seed unavailable without auth
4. router picks first enabled provider with capability available
5. router skips disabled provider
6. deterministic failure when no provider can satisfy capability
7. regression coverage that current default provider order still works

Deliverables:
- capability model
- metadata router
- provider declarations
- refactor of call sites to use router
- tests
- small contract doc update if needed

Commit message:
feat(metadata): add capability-aware provider routing
```

---

## Prompt 5 — Per-role activation model (metadata vs download)

```text
You are an expert Python engineer working in the tagslut repository.

Goal:
Introduce per-role provider activation config and registry scaffolding for download vs metadata, without yet implementing new download providers.

This PR creates the policy model needed for “service paid or not paid” toggling.
Do NOT implement full Qobuz or Beatport download acquisition yet.
Do NOT break current tools/get and tools/get-intake behavior.

Read first:
1. docs/contracts/metadata_architecture.md
2. docs/contracts/provider_matching.md
3. docs/CREDENTIAL_MANAGEMENT.md
4. tools/get
5. tools/get-intake
6. tagslut/metadata/provider_registry.py
7. tagslut/metadata/provider_state.py
8. tagslut/metadata/enricher.py

Implement:
1. Extend providers.toml schema from metadata-only to per-role activation:
   - providers.beatport.metadata_enabled
   - providers.beatport.download_enabled
   - providers.tidal.metadata_enabled
   - providers.tidal.download_enabled
2. Keep Qobuz out of runtime for now, but design schema so qobuz can be added later cleanly.
3. Introduce role-aware registry concepts:
   - metadata provider activation
   - download provider activation
4. For this PR, download role behavior is mostly status/config only.
5. Add status/reporting so operator can see:
   - metadata enabled/disabled
   - download enabled/disabled
   - current runtime availability for each role
6. Preserve current behavior defaults:
   - Beatport metadata enabled by default
   - TIDAL metadata enabled by default
   - TIDAL download path remains whatever current wrapper/scripts do today
   - Beatport download remains disabled by default
7. Add a narrow integration point or helper for tools/get-intake to consult policy in a later PR, but do not rewrite the shell workflow aggressively yet.
8. Document exact precedence:
   - CLI override
   - profile overlay if present
   - providers.toml
   - built-in defaults

Do not:
- implement Qobuz
- replace shell download orchestration
- change metadata matching rules
- alter identity service

Tests required:
1. per-role config parsing
2. backward-compatible defaults
3. status output for both roles
4. Beatport download disabled by default
5. TIDAL metadata/download role separation visible in state model

Commit message:
feat(providers): add per-role activation model for metadata and download
```

---

## Prompt 6 — Qobuz provider scaffold (off by default, identity-safe)

```text
You are an expert Python engineer working in the tagslut repository.

Goal:
Add Qobuz as an OFF-BY-DEFAULT provider scaffold, metadata-first, identity-safe.

This PR is not the full Qobuz rollout.
It creates the insertion point and guarded behavior.
No Qobuz-driven identity-key derivation is allowed.

Read first:
1. docs/contracts/metadata_architecture.md
2. docs/contracts/provider_matching.md
3. tagslut/storage/v3/schema.py
4. tagslut/storage/v3/identity_service.py
5. tagslut/metadata/provider_registry.py
6. tagslut/metadata/provider_state.py
7. tagslut/metadata/enricher.py
8. tagslut/metadata/auth.py
9. any existing provenance-writing paths relevant to library_track_sources

Important constraints:
- track_identity identity_key derivation must remain unchanged
- Qobuz must not become an authoritative identity key source
- Qobuz should be treated initially as metadata/evidence only
- provider must be off by default in config and routing

Implement:
1. Add Qobuz provider registration surface and config entries.
2. Add Qobuz state handling in provider status.
3. Add a Qobuz provider scaffold module, even if capability support is initially partial.
Minimum acceptable first-pass capabilities:
   - metadata.search_by_text
   - metadata.fetch_track_by_id
Optional only if actually validated:
   - metadata.search_by_isrc
4. Qobuz provider should be feature-flagged or activation-gated off by default.
5. If any provenance/evidence write path exists for provider payloads, route Qobuz there first.
6. Do not write qobuz_id into track_identity as a default identity key mechanism.
7. If you need a safe rule, only allow Qobuz ID promotion into identity-linked fields when corroborated by stronger evidence such as ISRC plus agreement with an authoritative provider.
8. Add explicit warnings/logging for tentative or unvalidated Qobuz capabilities.
9. Update docs to state clearly:
   - Qobuz runtime scaffold exists
   - off by default
   - metadata/evidence only at first
   - not authoritative for identity derivation

Tests required:
1. Qobuz registry presence but disabled by default
2. Qobuz does not route when disabled
3. enabling Qobuz metadata exposes only implemented capabilities
4. identity service behavior unchanged for identical pre-existing Beatport/TIDAL cases
5. Qobuz cannot become identity key source by accident

Commit message:
feat(qobuz): add identity-safe provider scaffold off by default
```

---

## Recommended execution order

1. Prompt 1
2. Prompt 2
3. Prompt 3
4. Prompt 4
5. Prompt 5
6. Prompt 6

If you want the safest path, stop after Prompt 4, evaluate, then decide whether to land Prompt 5 and Prompt 6.
