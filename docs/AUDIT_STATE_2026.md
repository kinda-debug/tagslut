```markdown
# Authoritative Repo State Audit Execution Plan

## Summary
- Work from repo root `/Users/georgeskhawam/Projects/tagslut`.
- Run `source env_exports.sh 2>/dev/null || true` first, then complete all
  read-only audit steps, then write `docs/AUDIT_STATE_2026.md` once.
- Do not invoke `tagslut`, do not run pytest, do not read any credential file
  under `~/.tiddl/` or `~/.config/tagslut/`, and do not touch `/Volumes/`.
- Use the repo's actual audit surfaces:
  - provider code: `tagslut/metadata/providers/`
  - provider config: `config/providers.toml`
  - v3 schema: `tagslut/storage/v3/schema.py`
- Planning documents for cross-reference (all present in repo):
  - `docs/archive/reference/Technical Whitepaper Personal TIDAL Metadata Tagger.md`
  - `docs/archive/reference/Technical Whitepaper Building a Personal Beatport
    Metadata Tagger Using the Unofficial v4 API.md`
  - `docs/archive/reference/Technical Whitepaper Personal Qobuz Metadata Tagger.md`
- Retired documents (do not reference in report):
  - `docs/archive/retired/executive-summary.md` — Flask REST API proposal,
    formally retired. Section 10.4 does not exist.
  - Provider Architecture Assessment — phase model retired. Section 10.4
    is the last cross-reference section.

---

## Public Interfaces
- No code, API, or type changes are part of this work.
- The only artifact created or overwritten is `docs/AUDIT_STATE_2026.md`.

---

## Execution Steps

### Step 1 — Repo surface inventory

Run each command from repo root. Capture output verbatim or summarize only
where noted. Note absent paths as ABSENT rather than substituting silently.

```bash
# 3-level directory tree
find . -not -path './.git/*' -not -path './node_modules/*' \
       -not -path './__pycache__/*' -not -path './.venv/*' \
       -maxdepth 3 | sort

# Python package surface
find tagslut/ -name '*.py' | sort

# CLI commands — infer from decorators only, do not invoke tagslut
grep -rn '@.*command\|@.*group' tagslut/cli/ | sort

# Migration files in order
ls -1 tagslut/storage/v3/migrations/ 2>/dev/null || \
find . -name '*.sql' -path '*/migrations/*' | sort

# Prompt files
ls -1 .github/prompts/ 2>/dev/null

# pyproject.toml
cat pyproject.toml

# AGENT.md and CLAUDE.md
cat AGENT.md 2>/dev/null; cat CLAUDE.md 2>/dev/null

