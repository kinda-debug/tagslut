# Workflow Surface Map

**Generated:** 2026-02-14
**Audit Version:** 2.0

## Canonical CLI Surface

All operations use these 7 command groups:

| Command | Subcommands | Purpose |
|---------|-------------|---------|
| `tagslut intake` | `run`, `prefilter` | Download/intake orchestration |
| `tagslut index` | `register`, `check`, `duration-check`, `duration-audit`, `set-duration-ref`, `enrich` | Library inventory & metadata |
| `tagslut decide` | `profiles`, `plan` | Policy-based planning |
| `tagslut execute` | `move-plan`, `quarantine-plan`, `promote-tags` | Execute plans |
| `tagslut verify` | `duration`, `recovery`, `parity`, `receipts` | Validate operations |
| `tagslut report` | `m3u`, `duration`, `recovery`, `plan-summary` | Generate reports |
| `tagslut auth` | `status`, `init`, `refresh`, `login` | Provider authentication |

## Download Wrappers by Source

### Beatport (source=bpdl)

| Wrapper | Purpose | Auto-register |
|---------|---------|---------------|
| `tools/get <beatport-url>` | Routes to get-sync | No (manual) |
| `tools/get-sync <beatport-url>` | Download missing + M3U | No (manual) |
| `tools/get-report <beatport-url>` | Report only | N/A |
| `tools/get --raw-bpdl <url>` | Direct BeatportDL | No (manual) |

**Post-download registration:**
```bash
tagslut index register /path/to/downloads --source bpdl --execute
```

### Tidal (source=tidal)

| Wrapper | Purpose | Auto-register |
|---------|---------|---------------|
| `tools/get <tidal-url>` | Routes to tiddl | No (manual) |
| `tools/tiddl <url>` | Direct TIDDL | No (manual) |

**Post-download registration:**
```bash
tagslut index register ~/Downloads/tiddl/ --source tidal --execute
```

### Deezer (source=deezer)

| Wrapper | Purpose | Auto-register |
|---------|---------|---------------|
| `tools/get <deezer-url>` | Routes to deemix | **YES** |
| `tools/deemix <url>` | Direct deemix | **YES** |

**Note:** Deezer wrapper auto-registers with `--source deezer` after download.

## Pre-Download Check Flow

| Tool | Purpose |
|------|---------|
| `tools/get-auto <url>` | Check against DB + download only missing |
| `tools/review/pre_download_check.py` | Core precheck logic |

**Workflow:**
```bash
# Option 1: Automatic precheck + download
tools/get-auto https://www.beatport.com/release/...

# Option 2: Manual precheck
python tools/review/pre_download_check.py \
  --input links.txt \
  --db ~/Projects/dedupe_db/EPOCH_2026-02-10_RELINK/music.db \
  --out-dir output/precheck

# Then download from keep file
while read url; do tools/get "$url"; done < output/precheck/precheck_keep_track_urls_*.txt
```

## Source Registration Matrix

| Download Source | Wrapper | --source Flag | Auto-register |
|-----------------|---------|---------------|---------------|
| Beatport | get-sync, get | bpdl | No |
| Tidal | tiddl, get | tidal | No |
| Deezer | deemix, get | deezer | **Yes** |
| Qobuz | N/A | N/A | **Not in active workflows** |

## Operational Scripts (tools/review/)

### Move/Promotion

| Script | Purpose |
|--------|---------|
| `promote_by_tags.py` | Move files using tag-based rules |
| `move_from_plan.py` | Execute JSON move plans |
| `quarantine_from_plan.py` | Execute quarantine operations |
| `promote_replace_merge.py` | Replace/merge promotion |
| `promote_isrc_fp_dupes.py` | ISRC/FP dupe promotion |

### Planning

