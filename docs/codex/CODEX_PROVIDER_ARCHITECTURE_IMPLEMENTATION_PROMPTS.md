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
5. In `tools/get-intake`, locate the `ENRICH_PROVIDERS` default variable. If it lists provider
   names that are not exported by `tagslut/metadata/providers/__init__.py`, add a comment marking
   those names as future/aspirational so operators do not assume they are functional.
6. In `tagslut/cli/commands/index.py`, find any help text that references Qobuz or other non-active
   providers in a way that implies current support. Align those strings with contract scope by
   labelling them explicitly as "future/optional" or removing the specific provider names.
7. If dj-download.sh is clearly stale relative to current supported entrypoints, either:
   - rewrite its messaging to state it is legacy and unsupported, or
   - move it toward archival status with minimal safe edits
8. Add concise notes where needed to prevent future agents from treating stale surfaces as normative.

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
5. Canonical key names for this PR (use these exactly — Prompt 5 extends them):
   - `providers.beatport.metadata_enabled = true|false`
   - `providers.tidal.metadata_enabled = true|false`
   - `providers.beatport.trust = "dj_primary" | "secondary" | "do_not_use_for_canonical"`
   - `providers.tidal.trust = "dj_primary" | "secondary" | "do_not_use_for_canonical"`
   Note: `trust` is NOT a routing weight. It is the operator-declared signal that gates
   whether a provider's ID may be promoted into `track_identity` identity keys. A provider
   with `trust = "do_not_use_for_canonical"` must never contribute to identity key derivation
   even if its credentials are valid and it is enabled for metadata.
6. Example activation semantics for this PR:
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

IMPORTANT pre-condition before writing the state machine:
The provider matching contract (docs/contracts/provider_matching.md) describes TIDAL using OAuth 2.1
Authorization Code + PKCE. The current TokenManager implementation uses a device-authorization style
flow. Read both before implementing. Document the exact delta in a code comment at the top of
provider_state.py. The state machine must reflect actual TokenManager behavior, not the contract's
aspirations. If the two diverge in a way that affects enabled_expired_refreshable vs
enabled_expired_unrefreshable transition logic, note it explicitly as a follow-up item — do not
silently paper over it.

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
   - enabled_subscription_inactive  (token valid, but entitlement probe confirms subscription lapsed;
     only emit this state when the provider has a validated entitlement probe — do NOT emit it
     as a guess; fall back to enabled_authenticated if probe is unavailable or unvalidated)
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
6. enabled_subscription_inactive NOT emitted when no entitlement probe is available
7. status output snapshot or deterministic assertions

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
   - metadata.fetch_artwork
   - auth.refresh
   - auth.validate_credentials
Note: fetch_artwork is currently invoked ad hoc inside provider internals and is not
activation-gated. Declaring it as a named capability makes it routeable and enables
the router to skip providers that are enabled but have no artwork access.
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

IMPORTANT — define this before tests are written:
When a pipeline stage requests search_by_isrc and no provider can satisfy it (e.g., Beatport is the
only configured provider and it is in degraded/public mode), the router must emit a deterministic
result from one of exactly three options:
  a) block — raise an exception and halt the pipeline stage
  b) proceed-with-uncertain — continue, set ingestion_confidence = 'uncertain' on the identity row
  c) skip — skip this enrichment step, leave field unset, log reason
Pick option (b) as the default for metadata-only ISRC resolution failures, consistent with the
pipeline's existing behavior (missing tags should not block promotion). Implement this as a named
policy constant (e.g., ISRCResolutionFallbackPolicy.PROCEED_UNCERTAIN) so it can be changed
without editing routing logic.

