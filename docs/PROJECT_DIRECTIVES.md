# tagslut — Project Directives

These directives apply to every agent working in this repo.
They supplement AGENT.md and CLAUDE.md. When in conflict,
these directives take precedence.

Last updated: 2026-03-21

---

## Identity and origin

Repository: <https://github.com/kinda-debug/tagslut>
Active branch: dev
Owner account: kinda-debug (GitHub), georgeskhawam (personal)
Prior org: tagslut (GitHub) — treat all references to tagslut/tagslut as
pointing to kinda-debug/tagslut. They are the same repo.

---

## DB state

There are two DB contexts. Never confuse them.

LEGACY (read-only archaeology):
  /Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/music_v3.db
  Contaminated by MusicBrainz Picard tags. Do not write to it.
  Do not use as $TAGSLUT_DB default.

FRESH (target for all new work):
  /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db
  Does not exist yet. Must be initialized from migrations.
  All clean-slate ingestion goes here.

$TAGSLUT_DB must point at FRESH once initialized.
Until then, any test that requires a DB must use a temp/fixture DB.

---

## Provenance is non-negotiable

Every track_identity row must have four fields set at insert time:
  ingested_at         ISO 8601 UTC, set once, never updated
  ingestion_method    controlled vocabulary (see INGESTION_PROVENANCE.md)
  ingestion_source    specific evidence string
  ingestion_confidence  verified | high | uncertain | legacy

These are NOT NULL. Any migration or insert that omits them is wrong.
Full spec: docs/INGESTION_PROVENANCE.md

---

## The Picard rule

MusicBrainz Picard must never touch files under $MASTER_LIBRARY.
Any identity derived from Picard-written tags gets:
  ingestion_method = 'picard_tag'
  ingestion_confidence = 'legacy'
and is excluded from DJ export and canonical writeback until
manually reviewed and upgraded.

---

## Volume layout (current machine)

/Volumes/MUSIC/MASTER_LIBRARY    FLAC master library — source of truth for audio
/Volumes/MUSIC/MP3_LIBRARY       MP3 copies for playback
/Volumes/MUSIC/DJ_LIBRARY        DJ-admitted MP3s (admission-gated subset)
/Volumes/MUSIC/DJ_POOL_MANUAL_MP3  Manual DJ pool additions
/Volumes/MUSIC/mdl               Staging root for downloads
/Volumes/MUSIC/lexicondj.db      Lexicon DJ database (read-only reference)
/Volumes/SAD/                    Legacy epoch DBs — read-only, no writes

$MASTER_LIBRARY = /Volumes/MUSIC/MASTER_LIBRARY
$DJ_LIBRARY     = /Volumes/MUSIC/DJ_LIBRARY
$DJ_MP3_ROOT    = /Volumes/MUSIC/DJ_LIBRARY
$STAGING_ROOT   = /Volumes/MUSIC/mdl

If a volume is not mounted, operations that require it must fail
with a clear error — do not silently fall back to local paths.

---

## Tool assignment

Codex:   autonomous implementation — all tasks with a prompt file
         in .github/prompts/. Run from repo root.
         Never ask Codex to design — give it a spec first.

Claude Code (rate-limited — use sparingly):
         judgment-critical work: prompt authoring, architecture
         decisions, cross-cutting audit, debugging where the
         problem itself is unclear.

Copilot+: editor inline completions and single-file chat only.
          Not for agentic tasks.

---

## What Codex must not do without explicit instruction

- Touch tagslut/storage/v3/schema.py without a migration file
- Modify any DB file directly (use migrations only)
- Write to $MASTER_LIBRARY, $DJ_LIBRARY, or any volume
- Change the interface of tools/get or tools/get-intake
  without updating the corresponding CLI help text
- Add new Python dependencies without updating pyproject.toml
  and confirming with the operator
- Run the full test suite — use targeted pytest only

---

## Active task priority order

1. resume-refresh-fix (tools/get-intake) — unblocks daily intake
2. ingestion provenance migration — prerequisite for fresh DB
3. fresh DB initialization — prerequisite for clean-slate ingestion
4. repo cleanup — parallel, no dependencies
5. Phase 1 PR chain (PRs 9-11) — blocked on migration 0006 merge
6. DJ pipeline hardening — after Phase 1

Do not skip ahead. Do not work on item 5 before items 1-2 are done.

---

## Commit conventions

Format: type(scope): description
Types: fix, feat, chore, docs, test, refactor
Scope: the primary file or module changed
Examples:
  fix(intake): suppress dest_exists discard plan in resume mode
  feat(schema): add ingestion provenance columns to track_identity
  chore(cleanup): archive dead scripts and stale docs
  docs(roadmap): update with cleanup progress

One logical change per commit. Do not bundle unrelated changes.
Commit after each completed step, not at end of session.

## Testing policy (clarification)

Default: targeted pytest only.
  `poetry run pytest tests/<specific_module> -v`

Full suite (`poetry run pytest tests/ -x -q`) is permitted ONLY as a final
gate immediately before merging a PR. Never during implementation.
This exception must be stated explicitly in the task — if a prompt does not
say "run the full suite as a final gate", targeted only applies.

## Force-push prohibition

`git push --force` and `git filter-repo` are operator-only maintenance
procedures. They must never appear in a Codex prompt or be executed by
any agent. The git history cleanup task lives in `docs/OPS_RUNBOOK.md`
and is executed manually by the operator only.

## Confidence tier update (2026-03-21)

The four-tier model defined above is superseded. The correct five-tier model is:

  verified        Two+ providers confirmed same ISRC at ingest time (active check)
  corroborated    Multiple stored provider IDs present, all agree on ISRC
  high            Single provider API match, confirmed provider ID
  uncertain       Fuzzy match, fingerprint below 0.90, text-only, or any conflict
  legacy          Picard tag, unknown origin, or unverified migration

Full multi-provider policy: `docs/MULTI_PROVIDER_ID_POLICY.md`

## Three ingestion tracks

Track A (clean-slate): files from Beatport/TIDAL via `tools/get --enrich`
  ingestion_method = 'provider_api'
  ingestion_confidence = 'verified' (both providers agree) or 'high' (one provider)

Track S (Spotify intake): files from Spotify URLs via `tools/get`, `tagslut intake url`, or `tools/get-intake`
  ingestion_method = 'spotify_intake'
  ingestion_confidence = 'high' when ISRC is present, otherwise 'uncertain'
  ingestion_source = `spotiflac:<spotify_url>|service:<winning_service>`

Track B (legacy): older files with accumulated cross-provider IDs
  ingestion_method = 'multi_provider_reconcile'
  ingestion_confidence = 'corroborated' (all IDs agree on ISRC), 'uncertain' (conflict)
  Conflicts preserved in canonical_payload_json.provider_id_conflicts — never dropped

## Provider ID policy

All provider IDs preserved if they do not conflict with the ISRC.
Agreement across providers = positive confirmation.
Conflict = provenance failure — flagged not silently resolved.
Full policy: `docs/MULTI_PROVIDER_ID_POLICY.md`