| Script | Purpose |
|--------|---------|
| `plan_fpcalc_bulk_promote_and_stash.py` | FP bulk planning |
| `plan_fpcalc_crossroot_promote_and_stash.py` | FP crossroot planning |
| `plan_fpcalc_promote_unique_to_final_library.py` | FP unique promotion |
| `plan_promote_to_final_library.py` | Final library planning |
| `plan_summary.py` | Plan summary |

### Reporting

| Script | Purpose |
|--------|---------|
| `pre_download_check.py` | Pre-download DB check |
| `export_track_table.py` | Export to spreadsheet |
| `fingerprint_report.py` | FP analysis |
| `audio_analysis_report.py` | Audio health |
| `isrc_dupes_report.py` | ISRC duplicates |
| `audio_dupe_audit.py` | Audio duplication |

### Metadata

| Script | Purpose |
|--------|---------|
| `match_unknowns_to_epoch_2026_02_08_fast.py` | Match unknowns |
| `backfill_metadata_from_epoch_2026_02_08.py` | Backfill metadata |
| `canonize_tags.py` | Canonicalize tags |
| `hoard_tags.py` | Collect tags |
| `enrich_library_from_hoard_fingerprint.py` | FP enrichment |
| `onetagger_workflow.py` | OneTagger batch |

### Utilities

| Script | Purpose |
|--------|---------|
| `duration_check_from_list.py` | Duration check |
| `check_integrity_update_db.py` | Integrity + DB |
| `scan_with_trust.py` | Trust zone scan |
| `dump_file_tags.py` | Extract tags |
| `music_tags_scan_and_strip.py` | Scan/strip |

## Infrastructure Scripts (scripts/)

| Script | Purpose |
|--------|---------|
| `extract_tracklists_from_links.py` | Extract URLs to tracks |
| `audit_repo_layout.py` | Validate repo |
| `check_cli_docs_consistency.py` | Validate docs |
| `lint_policy_profiles.py` | Lint policies |
| `validate_v3_dual_write_parity.py` | V3 parity |
| `backfill_v3_*.py` | V3 backfill (2 scripts) |
| `bootstrap_*.py` | Bootstrap (3 scripts) |
| `reassess_*.py` | Reassess (2 scripts) |

## DO NOT USE (Retired)

| Retired | Replacement |
|---------|-------------|
| `dedupe scan` | `tagslut index ...` |
| `dedupe recommend` | `tagslut decide plan ...` |
| `dedupe apply` | `tagslut execute move-plan ...` |
| `dedupe promote` | `tagslut execute promote-tags ...` |
| `dedupe quarantine` | `tagslut execute quarantine-plan ...` |
| `dedupe mgmt` | `tagslut index + report m3u` |
| `dedupe metadata` | `tagslut auth + index enrich` |
| `dedupe recover` | `tagslut verify + report recovery` |

## File Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        URL INPUT                                │
│  (Beatport, Tidal, Deezer links)                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    tools/get-auto                               │
│  (optional: precheck + download only missing)                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
     ┌─────────────────┐           ┌─────────────────┐
     │ pre_download_   │           │    Proceed      │
     │ check.py        │           │  to download    │
     └────────┬────────┘           └────────┬────────┘
              │                             │
              ▼                             │
     ┌─────────────────┐                    │
     │ keep_urls.txt   │◄───────────────────┘
     └────────┬────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        tools/get                                │
│  Routes by domain:                                              │
│  - beatport.com → tools/get-sync → bpdl                        │
│  - tidal.com → tools/tiddl → tiddl                             │
│  - deezer.com → tools/deemix → deemix (+ auto-register)        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                 tagslut index register                          │
│  --source [bpdl|tidal|deezer]                                   │
│  (automatic for deezer, manual for others)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    tagslut decide plan                          │
│  Generate execution plan from policy                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  tagslut execute move-plan                      │
│  Execute moves with receipts                                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    tagslut verify                               │
│  duration, recovery, receipts, parity                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Final Library                              │
└─────────────────────────────────────────────────────────────────┘
```
