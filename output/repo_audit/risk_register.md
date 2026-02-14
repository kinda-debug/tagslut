# Risk Register

## Critical Risks

### R1: Stale Version Snapshots (tools/review/promote_by_tags_versions/)

**Severity:** Medium
**Impact:** Confusion, accidental use of outdated code
**Status:** MITIGATED (this audit)

**Description:**
16 timestamped snapshots of `promote_by_tags.py` exist in `tools/review/promote_by_tags_versions/`. These are historical backups, not active code.

**Mitigation:**
- Archive to `tools/archive/promote_by_tags_versions/`
- Only `tools/review/promote_by_tags.py` is active

---

### R2: Duplicate Script Variants

**Severity:** Medium
**Impact:** Confusion about which variant to use

**Description:**
Multiple variants exist for similar operations:
- `match_unknowns_to_epoch_2026_02_08.py` vs `_fast.py`
- `reassess_playlist_duration_unknowns.py` vs `_tokenless.py`
- `plan_fpcalc_*.py` (3 variants)

**Mitigation:**
- Archive superseded variants
- Document preferred variant in workflow docs
- Fast/tokenless variants are preferred

---

### R3: Misplaced Artifacts

**Severity:** Low
**Impact:** Repo clutter, unclear ownership

**Description:**
- `tools/flacs_inventory_20260202_191907.xlsx` (300MB) is in `tools/` not `artifacts/`
- `script.log` (empty) is in repo root

**Mitigation:**
- Move `flacs_inventory_*.xlsx` to `artifacts/`
- Delete empty `script.log`

---

### R4: Stale Configuration Files

**Severity:** Low
**Impact:** Confusion about active config method

**Description:**
Old config files remain in repo root:
- `config.toml` (superseded by `.env`)
- `config.example.toml` (superseded by `.env.example`)
- `config.example.yaml` (superseded by `.env.example`)

**Mitigation:**
- Delete stale config files
- `.env` is the canonical config method

---

### R5: Documentation Sprawl

**Severity:** Low
**Impact:** Difficulty finding authoritative docs

**Description:**
24 markdown files in `docs/`, many are completed phase/verification docs that are now reference-only. No single operator-focused README.

**Mitigation:**
- Archive completed phase docs to `docs/archive/`
- Create single-source-of-truth `docs/README_OPERATIONS.md`
- Keep only active policy docs in `docs/`

---

### R6: Pre-download Check Tool Needs Production Hardening

**Severity:** Medium
**Impact:** Pre-download workflow reliability

**Description:**
`tools/review/pre_download_check.py` exists but:
- Has hardcoded script path
- Not integrated with canonical CLI
- No confidence scoring

**Mitigation:**
- Enhance script with confidence scoring
- Remove hardcoded paths
- Add to canonical documentation

---

### R7: Tidal Token Dependency

**Severity:** Medium
**Impact:** Tidal extraction fails without valid token

**Description:**
`extract_tracklists_from_links.py` requires valid Tidal OAuth token for Tidal URLs. If token is missing/expired, Tidal tracks cannot be pre-checked.

**Mitigation:**
- Document token requirement
- `tagslut auth status` shows token status
- `tagslut auth refresh` refreshes tokens

---

### R8: Beatport Works Without Interactive Token (As Designed)

**Severity:** None (informational)
**Status:** CONFIRMED WORKING

**Description:**
Beatport extraction uses web scraping + BeatportProvider fallback. Does not require OAuth token flow for pre-download checks.

**Mitigation:**
None needed - this is the expected behavior.

---

## Mitigated Risks (Completed)

### M1: Legacy CLI Wrappers

**Status:** MITIGATED (Phase 5, Feb 9 2026)

All 8 legacy wrappers (`scan`, `recommend`, `apply`, `promote`, `quarantine`, `mgmt`, `metadata`, `recover`) have been retired from CLI surface. Code remains in `legacy/` for reference.

---

### M2: Command Surface Drift

**Status:** MITIGATED

- `docs/SURFACE_POLICY.md` defines canonical surface
- `docs/SCRIPT_SURFACE.md` maps all entry points
- `scripts/audit_repo_layout.py` validates compliance
- `scripts/check_cli_docs_consistency.py` validates doc sync

---

### M3: Path Hardcoding

**Status:** MITIGATED

All paths use environment variables via `dedupe/utils/env_paths.py`. No hardcoded `/Volumes/` paths in production code.

---

## Open Issues

| ID | Issue | Owner | Priority |
|----|-------|-------|----------|
| O1 | Archive obsolete scripts to tools/archive/ | This audit | High |
| O2 | Create docs/README_OPERATIONS.md | This audit | High |
| O3 | Enhance pre_download_check.py | This audit | High |
| O4 | Delete stale config files | This audit | Medium |
| O5 | Move misplaced artifacts | This audit | Medium |
| O6 | Archive completed phase docs | This audit | Low |
