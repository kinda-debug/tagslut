# Implementation Status & Action Plan

**As of 2026-02-03**

---

## Current Status

### ✅ IMPLEMENTED & WORKING

1. **Core Scanning**
   - `dedupe scan` — Full integrity + hash scanning
   - Database schema for files, hashes, metadata
   - Zone auto-assignment
   - 158 files scanned in ~34 seconds ✓

2. **Deduplication Planning**
   - `dedupe recommend` — Generates duplicate groups (4226 groups found)
   - `dedupe apply` — Executes deduplication plan
   - Keeper selection logic (4-stage tie-breaker)

3. **Metadata Enrichment**
   - `dedupe metadata enrich` — Beatport, iTunes, Spotify, Tidal, Qobuz support
   - `dedupe enrich-file` — Single-file enrichment
   - Duration-based health validation

4. **Promotion & Organization**
   - `dedupe promote` — Moves files to canonical structure
   - `tools/review/promote_by_tags.py` — Alternative promotion with canon rules
   - `tools/review/canonize_tags.py` — Tag normalization

5. **Environment & Configuration**
   - `auto_env.py` — Auto-populates .env with latest EPOCH + zone volumes ✓
   - Zone configuration (`zones.yaml`) — Fully working ✓
   - .env template with EPOCH_PLACEHOLDER pattern ✓

6. **Utility Tools**
   - `dedupe show-zone` — Zone assignment verification
   - `tools/tiddl` — Tidal downloader wrapper
   - `tools/get` — Unified download entrypoint
   - `tools/review/hoard_tags.py` — Tag inventory collection

---

### ❌ NOT IMPLEMENTED YET

#### High Priority (Blocking Current Workflow)

1. **`dedupe mgmt` (Management Mode)**
   - NOT IMPLEMENTED
   - Supposed to:
     - Maintain central inventory of downloads
     - Check for duplicates BEFORE downloading
     - Track download sources (bpdl, tidal, qobuz, legacy)
     - Generate M3U playlists for Roon
   - Status: Stubs exist but no real implementation

2. **`dedupe recovery` (Recovery Mode)**
   - PARTIALLY IMPLEMENTED (old recover command exists)
   - Needs:
     - `--move` / `--no-move` flags with explicit semantics
     - `--rename-only` for normalization without relocation
     - Full JSON audit logging
     - Zone-aware moves
     - Verification before source deletion
   - Current: Old "recover" wizard exists but doesn't match spec

3. **Plan.json Visualization**
   - Current: 4226 empty objects (useless)
   - Needs: Better output format (CSV, summary stats, HTML dashboard)
   - Suggested: `plan_to_csv.py` or `plan_summary.py` script

#### Medium Priority (Needed for Full Workflow)

4. **BeatportDL Integration**
   - Vendored at `tools/beatportdl/bpdl/`
   - Needs:
     - Config file template with directory templates
     - Post-download registration hook
     - Wrapper script that integrates with `dedupe mgmt`

5. **M3U Generation**
   - Currently: Manual via `promote_by_tags.py`
   - Needs: Proper `dedupe mgmt --m3u` implementation
   - Should: Support --merge for single playlists

6. **Inventory Database Schema**
   - Current DB: Basic file metadata
   - Missing fields:
     - `download_source` (bpdl, qobuz, tidal, legacy)
     - `download_date` (ISO timestamp)
     - `original_path` (source location)
     - `canonical_path` (final destination)
     - `isrc` (for similarity matching)
     - `fingerprint` (chromaprint for duplicates)
     - `m3u_exported` (last export timestamp)
     - `mgmt_status` (new → checked → verified → moved)

7. **Audit Logging**
   - Needed: JSON/TSV logs for all operations
   - Current: No standardized logging
   - Should track: Downloads, moves, dedupes, metadata enrichments

#### Lower Priority (Nice-to-Have)

8. **DJ vs Non-DJ Separation**
   - No separate download paths or tagging convention
   - Could add: `--dj` flag to downloads, separate config profiles