Tests required:
1. Beatport search_by_text available in degraded/public mode
2. Beatport search_by_isrc unavailable without auth
3. TIDAL export_playlist_seed unavailable without auth
4. router picks first enabled provider with capability available
5. router skips disabled provider
6. deterministic failure when no provider can satisfy capability
7. regression coverage that current default provider order still works
8. ISRC resolution failure in degraded mode yields ingestion_confidence = 'uncertain', not exception

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
1. Extend providers.toml schema from metadata-only to per-role activation.
   Use these exact key names — they are the canonical names established in Prompt 2 and must be
   consistent across all config parsing, status output, and test fixtures:
   - providers.beatport.metadata_enabled = true|false
   - providers.beatport.download_enabled = true|false
   - providers.beatport.trust = "dj_primary" | "secondary" | "do_not_use_for_canonical"
   - providers.tidal.metadata_enabled = true|false
   - providers.tidal.download_enabled = true|false
   - providers.tidal.trust = "dj_primary" | "secondary" | "do_not_use_for_canonical"
   Do NOT use shortened forms (metadata/download without _enabled suffix) or alternate casing.
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
5. Write all Qobuz metadata and evidence to library_track_sources using this exact write contract:
     (identity_key, provider='qobuz', provider_track_id=<id>, source_url, raw_payload_json, metadata_json)
   Do NOT create a new table or a parallel evidence store. library_track_sources is the designated
   home for non-authoritative provider evidence.
6. Do not write qobuz_id into track_identity as a default identity key mechanism.
7. Only allow Qobuz ID promotion into track_identity.qobuz_id when ALL of the following are true:
   - ISRC is present and matches between Qobuz and at least one authoritative provider
   - The corroborating provider has trust != 'do_not_use_for_canonical'
   - No existing qobuz_id conflict exists in track_identity (the column has a uniqueness constraint
     for active rows — a duplicate write produces a hard constraint violation, not a soft conflict)
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
5. Qobuz cannot become identity key source by accident:
   a) attempt to write a qobuz_id to track_identity WITHOUT corroboration — assert it is rejected
      at the application layer before the DB is touched
   b) attempt to write a DUPLICATE qobuz_id to track_identity — assert the SQLite uniqueness
      constraint fires and the error is caught and logged, not silently swallowed
6. library_track_sources write: assert the correct fields are present and raw_payload_json is valid JSON
7. Attempt to write a duplicate qobuz_id to track_identity directly (bypassing the
   library_track_sources path) and assert the DB uniqueness constraint fires before any
   application-level guard is reached. This test proves the schema is the last line of defense,
   not just the application code.

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
7. Prompt 7
8. Prompt 8

If you want the safest path, stop after Prompt 4, evaluate, then decide whether to land Prompt 5 and 6.
Stop again after Prompt 6. Prompts 7 and 8 require Qobuz to be operationally validated in staging
before download integration proceeds.

---

## Prompt 7 — Qobuz and Beatport download provider adapters (Phase 5)

