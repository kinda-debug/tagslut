You are an expert Python and data-modeling engineer working in the tagslut repository.

Goal:
Complete the transition from "haunted wrapper stack" to a clean, explicit, test-covered 4-stage DJ pipeline.
This is a follow-up to a completed architectural redesign. The layers exist. The verbs exist.
The remaining work is: enforcing discipline on the old command surface, hardening invariants,
and making docs/help/tests all agree on the canonical workflow.

═══════════════════════════════════════════════════════
CONTEXT: Read these first, in order
═══════════════════════════════════════════════════════

Agent instructions:
  AGENT.md
  CLAUDE.md

Audit docs (source of truth for all decisions):
  docs/audit/DJ_WORKFLOW_AUDIT.md
  docs/audit/DJ_WORKFLOW_TRACE.md
  docs/audit/DJ_WORKFLOW_GAP_TABLE.md
  docs/audit/MISSING_TESTS.md
  docs/audit/DATA_MODEL_RECOMMENDATION.md
  docs/audit/REKORDBOX_XML_INTEGRATION.md

Current implementation:
  tools/get
  tools/get-intake
  tagslut/cli/commands/dj.py
  tagslut/exec/precheck_inventory_dj.py
  tagslut/exec/mp3_build.py
  tagslut/dj/admission.py
  tagslut/dj/xml_emit.py
  tagslut/storage/schema.py
  tagslut/storage/migrations/
  tests/exec/test_precheck_dj_contract.py
  tests/dj/test_admission.py
  tests/storage/test_mp3_dj_migration.py

═══════════════════════════════════════════════════════
OPERATING RULES
═══════════════════════════════════════════════════════

- Obey AGENT.md as primary rules. CLAUDE.md for Claude-specific behavior.
- Never run destructive git commands (no force-push, no rebase, no history rewriting).
- Keep all edits small and reviewable. No drive-by refactors.
- Work only in the narrowest relevant scope. Do not scan the whole repo.
- Do not touch artifacts, databases, generated files, caches, exports, or unrelated paths.
- If ambiguous (e.g. DJ root path, MP3 root location), ask before guessing.
- Prefer updating docs and tests before touching working code.

═══════════════════════════════════════════════════════
TASK 1: Audit and triage DJ-related docs only (no repo-wide scans)
═══════════════════════════════════════════════════════

Do NOT scan all *.md files across the repo.
Limit doc discovery to the files explicitly listed in the CONTEXT section above,
plus any additional Markdown files that are directly referenced (linked) by those
context docs and are clearly about DJ/MP3/Rekordbox.

For each in-scope Markdown file you open, classify it as one of:

  ESSENTIAL   — actively describes current behavior, workflow, or design.
                Must be updated to reflect the 4-stage pipeline if it mentions DJ/MP3/Rekordbox.
  STALE       — describes old behavior that has been superseded.
                Must be updated or explicitly archived under docs/archive/.
  ORPHAN      — no longer referenced by any code, test, or doc.
                Must be archived or deleted.
  UNRELATED   — unrelated to DJ/MP3/Rekordbox and not stale.
                Leave untouched, note it exists.

Output a triage table:

  | File | Classification | Action | Reason |

Then apply the required actions:
  - Update ESSENTIAL files to reference the 4-stage canonical pipeline.
  - Move STALE and ORPHAN files to docs/archive/ with a one-line deprecation note at the top.
  - Never silently delete — always archive or update.
  - Save reusable prompt files under .github/prompts/ (the VS Code standard location).

═══════════════════════════════════════════════════════
TASK 2: Make the canonical workflow undeniable
═══════════════════════════════════════════════════════

The canonical DJ pipeline is exactly these four stages. No exceptions, no shortcuts:

  Stage 1: Intake masters
    tagslut master intake (or current equivalent)
    Produces: master asset rows, promoted FLACs, provenance records.

  Stage 2: Build or reconcile MP3 library
    tagslut mp3 build --db --dj-root [--identity-ids] [--dry-run|--execute]
    tagslut mp3 reconcile --db --mp3-root [--dry-run|--execute] [-v]
    Produces: mp3_asset rows, linked to track_identity and asset_file.

  Stage 3: Admit to DJ library
    tagslut dj admit --db --identity-id --mp3-asset-id [--notes]
    tagslut dj backfill --db [--dry-run|--execute]
    tagslut dj validate --db [-v]
    Produces: dj_admission rows, dj_track_id_map entries.

  Stage 4: Emit or patch Rekordbox XML
    tagslut dj xml emit --db --out [--playlist-ids] [--skip-validation]
    tagslut dj xml patch --db --out [--prior-export-id] [--playlist-ids]
    Produces: deterministic Rekordbox XML + dj_export_state manifest row.

This 4-stage flow must be the stated primary workflow in:
  - README.md
  - AGENT.md
  - CLAUDE.md
  - Any DJ-specific docs under docs/
  - CLI --help text for all dj and mp3 subcommands