9. **Similarity Matching**
   - Current: Only exact SHA256 matches
   - Could add: Fuzzy matching via ISRC, fingerprinting for near-dupes

10. **Periodic Refresh Automation**
    - No script for incremental rescanning
    - Could add: Cron-friendly batch mode

11. **Interactive Prompts**
    - `dedupe mgmt --check` should prompt when similar files exist
    - Currently: Silent, non-interactive

12. **Documentation**
    - REPORT.md — Partially updated
    - Workflow docs — Good but could be more detailed
    - BeatportDL config reference — In AGENTS.md, needs expansion

---

## Action Plan (Priority Order)

### Phase 1: Visualization & Immediate Fixes (This Week)

- [ ] **1.1** Create `plan_summary.py` to visualize plan.json
  - Output: Summary stats (# groups, total size, top duplicates)
  - Output: CSV of duplicate groups with recommendations
  - Goal: Make the 4226 groups useful and reviewable

- [ ] **1.2** Implement `dedupe mgmt` stub → basic version
  - `dedupe mgmt --check <path>` — Check if files exist in DB
  - `dedupe mgmt --register <path>` — Add to inventory
  - Goal: Basic inventory tracking (even if incomplete)

- [ ] **1.3** Update database schema with missing fields
  - Add: `download_source`, `download_date`, `original_path`, `mgmt_status`
  - Migration: `dedupe/migrations/add_mgmt_fields.py`
  - Goal: Support inventory tracking

### Phase 2: Management & Recovery Modes (Next 1-2 Weeks)

- [ ] **2.1** Implement `dedupe recovery` properly
  - `--move` / `--no-move` explicit semantics
  - `--rename-only` for in-place normalization
  - Full audit logging to JSON
  - Goal: Safe file operations with provenance tracking

- [ ] **2.2** Implement `dedupe mgmt` fully
  - `--m3u` M3U playlist generation
  - `--merge` for combining playlists
  - Interactive prompts for conflicts
  - Goal: Complete inventory management workflow

- [ ] **2.3** BeatportDL wrapper integration
  - Post-download hook: `dedupe mgmt --source bpdl --register <path>`
  - Config template: `tools/beatportdl/bpdl/beatportdl-config.yml`
  - Goal: Seamless download → inventory → M3U pipeline

### Phase 3: Polish & Automation (Later)

- [ ] **3.1** Interactive CLI improvements
  - Prompts for similar files
  - Waiver system for confidence thresholds
  - Goal: User-friendly deduplication workflow

- [ ] **3.2** Automated job scheduling
  - Cron-friendly batch modes
  - Periodic rescanning
  - Goal: Hands-off incremental updates

- [ ] **3.3** DJ vs Non-DJ separation
  - Config profile for DJ material
  - Separate download paths / tagging
  - Goal: Zero-error DJ track handling

---

## Immediate Next Steps (Today)

1. **Create plan visualization** (`plan_summary.py`)
   ```bash
   python tools/review/plan_summary.py plan.json --output plan_summary.csv
   ```

2. **Review the 4226 duplicate groups** in CSV format

3. **Implement basic `dedupe mgmt`** with `--check` and `--register`

4. **Test inventory registration** with a small subset

5. **Document the workflow** in WORKFLOW_PERSONAL.md

---

## Success Criteria

When complete, this workflow should work end-to-end:

```bash
# 1. Environment
python3 scripts/auto_env.py && source .env

# 2. Download new tracks
tools/get https://www.beatport.com/release/12345

# 3. Register to inventory
dedupe mgmt --source bpdl --register ~/Downloads/bpdl/

# 4. Check for duplicates
dedupe mgmt --check ~/Downloads/bpdl/

# 5. Generate playlist
dedupe mgmt --m3u ~/Downloads/bpdl/

# 6. Verify in Roon (external)

# 7. Move to canonical library
dedupe recovery --move ~/Downloads/bpdl/ --zone accepted

# 8. Cleanup (manual for safety)
rm -rf ~/Downloads/bpdl/
```

---

## Tracking

- Last Updated: 2026-02-03
- Next Review: After Phase 1 completion
