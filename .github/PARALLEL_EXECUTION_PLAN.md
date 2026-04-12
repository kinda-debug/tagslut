# Codex Parallelization Plan
# tagslut / dev branch
# Last updated: 2026-04-12 (updated)

## Ground rules

1. Each Codex instance gets ONE prompt. Do not combine prompts in a single run.
2. Instances in the same GROUP may run simultaneously — their file scopes do not overlap.
3. Instances in different groups must be sequenced — later groups depend on earlier group output.
4. After each group: pull, resolve any conflicts, push before starting next group.
5. Filesystem-only prompts (no source changes) can run alongside any code group.

---

## STATUS KEY
# READY       — safe to run now
# STALE       — probably superseded; read before running
# DONE        — already implemented (archive)
# BLOCKED     — depends on another prompt completing first
# NEEDS_REVIEW — scope unclear or may conflict

---

## GROUP 0 — Filesystem only (no repo changes, run any time)

These prompts operate purely on /Volumes/MUSIC. They do not touch the repo.
Can run in parallel with each other AND with any code group.

| Prompt                        | Status | Notes |
|-------------------------------|--------|-------|
| triage-loose-audio            | DONE   | Implemented 0885d93, 11/11 tests |
| absorb-rbx-usb-bpdl-flacs    | DONE   | Absorb ran 2026-04-12 |
| absorb-mp3-to-sort            | DONE   | Ran 2026-04-12 |
| consolidate-playlists         | READY  | Filesystem under /Volumes/MUSIC/playlists/ only |
| cleanup-djpool-home           | READY  | Deletes /Users/georgeskhawam/Music/DJPool |
| mp3-consolidate               | READY  | Filesystem MP3 moves only |

NOTE: triage-loose-audio does write to tools/ and tests/ — do not run it
simultaneously with any prompt that also touches tools/ or tests/.

---

## GROUP 1 — Independent source modules (no shared files)

Run these simultaneously. Each touches a distinct module with no overlap.

| Prompt                        | Files touched                                      | Status |
|-------------------------------|-----------------------------------------------------|--------|
| auth-tidal-logout             | tagslut/cli/commands/auth.py, tests/cli/           | READY  |
| beatport-circuit-breaker      | tagslut/metadata/providers/beatport.py, tests/     | READY  |
| reccobeats-provider-stub      | tagslut/metadata/providers/reccobeats.py, tests/   | READY  |
| fix-mp3-tags-from-filenames   | tagslut/exec/fix_mp3_tags.py, tests/exec/          | READY  |
| dj-pool-named-m3u             | tagslut/dj/m3u.py or similar, tests/dj/            | READY  |
| dj-xml-patch-repair           | tagslut/dj/xml.py or similar, tests/dj/            | READY  |
| qobuz-routing-tools-get       | tools/get ONLY — no Python source                  | READY  |

DO NOT run simultaneously:
- fix-per-stage-resume touches tagslut/metadata/pipeline/stages.py
  — keep separate from intake-pipeline-hardening (same area)

---

## GROUP 2 — Depends on GROUP 1 completions

| Prompt                        | Depends on                    | Status  |
|-------------------------------|-------------------------------|---------|
| register-mp3-only             | fix-mp3-tags-from-filenames   | BLOCKED |
| dj-pool-wizard-transcode      | dj-pool-named-m3u             | BLOCKED |
| fix-per-stage-resume          | (independent but risky)       | READY   |
| intake-pipeline-hardening     | (independent but risky)       | READY   |

fix-per-stage-resume and intake-pipeline-hardening both touch pipeline code.
Run them in separate Codex instances but stagger by 10 min to avoid merge pain,
OR run sequentially.

---

## GROUP 3 — Phase 1 PR chain (strict sequence, one at a time)

These must run in order. Each builds on the previous migration/service state.

Order:
1. phase1-pr9-migration-0006-merge   — migration DDL
2. phase1-pr10-identity-service      — depends on migration 0006/0007 schema
3. phase1-pr12-identity-merge        — depends on PR 10 identity service
4. phase1-pr15-phase2-seam           — depends on PR 12 merge logic

phase1-pr14-agent-docs-update (AGENT.md / CLAUDE.md only) can run in parallel
with any of the above since it touches only docs.

---

## GROUP 4 — Intake features (run after GROUP 3)

| Prompt                        | Depends on                    | Status  |
|-------------------------------|-------------------------------|---------|
| feat-tidal-native-fields      | migration 0006+ merged        | BLOCKED |
| feat-intake-spotiflac         | identity service hardened     | BLOCKED |
| feat-spotify-intake-path      | feat-intake-spotiflac         | BLOCKED |
| lexicon-reconcile             | GROUP 3 complete              | BLOCKED |

feat-tidal-native-fields and lexicon-reconcile touch different modules
and can run simultaneously once GROUP 3 is done.

---

## GROUP 5 — Docs and cleanup (run any time, low risk)

These only touch docs/, .github/, or archived files.

| Prompt                        | Status       | Notes |
|-------------------------------|--------------|-------|
| docs-housekeeping-2026-04     | NEEDS_REVIEW | May overlap with docs-housekeeping-2026-04b |
| docs-housekeeping-2026-04b    | NEEDS_REVIEW | Read both before running either |
| repo-cleanup                  | STALE        | May conflict with repo-cleanup-supplement |
| repo-cleanup-supplement       | STALE        | Run after repo-cleanup |
| repo-audit-and-plan           | READY        | Read-only; writes docs/ACTION_PLAN.md only |
| phase1-pr14-agent-docs-update | READY        | AGENT.md + CLAUDE.md only |

---

## STALE / NEEDS REVIEW before running

| Prompt                        | Issue |
|-------------------------------|-------|
| postman-api-optimize          | DONE   | Marked COMPLETE in file header — archive it |
| rename-mdl-to-staging         | DONE   | Implemented, archive it |
| beets-sidecar-research        | Research doc only — check if feat-beets-sidecar supersedes |
| beets-sidecar-package         | Check if feat-beets-sidecar covers this |
| feat-beets-sidecar            | Runs on separate branch feat/beets-sidecar — safe to run any time |
| codex_prompt_build_dj_seed_from_tree_rbx | Old naming convention — verify scope |
| dj-missing-tests-week1        | Check against current test coverage first |

---

## Parallel execution checklist (before starting a group)

[ ] git pull --rebase origin dev
[ ] Confirm no uncommitted changes on dev
[ ] Verify each prompt's target files don't appear in `git status`
[ ] Launch Codex instances (one tab per prompt)
[ ] After all finish: git pull each result, review conflicts, push
[ ] Run targeted pytest for each changed module before moving to next group