```text
You are an expert Python engineer working in the tagslut repository.

Goal:
Implement DownloadProvider adapters for Qobuz (primary) and optionally Beatport (secondary),
activation-controlled, without replacing the existing TIDAL/tiddl acquisition path.

Pre-requisites that must be confirmed complete before starting this prompt:
- Prompt 6 (Qobuz scaffold) is merged and on dev
- Qobuz metadata integration has been operationally validated in staging (at least one real
  track enriched successfully via Qobuz metadata path)
- Operator has confirmed Qobuz account purchase-download workflow is accessible

Read first:
1. docs/contracts/metadata_architecture.md
2. docs/DOWNLOAD_STRATEGY.md
3. tagslut/metadata/provider_registry.py
4. tagslut/metadata/provider_state.py
5. tools/get
6. tools/get-intake
7. tagslut/storage/v3/schema.py (specifically asset_file.download_source)

Context:
- Today TIDAL download is implemented as an external wrapper (tools/tiddl) called by tools/get-intake.
- Beatport downloads are explicitly rejected in tools/get as retired.
- Qobuz supports DRM-free purchased downloads via official store workflow.
- asset_file.download_source already exists as the acquisition provider field.

Implement:
1. Define a DownloadProvider protocol/ABC:
   - download_track(isrc: str, dest_dir: Path) -> DownloadResult
   - download_release(release_id: str, dest_dir: Path) -> list[DownloadResult]
   - DownloadResult must carry: file_path, provider, provider_track_id, format, download_source
2. Implement QobuzDownloadProvider wrapping the official Qobuz purchase-download workflow.
   - Must set asset_file.download_source = 'qobuz' on the resulting file row
   - Must NOT touch track_identity.qobuz_id unless Prompt 6 corroboration rules are satisfied
   - DRM-free formats only; reject DRM-encumbered responses with a clear error
3. Implement BeatportDownloadProvider as a minimal stub (raise NotImplementedError with
   a clear message) unless the Beatport store download workflow has been validated in the
   current session. Do not implement a broken download path silently.
4. Wire both adapters into the provider registry under the download role.
5. Default activation:
   - providers.qobuz.download_enabled = false (operator must explicitly enable)
   - providers.beatport.download_enabled = false (unchanged from current)
   - providers.tidal.download_enabled = true (existing wrapper behavior preserved)
6. tools/get-intake download routing must consult providers.toml precedence before
   dispatching a download. Do not rewrite the shell script; add a thin Python helper
   (e.g., tagslut download route <url_or_id>) that the shell calls.
7. Preserve existing TIDAL/tiddl path exactly — this is not a migration of TIDAL downloads.

Do not:
- Remove or modify the tiddl wrapper invocation in tools/get-intake
- Write qobuz_id to track_identity without satisfying Prompt 6 corroboration contract
- Mark Beatport download as implemented unless store workflow is validated end-to-end
- Modify identity service

Tests required:
1. QobuzDownloadProvider.download_track returns DownloadResult with download_source = 'qobuz'
2. download_source is written to asset_file row correctly
3. Beatport stub raises NotImplementedError with explanatory message
4. registry returns qobuz and beatport adapters when configured, but routes only enabled ones
5. disabled download provider never receives a dispatch call
6. TIDAL download path unaffected (existing integration test still passes)
7. provider precedence in providers.toml determines dispatch order

Commit message:
feat(download): add Qobuz download adapter and download provider protocol
```

---

## Prompt 8 — Stale surface archival and provider scope cleanup (Phase 6)

