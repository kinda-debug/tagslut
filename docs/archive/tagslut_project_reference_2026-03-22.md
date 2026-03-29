# tagslut Project — Complete Index

**Updated:** March 22, 2026  
**Scope:** Claude chat conversations + Claude Code (Codex) work + key repo documents  
**Purpose:** Single source of truth for all tagslut-related threads and work streams

---

## CLAUDE CHAT CONVERSATIONS

These are the main planning, decision, and analysis threads. Add all to your Claude Projects sidebar.

### Active Development (Most Recent First)

1. **[Prompt quality evaluation](https://claude.ai/chat/23fd305b-1d37-487d-9365-f2232ea85f1a)**  
   **Date:** March 21, 2026 | **Focus:** Execution & implementation  
   Topics: DB epoch cleanup, repo hygiene, Postman collection optimization (8 passes), bp2tidal.py downloader, TIDDL config, dry-run failure diagnosis (load_env quote stripping)  
   **Key Output:** Full working downloader/tagger, identified quote-stripping bug  
   **Claude Code Delegated:** bp2tidal.py implementation, Postman collection optimization passes

2. **[Architecture investment analysis](https://claude.ai/chat/a53a6699-38ad-470f-92cb-ccf8876a1fb0)**  
   **Date:** March 21, 2026 | **Focus:** Strategic planning  
   Topics: Implementation plan synthesis (Phase 1–6), CSV vs. track_identity relationship, TIDAL PKCE/OAuth resolution, confidence normalization, year tagging policy (electronic vs. reissue), Phase 0 security hygiene  
   **Key Decisions:** Dual-provider constraint (TIDAL + Beatport only), Supabase transaction constraint (RPC functions required), identity_service as sole track_identity writer  
   **Blockers:** Q1 (relationship between CSV pipeline and Supabase table)

3. **[Comparing report assessment capabilities](https://claude.ai/chat/d4669a1a-e481-4e4c-9fdf-0248f91fae1d)**  
   **Date:** March 15, 2026 | **Focus:** Task planning & delegation  
   Topics: Task 1.4 completion (help text), Task 2.1 planning — unified `tagslut intake` command with precheck-before-download, repo structure navigation  
   **Key Deliverable:** Real Task 2.1 implementation plan (intake pipeline with 5 stages)  
   **Constraint Established:** Precheck before download is non-negotiable

4. **[Supabase CLI integration with Claude](https://claude.ai/chat/d8b8ce43-382f-40ae-ae81-e885d987b8e4)**  
   **Date:** March 16, 2026 | **Focus:** Infrastructure & operations  
   Topics: Local dev environment setup, schema audit (42 public tables), RLS policy conflict resolution, operational docs + diagnostic script  
   **Key Outputs:** 4 operational documents (ops manual, RLS policy templates, diagnostic script, quickstart guide), TIDAL ISRC lookup method confirmation  
   **Claude Code Delegated:** Schema audit, RLS debugging

5. **[Reusable repository audit prompt](https://claude.ai/chat/d89a3857-0b9b-4eb4-a740-1fe21e09142b)**  
   **Date:** March 10, 2026 | **Focus:** Process & methodology  
   Topics: Phase 1-aware audit prompt (v2), audit pass reordering, 11 CLI command groups, v3 core tables, known risks, environment variables  
   **Key Output:** Comprehensive audit prompt template with Phase 1 invariants overlay  
   **Claude Code Delegated:** identity_service.py implementation (4 structured prompts), testing, code archival

### Earlier Context (Reference)

6. **[Consolidating music library genres](https://claude.ai/chat/33b28669-1c05-46c2-92f2-94d2e508b3f3)** — Feb 5, 2026  
   Genre standardization, artist lists, tag consolidation (123 → 7-pillar system)

7. **[Continuing from previous discussion](https://claude.ai/chat/9342b788-5b97-46be-8468-a6299dd88090)** — Feb 22, 2026  
   DJ curation workflow, policy profiles, zone config, CLI surface design

8. **[Comparing flaccid and fla_cid repositories](https://claude.ai/chat/d0acad99-b5c0-4cb6-8b7c-48299dc8169e)** — Jan 24, 2026  
   Codebase consolidation (flaccid → fla_cid foundation)

9. **[Sharing code context with Codex in VS Code](https://claude.ai/chat/3a1463d1-6811-4773-93df-34f64ab484ef)** — Mar 9, 2026  
   Context transmission strategy (incomplete)

---

## CLAUDE CODE (CODEX) WORK STREAMS

These are autonomous filesystem tasks. Codex sessions don't appear in chat history but are referenced in the threads above and tracked via repo commits/prompts.

### Current Prompts (In `.github/prompts/`)

Located at: `/Users/georgeskhawam/Projects/tagslut/.github/prompts/`

- **`resume-refresh-fix.prompt.md`** — Fix resume/refresh mode in `tools/get-intake` (3 root causes identified, ready to delegate)
- **`open-streams-post-0010.prompt.md`** — Open work after PR 10 merges
- **`repo-cleanup.prompt.md`** — Triage/archive dead scripts and markdown (in progress)
- **`CODEX_SESSION_STARTUP.prompt.md`** — Bootstrap context for Codex sessions (invariants + current status)
- **`CODEX_BOOTSTRAP_REPORT.md`** — Phase 1 status, PR chain, current blocker

### Recent Codex Executions (From Chat Context)

1. **DB & Repo Cleanup** (March 21 session, #1 above)  
   - Epoch renaming (`EPOCH_2026-03-04` → `LEGACY_2026-03-04_PICARD`)
   - Backup deletion, write-test marker cleanup
   - Sensitive file deletion (auth.txt, tokens, API specs)
   - Artifact archival

2. **Postman Collection Optimization** (March 21 session, #1 above)  
   - 8 passes: cleanup, base_url tracking, ISRC endpoint auth, Track ID validation
   - Identity Verification chain (Beatport → TIDAL → Spotify 3-way ISRC corroboration)
   - Collection-level token guard, validation run setup

3. **TIDAL OAuth Refactoring** (March 21 session, #1 above)  
   - Removed global mutable state
   - Switched to `time.monotonic()`, private naming conventions
   - Commit: `3a3595c`

4. **Tiddl Staging Area Audit** (March 21 session, #1 above)  
   - 52 `tmp*` files deleted (29 album folders with 0 FLACs)
   - Cover JPEGs moved to `cover.jpg` inside album folders
   - Config installed at `~/.tiddl/config.toml`

5. **Identity Service Implementation** (Referenced in #5 above)  
   - 4 modular prompts for staged implementation
   - Signature definitions, `resolve_active_identity()`, `resolve_or_create_identity()`, `mirror_identity_to_legacy()`
   - Parity testing for each function

### Codex Delegation Patterns (From Your Workflow)

**When to use Codex:**
- Clear written prompt ✓
- Autonomous filesystem tasks ✓
- No external judgment calls needed ✓
- Unlimited parallel tasks possible ✓

**When NOT to use Codex:**
- Architecture decisions ✗
- Prompt authoring ✗
- Cross-cutting analysis ✗
- Token efficiency critical (rate limits) ✗

---

## KEY REPOSITORY DOCUMENTS

These files live in your repo and provide context for both Claude chat and Codex work.

### Status & Planning

- **`docs/PHASE1_STATUS.md`** — 15-PR merge chain, current blocker (PR 9), dependency graph
- **`docs/PROGRESS_REPORT.md`** — Completed work, active streams, upcoming phases
- **`docs/ROADMAP.md`** — Agent assignments (Codex vs. Claude Code vs. Copilot+)
- **`PLAN2.md`** — Full Phase 1–6 implementation plan (referenced in prompts, not pasted inline)

### Architecture & Reference

- **`.codex/CODEX_AGENT.md`** — Phase 1 invariants (read by Codex on every invocation)
- **`docs/ARCHITECTURE.md`** — System architecture, module layers, import constraints
- **`docs/DB_V3_SCHEMA.md`** — Supabase v3 schema (core identity model)
- **`docs/CONTRACTS/`** — CSV schemas, provider contracts, identity resolution precedence
- **`.github/workflows/`** — Claude bot automation (issue/PR comments, code review)

### Operational

- **`CHANGELOG.md`** — Unreleased section (current focus: DJ pipeline verification)
- **`.env.example`** — Environment variable reference
- **`Makefile`** — Common operations (pytest, lint, migrations)

---

## HOW TO USE THIS INDEX

### Starting a New Chat in the Project

1. Open the **tagslut** Project in Claude.ai
2. Start a new conversation
3. Reference this index to find:
   - Which prior chat covers a topic (use links)
   - Which Claude Code work was already done (avoid duplication)
   - Which repo documents to attach or paste

### Delegating Work to Codex

1. Open `.github/prompts/CODEX_SESSION_STARTUP.prompt.md` in your editor
2. Append your specific task prompt (5–15 lines, surgical scope)
3. Run: `claude --prompt .github/prompts/CODEX_SESSION_STARTUP.prompt.md`
4. Codex reads `.codex/CODEX_AGENT.md` (invariants) automatically

### Prioritizing Next Steps

Current blocker: **Phase 1 PR 9** (`fix/migration-0006`) must merge before PRs 10–11.

Next unblocked Codex task: **resume/refresh fix** (prompt ready in `.github/prompts/resume-refresh-fix.prompt.md`)

---

## QUICK LINKS

**Project root:** `/Users/georgeskhawam/Projects/tagslut`  
**Active branch:** `dev`  
**GitHub:** `github.com/kinda-debug/tagslut`  
**Database:** `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/music_v3.db`  
**External volumes:** `/Volumes/MUSIC/`, `/Volumes/SAD/`

---

## METADATA

| Field | Value |
|-------|-------|
| Last Updated | 2026-03-22 |
| Conversations Indexed | 9 |
| Codex Prompts Ready | 2 |
| Open PRs (Phase 1) | 6 (PRs 9–15) |
| Rate-Limit Status | Promo hours: weekends + weekdays 12–6pm GMT |
| Copilot+ Account | tagtag (not yet configured) |