═══════════════════════════════════════════════════════
TASK 3: Demote tools/get --dj to explicit legacy status
═══════════════════════════════════════════════════════

tools/get --dj must no longer masquerade as the recommended curated-library workflow.
Choose one of these two options and apply it:

  Option A — Hard deprecation:
    - Add to tools/get --dj help text:
        "[LEGACY] This flag is deprecated. Use the 4-stage pipeline instead.
         See docs/DJ_PIPELINE.md or run: tagslut dj --help"
    - Print the same deprecation warning to stderr at runtime (not just in --help).
    - Update all docs that mention tools/get --dj to mark it as legacy.

  Option B — Thin wrapper:
    - Rewire tools/get --dj to call, in sequence:
        tagslut mp3 build (or mp3 reconcile if no new FLACs promoted)
        tagslut dj admit (or dj backfill)
        tagslut dj validate
        tagslut dj xml emit
    - The old --dj flag becomes a convenience alias for the 4-stage pipeline, not a parallel path.
    - Document this explicitly.

If Option B is technically safe given the current code, prefer it.
If rewiring requires touching fragile code paths, choose Option A.
Either way, the legacy path must be explicitly second-class in all docs and help text.

═══════════════════════════════════════════════════════
TASK 4: Harden dj_export_state and dj_track_id_map invariants
═══════════════════════════════════════════════════════

These two tables are the load-bearing parts of the XML architecture.
They must have strict, enforced invariants:

  dj_track_id_map:
    - One row per dj_admission. TrackID must be stable across re-emits and patch cycles.
    - Never reassign a TrackID to a different dj_admission row.
    - Test: emit XML, re-emit from same DB state, assert TrackIDs are identical.

  dj_export_state:
    - Every emit or patch writes a manifest row (hash of output XML + DB scope).
    - On re-emit: compare against prior manifest. If hash matches, skip or warn.
      If structure has changed without a DB state change, fail loudly.
    - On patch: verify the prior export ID exists and its manifest hash matches
      the on-disk XML before applying any patch.
    - Test: tamper with emitted XML, re-run patch, assert it fails with a clear error.

  XML determinism:
    - Same DB state → identical XML output on repeated emits.
    - Playlist ordering must be stable (order by ordinal, then by dj_admission_id as tiebreak).
    - Track element ordering within a playlist must be stable.
    - Test: emit twice from unchanged DB, assert output files are byte-identical
      (or logically equivalent after stripping timestamps).

═══════════════════════════════════════════════════════
TASK 5: End-to-end pipeline proofs
═══════════════════════════════════════════════════════

Implement or extend tests so there is at least one green, documented
end-to-end scenario covering each pipeline stage transition:

  E2E-1: intake → mp3 build
    Given: a canonical track_identity and promoted FLAC.
    When: tagslut mp3 build runs.
    Then: mp3_asset row exists, file is on disk at expected path, status is ready.

  E2E-2: existing inventory → mp3 reconcile
    Given: MP3 files already exist under a DJ root with no mp3_asset rows.
    When: tagslut mp3 reconcile runs.
    Then: mp3_asset rows are created, linked to correct track_identity,
          and conflicts or unmatched files are reported clearly.

  E2E-3: existing MP3 → dj admit / backfill
    Given: mp3_asset rows exist, no dj_admission rows yet.
    When: tagslut dj backfill runs.
    Then: dj_admission rows created, dj_track_id_map populated,
          dj validate passes with no errors.

  E2E-4: dj state → deterministic Rekordbox XML
    Given: dj_admission rows, dj_playlist_track rows, dj_track_id_map entries.
    When: tagslut dj xml emit runs, then runs again from same DB state.
    Then: both outputs are logically identical,
          dj_export_state records a manifest hash,
          TrackIDs are stable between runs.

  E2E-5: XML patch integrity
    Given: a prior dj_export_state row and its emitted XML on disk.
    When: one track is added to a playlist, then dj xml patch runs.
    Then: patched XML contains the new track, manifest is updated,
          TrackIDs for unchanged tracks are identical to the prior emit.
    And when: the on-disk XML is tampered with before patching.
    Then: patch fails loudly with a manifest mismatch error.

Test guidelines:
  - Use minimal fixtures (in-memory SQLite where possible).
  - Assert on DB rows AND file/manifest content, not just return codes.
  - Tests should be runnable standalone with no network or DJ hardware.
  - Place under tests/e2e/test_dj_pipeline.py

═══════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════

For each task, produce:
  1. A short markdown summary:
       - What changed
       - Which audit risk or gap this closes (reference the audit docs)
       - How an operator runs the canonical workflow end-to-end after this change
  2. The actual file edits or new files.
  3. Pointers to new or updated tests.

After all tasks are complete, produce a single CHANGELOG.md entry
summarizing the full set of changes as if writing for a future contributor
who has never seen the audit docs.