```text
You are an expert Python engineer working in the tagslut repository.

Goal:
Complete Phase 6: archive stale scripts, align all provider scope references with the
post-Prompt-7 live runtime, and remove dead doc references. This is cleanup only —
no new behavior, no schema changes.

Pre-requisites:
- Prompts 1–7 are all merged on dev
- Operator has confirmed no active workflows depend on any of the files being archived

Read first:
1. docs/codex/CODEX_PROVIDER_ARCHITECTURE_IMPLEMENTATION_PROMPTS.md (this file — stale surfaces
   list from Prompt 1 onwards)
2. dj-download.sh
3. tools/get-intake (ENRICH_PROVIDERS default)
4. tagslut/cli/commands/index.py (help text)
5. tagslut/metadata/README.md
6. tagslut/metadata/__init__.py

Tasks:
1. Archive dj-download.sh:
   - Move to docs/archive/ with a header comment: "Archived YYYY-MM-DD. Superseded by
     tools/get-intake and tagslut intake url. Do not use."
   - If a symlink or reference to it exists in any active script or Makefile, remove it.
2. Align tools/get-intake ENRICH_PROVIDERS default:
   - The default provider list must contain only names that are exported by
     tagslut/metadata/providers/__init__.py and registered in provider_registry.py.
   - Remove or comment out any name not in the active registry.
3. Final pass on tagslut/cli/commands/index.py help strings:
   - No provider name should appear in help text that is not in the live registry.
   - If a capability or provider is labeled 'future/optional' from Prompt 1, confirm the
     label is still accurate or remove entirely.
4. Final pass on tagslut/metadata/README.md and tagslut/metadata/__init__.py:
   - These were corrected in Prompt 1 but may have drifted. Re-verify against live exports.
   - Provider list must match: beatport, tidal, qobuz (off by default).
   - No mention of Spotify, Apple Music, or any other provider as active or planned.
5. Remove any dead doc references to providers not in the registry from all docs under docs/.
   Use grep to identify them. Limit scope to docs/ — do not touch contracts/ without operator
   review.
6. Confirm no test fixture, conftest, or factory references a provider name that no longer exists
   in the registry. Update fixture names to match registry canonical names.

Do not:
- Modify tools/get or tools/get-intake download orchestration logic
- Remove contracts/ files — those are normative references, not stale
- Delete any file without moving it to docs/archive/ first
- Touch DB schema or migrations

Verification:
- python -m compileall tagslut
- poetry run pytest tests/metadata/ -v (all must pass)
- grep -r 'qobuz\|beatport\|tidal\|spotify\|apple' tagslut/metadata/ --include='*.py' and
  confirm every hit is either (a) a live provider module, (b) a test, or (c) an archived ref
  with a clear label
- tagslut provider status — output must list exactly: beatport (enabled), tidal (enabled),
  qobuz (disabled by default)

Deliverables:
- archived dj-download.sh
- corrected ENRICH_PROVIDERS in tools/get-intake
- final-pass help text and README corrections
- summary of every file touched and every dead reference removed

Commit message:
chore(cleanup): archive stale provider surfaces and align docs with live registry
```

---

## Prompt 7 — Download provider adapters (Phase 5)

```text
You are an expert Python engineer working in the tagslut repository.

Goal:
Implement download provider adapters for TIDAL (wrapper-based) and Qobuz (purchase download),
and introduce an optional Beatport download adapter stub. All three are activation-controlled
via providers.toml. No existing acquisition workflows are broken.

Read first:
1. docs/contracts/metadata_architecture.md
2. docs/DOWNLOAD_STRATEGY.md
3. tools/get
4. tools/get-intake
5. tagslut/metadata/provider_registry.py
6. tagslut/metadata/provider_state.py
7. tagslut/storage/v3/schema.py  (asset_file.download_source column)

Constraints:
- tools/get and tools/get-intake CLI interfaces must not change.
- Beatport downloads remain disabled by default (providers.beatport.download_enabled = false).
- TIDAL download remains a wrapper-based adapter calling tools/tiddl; it does not become a direct
  Python download implementation.
- Qobuz download adapter targets the official purchase-download workflow only (DRM-free). It does
  not scrape or reverse-engineer the streaming endpoint.
- asset_file.download_source must be set consistently for all acquisition paths:
    'tidal_wrapper' | 'qobuz_purchase' | 'beatport_store' | 'manual'
- ingestion_method for downloaded files = 'provider_api'; ingestion_confidence follows the
  five-tier model.

Implement:
1. Define a DownloadProvider abstract base class with:
   - download_track(isrc: str, dest_dir: Path) -> DownloadResult
   - download_release(release_id: str, dest_dir: Path) -> list[DownloadResult]
   - declared capabilities (download.download_track, download.download_release)
2. Implement TidalWrapperDownloadProvider:
   - wraps the existing tools/tiddl call as a subprocess
   - resolves activation state from providers.toml providers.tidal.download_enabled
   - sets asset_file.download_source = 'tidal_wrapper'
3. Implement QobuzPurchaseDownloadProvider:
   - uses Qobuz purchase-download API (authenticated; requires providers.qobuz.download_enabled)
   - sets asset_file.download_source = 'qobuz_purchase'
   - capability advertised as download.download_track only for this PR (no bulk release download yet)
4. Add BeatportStoreDownloadProvider as a disabled-by-default stub:
   - raises NotImplementedError when called
   - state always reports disabled unless providers.beatport.download_enabled = true in config
   - stub must be wired into registry so activation can be toggled later without code changes
5. Register all three in ProviderRegistry under the 'download' role.
6. Do NOT wire download providers into tools/get-intake shell orchestration in this PR.
   Add a TODO comment in get-intake at the point where a registry call would be inserted.

Tests required:
1. TidalWrapperDownloadProvider disabled when providers.tidal.download_enabled = false
2. QobuzPurchaseDownloadProvider disabled when providers.qobuz.download_enabled = false
3. BeatportStoreDownloadProvider always raises NotImplementedError when called (even if enabled)
4. asset_file.download_source set correctly per provider
5. DownloadResult fields present and consistent with asset_file schema
6. registry returns correct download provider by precedence from providers.toml routing.download.precedence

Commit message:
feat(providers): add download provider adapters for TIDAL, Qobuz, Beatport stub
```

