# Dedupe System Complexity Audit
**Date:** January 19, 2026
**Purpose:** Identify complexity, redundancy, hardcoded paths, and simplification opportunities

---

## 🚨 CRITICAL ISSUES

### 1. Hardcoded Paths Everywhere (100+ instances)
**Problem:** Absolute paths are baked into scripts and docs, making the system fragile and non-portable.

**Examples:**
- `/Users/georgeskhawam/Projects/dedupe_db/EPOCH_20260119/music.db`
- `/Volumes/COMMUNE/M/Library`
- `/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/`

**Files Affected:**
- `tools/review/promote_by_tags.py`
- `tools/decide/apply.py` (has a hardcoded block preventing 'DROP' actions!)
- 20+ Markdown files.

---

### 2. Tool Sprawl & Fragmentation
**Problem:** 30+ standalone scripts in `tools/` often bypass the `dedupe` core package.

**Redundancy Examples:**
- **Recommendation logic**: `tools/decide/recommend.py` (JSON) vs `tools/review/plan_removals.py` (CSV) - both do similar work but output different formats.
- **Apply logic**: `tools/decide/apply.py` vs `tools/review/apply_removals.py`.
- **Scan logic**: `tools/integrity/scan.py` is the primary entry, but many "analysis" scripts implement their own database connections and queries.

---

### 3. Documentation Chaos (20+ files)
**Problem:** Multiple "authoritative" guides.
- `DEFINITIVE_WORKFLOW.md`
- `docs/OPERATOR_GUIDE.md`
- `docs/OPERATOR_RUNBOOK.md`
- `AI_AGENT_HANDOVER_REPORT.md`

Many paths in these docs are now outdated, leading to user confusion.

---

### 4. Split Core (dedupe vs dedupe_v2)
**Problem:** Development is split between the original `dedupe` package and a `dedupe_v2` subdirectory, leading to import confusion and duplicate utility functions (e.g., `zone_assignment.py` exists in both).

---

## 🗂️ TOOL CATEGORIZATION

| Category | Tools | Recommendation |
| :--- | :--- | :--- |
| **Consolidate** | `scan.py`, `recommend.py`, `plan_removals.py`, `apply.py`, `apply_removals.py` | Merge into a unified `dedupe` CLI with subcommands. |
| **Retain** | `promote_by_tags.py`, `doctor.py`, `import_roon.py` | Move to `dedupe.cli` namespace. |
| **Deprecate** | `auto_mark.py`, `prepare_enriched.py`, various `fast_ops` | Replace with standardized flags in the core CLI. |

---

## 🎯 MODERNIZATION ROADMAP

### Phase 1: Environment & Config (Immediate)
- [ ] Enforce use of `dedupe/utils/env_paths.py` in all scripts.
- [ ] Replace all `/Users/georgeskhawam/...` paths with variable expansion.
- [ ] Update `config.toml` to be the single source of truth for zone priorities.

### Phase 2: Documentation Consolidation
- [ ] Merge all workflows into a single `GUIDE.md`.
- [ ] Archive (move to `docs/archive/`) all handover and snapshot reports.

### Phase 3: Architectural Cleanup
- [ ] Merge `dedupe_v2` logic back into `dedupe`.
- [ ] Create a single entry point: `python -m dedupe`.
- [ ] Standardize on one "Plan" format (JSON or CSV) used by both recommenders and executors.

---

## 📈 SUCCESS METRICS (Target)
- **Hardcoded paths**: 0
- **Standalone scripts**: < 5 (replaced by 1 CLI)
- **Primary docs**: 3 (`README.md`, `GUIDE.md`, `CHANGELOG.md`)

---

## ⚠️ RISKS

1. **Breaking changes** - Users with existing workflows
2. **Migration complexity** - Lots of hardcoded paths to update
3. **Test coverage** - Need comprehensive tests before refactor
4. **Time investment** - Significant development effort

**Mitigation:**
- Phased rollout with deprecation warnings
- Automated migration tools
- Maintain backward compatibility for 6 months
- Comprehensive testing before each phase

---

**END OF AUDIT**