# docs/ surface
ls -1 docs/ 2>/dev/null && cat docs/*.md 2>/dev/null

# tools/ and scripts/ surface
ls -1 tools/ 2>/dev/null; ls -1 scripts/ 2>/dev/null
cat tools/get 2>/dev/null
cat tools/get-intake 2>/dev/null
cat tools/get-help 2>/dev/null

# Git metadata
git log --oneline -30
git status
git branch -a

# Repo initialization
source env_exports.sh 2>/dev/null || true
```

---

### Step 2 — Migration chain and schema audit

Migrations 0001–0005 are embedded in `tagslut/storage/v3/schema.py` as
initial DDL by design. They are not discrete migration files. State this
in section 2 and do not treat their absence as a gap.

Read every migration file from `tagslut/storage/v3/migrations/0006` through
the highest-numbered file present. For each, record:
- Migration number and filename
- What it adds, modifies, or drops
- Which tables it touches: `track_identity`, `asset_file`, `asset_link`,
  `files`, or any provenance table
- Whether `ingestion_confidence` uses the five-tier vocabulary:
  `verified | corroborated | high | uncertain | legacy`
  Flag any migration using a four-tier model or omitting `corroborated`.

Then read `tagslut/storage/v3/schema.py` and cross-reference against the
migration chain. Answer explicitly:
- Are there columns in schema.py not covered by any migration?
- Do any migrations reference columns absent from schema.py?
- Does migration 0013 enforce a CHECK constraint for the five-tier vocabulary?
- Does migration 0014 add `dj_validation_state`?
- Are provenance columns (`ingested_at`, `ingestion_method`,
  `ingestion_source`, `ingestion_confidence`) on `track_identity` added by
  a migration? If yes, state which number. If no, flag as CRITICAL GAP.

---

### Step 3 — Provider architecture audit

Read the following files in full:
- `config/providers.toml`
- `tagslut/metadata/provider_registry.py`
- `tagslut/metadata/provider_state.py`
- `tagslut/metadata/enricher.py`
- `tagslut/metadata/store/db_reader.py`
- Every file under `tagslut/metadata/providers/`

Produce one row per concrete provider: `tidal`, `beatport`, `qobuz`,
`reccobeats`. For each, record:
- Activation state from `config/providers.toml`
- Capabilities declared in code
- Capabilities required by the corresponding whitepaper (see Step 9)
- Whether the provider is end-to-end callable or scaffold-only
- Whether a `do_not_use_for_canonical` trust flag is present in config
  or registry
- Whether `provider_registry.py` replaces the hard-coded provider mapping
  in `Enricher._get_provider` or whether the hard-coded mapping still exists
- Whether `provider_state.py` implements the eight activation states:
  `disabled`, `enabled_unconfigured`, `enabled_configured_unauthenticated`,
  `enabled_authenticated`, `enabled_expired_refreshable`,
  `enabled_expired_unrefreshable`, `enabled_degraded_public_only`,
  `enabled_subscription_inactive`

State the enrichment eligibility condition exactly as found in code
(expected: `flac_ok = 1 OR flac_ok IS NULL`; flag if different).

State whether Qobuz genre enrichment is implemented in code or absent.

State the ReccoBeats endpoint as found in code. Flag if it uses the singular
form `/v1/audio-feature` instead of the correct plural `/v1/audio-features`.

---

### Step 4 — Auth and token management audit

Read the following files in full:
- `tagslut/metadata/auth.py`
- `tagslut/metadata/qobuz_credential_extractor.py`
- `tagslut/cli/commands/auth.py`

Flag explicitly with ABSENT / PARTIAL / IMPLEMENTED:
- Does `tagslut auth` exist as a CLI group with `login` and `logout`
  subcommands for TIDAL?
- Does the code read TIDAL tokens from `~/.tiddl/auth.json` via tiddl
  subprocess delegation, or is that delegation absent?
- Does `auth.py` TokenManager use `~/.config/tagslut/tokens.json` as
  the credential store?
- Is Qobuz credential auto-refresh implemented and wired before every
  enrich run? If yes, state the exact file and function. If no, flag as GAP.
- Does `tagslut/metadata/qobuz_credential_extractor.py` exist and implement
  the bundle.js scraping approach?

Do not read `~/.tiddl/auth.json` or any file under `~/.tiddl/` or
`~/.config/tagslut/`.

---

### Step 5 — CLI and active pipeline audit

Read every file under `tagslut/cli/commands/` and
`tagslut/exec/intake_orchestrator.py`.

Infer commands and groups from decorators and registration only.
Do not invoke `tagslut`.

For each command or group found, record:
- Command name and group
- One-sentence purpose
- Whether tests exist under `tests/`

#### Active pipeline verification

The current canonical architecture is:
- `MP3_LIBRARY` = active MP3 output root
- DJ pool membership = defined by `MP3_LIBRARY/dj_pool.m3u`
- Active workflow = `download → enrich → --dj writes M3U → Rekordbox imports M3U`
- `DJ_LIBRARY` = retired as active pipeline destination
- `DJ_POOL_MANUAL_MP3` = legacy, not a current reconcile target
- 4-stage MP3/DJ/XML pipeline = retired
- `--dj-cache-root` = not a real current flag

Verify each item with YES / NO / PARTIAL and cite the evidence file:

- Does `tools/enrich` exist and function as a zero-config enrichment wrapper?
- Does `tools/get-intake` exist? Does it have a `--no-download` flag?
  Is there a documented gap about pre-scan tag-completion before planning?
- Does `--dj` write two M3U files:
    (a) per-batch M3U in the album folder
    (b) accumulating `dj_pool.m3u` at `MP3_LIBRARY` root
  Or is this planned but not yet in code?
- Does `--tag` exist on `tagslut intake url`? Is it wired through
  `intake_orchestrator.py` to run enrich/writeback without requiring `--mp3`?
  Does its help string state that DJ pool admission requires a separate
  `--dj` pass?
- Does a unified `tagslut get <url>` command exist? Or is it absent?
- Does `tagslut auth login/logout tidal` exist? Or is it absent?
- Is `--dj-cache-root` still present in active CLI code?

#### Retired pipeline language grep

Run this command exactly:

```bash
grep -rn 'DJ_LIBRARY\|dj.cache.root\|DJ_POOL_MANUAL_MP3\|4.stage\|xml.emit\|emit.*xml\|XML.*export\|DJ_LIBRARY.*destination' \
  tagslut/ tools/ docs/ README* 2>/dev/null
```

For each hit, record file, line number, matched text, and classify as:
- LIVE CODE (in an active code path)
- DEAD CODE (in a retired or unreachable path)
- DOCUMENTATION ONLY (help text, docstring, comment, or markdown)

Flag any hits in `tagslut/metadata/`, `tagslut/cli/`, or `tagslut/exec/`
as LIVE CODE requiring correction.

---

### Step 6 — Test coverage audit

Run these commands without invoking pytest:

```bash
find tests/ -name '*.py' | sort
grep -rn 'def test_' tests/ | grep -c 'def test_'
grep -rn 'def test_' tests/ | sed 's/:.*$//' | sort | uniq -c | sort -rn
```

For each test file found:
- State which implementation module or command it covers
- State the test count
- State whether the corresponding implementation file exists

Flag:
- Implementation files in audited scope with zero test coverage
- Test files that import from paths that no longer exist
- Whether `tests/exec/test_intake_orchestrator.py` covers both:
    (a) `--tag` accepted without `--mp3-root`
    (b) `--tag` runs enrich while MP3 remains skipped

---

### Step 7 — Rekordbox integration audit

Run these commands exactly:

```bash
ls ~/Library/Pioneer/rekordbox/master.db 2>/dev/null && echo EXISTS || echo ABSENT
grep -rn 'master\.db\|rekordbox\|pioneer' tagslut/ tools/ 2>/dev/null
grep -rn 'dj_pool\.m3u\|\.m3u' tagslut/ tools/ 2>/dev/null
grep -rn '75.*missing\|missing.*75\|missing.*file' docs/ 2>/dev/null
```

State:
- `master.db` awareness: ABSENT / READ-ONLY / READ-WRITE
- M3U emission: IMPLEMENTED or PLANNED ONLY
- 75-missing-entry cleanup task: DOCUMENTED or UNDOCUMENTED

---

### Step 8 — Dependency and environment audit

Run these commands exactly:

```bash
poetry show --tree 2>/dev/null | head -100
python --version 2>/dev/null
sqlite3 --version 2>/dev/null
which ffmpeg && ffmpeg -version 2>/dev/null | head -3
which tiddl 2>/dev/null || echo 'tiddl not on PATH'
```

Compare `pyproject.toml` runtime dependencies against imports found in
audited code paths under `tagslut/`, `tools/`, and `scripts/`, excluding
archive, generated, and cache paths.

Flag:
- Declared-but-unused runtime dependencies
- Imports in code not present in `pyproject.toml`
- Flask or `flask-smorest` presence (optional extra only, not core runtime)
- `alembic` declared but `alembic/versions/` absent

---

### Step 9 — Planning document cross-reference

All three documents are in the repo. Read each in full.

1. `docs/archive/reference/Technical Whitepaper Personal TIDAL Metadata Tagger.md`
2. `docs/archive/reference/Technical Whitepaper Building a Personal Beatport
   Metadata Tagger Using the Unofficial v4 API.md`
3. `docs/archive/reference/Technical Whitepaper Personal Qobuz Metadata Tagger.md`

For each, produce a three-column table:
`Feature / Section | Implementation Status | Notes / Contradictions`

Status values: IMPLEMENTED | PARTIAL | UNIMPLEMENTED | CONTRADICTS CODE

---

## Report format

Write `docs/AUDIT_STATE_2026.md` once, after all steps are complete.
Use exact section headers as shown below.
Use ABSENT for missing files or features. Use WRONG for incorrect behavior.
Use YES / NO / PARTIAL for checklist items.
Ground every finding in a file path and line number where material.
Do not hedge. Do not summarize away contradictions.

```markdown
# Tagslut Repo Audit — 2026-04-02

## 0. Audit Metadata
- Date:
- Branch:
- Last commit (hash + message):
- Auditor: Codex GPT-5.4

## 1. Repo Surface Summary
[3-level tree summary. File counts by type. Structural health verdict.]

## 2. Migration Chain
[Table: number | description | tables affected | confidence tier correct?]
[Note: 0001–0005 are embedded in schema.py initial DDL by design, not
 discrete files. This is not a gap.]
[CRITICAL GAPS bolded.]

## 3. Schema vs Migration Consistency
[Explicit YES / NO / GAP for each key column group.]
[Provenance columns status called out separately.]
[0013 CHECK constraint: YES / NO / WRONG.]

## 4. Provider Architecture
[Table: provider | active | capabilities in code | e2e callable? | gaps vs whitepaper]
[Enrichment eligibility condition quoted exactly from code.]
[provider_registry.py vs hard-coded Enricher mapping: resolved.]
[provider_state.py eight-state implementation: YES / NO / PARTIAL.]
[Qobuz genre enrichment: IMPLEMENTED / ABSENT.]
[ReccoBeats endpoint: correct plural / WRONG singular.]

## 5. Auth and Token Management
[Each item: ABSENT | PARTIAL | IMPLEMENTED with file evidence.]

## 6. CLI and Pipeline
[Table: command | group | purpose | tested?]
[Active pipeline checklist: each item YES / NO / PARTIAL with evidence.]
[Retired pipeline grep: table of file | line | text | classification.]

## 7. Test Coverage
[Table: test file | module covered | test count | verdict.]
[Zero-coverage implementation files listed explicitly.]
[test_intake_orchestrator.py --tag case coverage stated explicitly.]

## 8. Rekordbox Integration
[master.db awareness: ABSENT / READ-ONLY / READ-WRITE.]
[M3U emission: IMPLEMENTED / PLANNED ONLY.]
[75-entry cleanup task: DOCUMENTED / UNDOCUMENTED.]

## 9. Dependency Health
[Declared-but-unused deps. Missing deps. Flask and alembic noted.]

## 10. Planning Document Cross-Reference
### 10.1 TIDAL Whitepaper
### 10.2 Beatport Whitepaper
### 10.3 Qobuz Whitepaper

## 11. Immediate Action Items (≤1 week)
[Ordered list. Format: ITEM — why blocking — exact file to touch.]

## 12. Short-Term Plan (1–4 weeks)
[Ordered list. Format: ITEM — dependency — expected outcome.]

## 13. Long-Term Plan (1–3 months)
[Ordered list. Format: capability goal — prerequisite — risk.]

## 14. Open Questions Requiring Operator Decision
[Exact decision needed for each item. No hedging.]

---

## Hard constraints

- Read-only. The only permitted write is `docs/AUDIT_STATE_2026.md`.
- Do not invoke `tagslut` or `poetry run python -m tagslut` for any reason.
- Do not run `poetry run pytest` or any command that mutates state.
- Do not access any path under `/Volumes/`.
- Do not read `~/.tiddl/auth.json`, `~/.config/tagslut/tokens.json`,
  or any credential file.
- If a file is absent that should exist, document it as ABSENT.
  Do not create it.
- If a directory does not exist, note it and continue.
- Complete all nine steps before writing any output.
- Produce the full report in one pass. No partial output.