---

## Prompt 8 — Phase 6: stale surface archival and final cleanup

```text
You are an expert Python engineer working in the tagslut repository.

Goal:
Archive or correct all stale provider-related docs and scripts identified in Phase 0 assessment
that were deferred from Prompt 1. This is a cleanup-only PR — no behavior changes.

Read first:
1. docs/contracts/metadata_architecture.md  (normative; use as ground truth for what is active)
2. tagslut/metadata/providers/__init__.py   (active provider exports; use as ground truth)
3. tools/get-intake                          (ENRICH_PROVIDERS variable and default list)
4. tagslut/cli/commands/index.py            (provider help text and narrative strings)
5. dj-download.sh
6. tagslut/metadata/README.md
7. tagslut/metadata/__init__.py

Tasks:
1. tools/get-intake ENRICH_PROVIDERS:
   - Align the default variable value to only list providers that exist in
     tagslut/metadata/providers/__init__.py exports.
   - If a provider name was previously listed as a future/aspirational comment (added in Prompt 1),
     either remove it from the default value or confirm it is now real after Prompts 2-7.
   - Do not change the variable interface or any other get-intake behavior.

2. tagslut/cli/commands/index.py help text:
   - Remove or relabel any provider names that are not yet active as real, routeable providers.
   - Labels must be consistent with providers.toml and ProviderRegistry.

3. dj-download.sh:
   - Move to docs/archive/ as dj-download.sh.LEGACY
   - Add a one-line header comment: "LEGACY: replaced by tools/get and tools/get-intake. Do not use."

4. tagslut/metadata/README.md:
   - Rewrite the active provider list section to reflect only Beatport + TIDAL as active metadata
     providers and Qobuz as "scaffold, off by default."
   - Move any stale provider sections (Spotify, Apple Music, etc.) to a Legacy section at the bottom.

5. tagslut/metadata/__init__.py docstring:
   - Remove Qobuz/Spotify/Apple Music claims from the active provider list.
   - Replace with: "Active metadata providers: Beatport, TIDAL. Qobuz: scaffold, off by default."

6. Confirm no runtime behavior changed:
   - python -m compileall tagslut
   - poetry run pytest tests/test_tidal_beatport_enrichment.py -v
   - tagslut --help (confirm help text still renders without error)

Do not:
- touch schema, migrations, or DB files
- modify any provider Python implementation
- change tools/get interface
- move or rename files other than dj-download.sh

Commit message:
chore(cleanup): archive stale provider docs and align active surfaces with contracts
```

---

## Recommended execution order

1. Prompt 1
2. Prompt 2
3. Prompt 3
4. Prompt 4
5. Prompt 5
6. Prompt 6
7. Prompt 7 (after Prompt 6 is verified stable)
8. Prompt 8 (final cleanup; can run in parallel with Prompt 7 if scopes don't collide)

Stop after Prompt 4 if any routing behavior deviates from current defaults.
Evaluate before proceeding to Prompt 5 and beyond.
