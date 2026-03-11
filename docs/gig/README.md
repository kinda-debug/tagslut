# Gig Preparation Workflow

This directory contains the complete workflow for preparing a gig using the tagslut pool-wizard.

## Quick Start

For the March 13, 2026 gig:

```bash
# 1. Set up your environment variables (add to ~/.bashrc or ~/.zshrc)
export TAGSLUT_DB="/path/to/your/music.db"
export MASTER_LIBRARY="/path/to/your/master/library"
export DJ_LIBRARY="/path/to/your/dj/cache"  # optional
export VOLUME_WORK="/path/to/work/volume"

# 2. Create the gig directory structure
mkdir -p "$VOLUME_WORK/gig_runs/gig_2026_03_13"

# 3. Copy templates
cp docs/gig/templates/SCOPE_FREEZE.txt "$VOLUME_WORK/gig_runs/gig_2026_03_13/"
cp docs/gig/templates/profile_initial.json "$VOLUME_WORK/gig_runs/gig_2026_03_13/profile.json"
cp docs/gig/templates/cheat_sheet.txt "$VOLUME_WORK/gig_runs/gig_2026_03_13/"

# 4. Run the workflow scripts in order
cd /path/to/tagslut/repo

# Phase 0: Verify environment (T-36 to T-34)
bash scripts/gig/00_verify_environment.sh

# Phase 1: Plan mode (T-34 to T-30)
# Edit profile.json if needed, then:
bash scripts/gig/01_plan_mode.sh
# Inspect artifacts, tighten profile if needed, rerun until satisfied

# Phase 2: Execute (T-24 to T-20)
bash scripts/gig/02_execute.sh

# Phase 3: Validate (T-24 to T-20)
bash scripts/gig/03_validate_pool.sh
# After validation passes, manually create POOL_VERIFIED.txt

# Phase 4: Import to Rekordbox and curate (T-20 to T-8)
# Import the pool/ directory into Rekordbox
# Build intent playlists, then time-of-night playlists
# Fill out cheat_sheet.txt

# Phase 5: Export USBs (T-8 to T-4)
# Export and verify USB A, then USB B

# Phase 6: Freeze (T-4 to gig)
# No more changes
```

## File Structure

```
docs/gig/
├── README.md                          # This file
├── GIG_EXECUTION_PLAN_v3.3.md         # Complete execution plan
└── templates/
    ├── SCOPE_FREEZE.txt               # Scope freeze template
    ├── profile_initial.json           # Initial profile template
    └── cheat_sheet.txt                # Offline cheat sheet

scripts/gig/
├── 00_verify_environment.sh          # Phase 0: Environment checks
├── 01_plan_mode.sh                   # Phase 1: Dry run
├── 02_execute.sh                     # Phase 2: Execute pool build
└── 03_validate_pool.sh               # Phase 3: File validation
```

## Workflow Phases

### Phase 0: Environment Verification (T-36 to T-34)
- Verify all paths and environment variables
- Check CLI availability
- Confirm disk space
- **Script:** `00_verify_environment.sh`

### Phase 1: Plan Mode (T-34 to T-30)
- Run pool-wizard in plan mode (dry run)
- Inspect artifacts (cohort_health.json, selected.csv, plan.csv)
- Tighten profile one axis at a time if needed
- Rerun until pool shape is correct
- **Script:** `01_plan_mode.sh`

### Phase 2: Execute (T-24 to T-20)
- Run pool-wizard in execute mode
- Copy files to pool directory
- Verify file counts match
- **Script:** `02_execute.sh`

### Phase 3: Validate Pool (T-24 to T-20)
- Check for zero-byte files
- Check for truncated files
- Check for non-MP3 files
- Manual spot-check playback
- Create POOL_VERIFIED.txt
- **Script:** `03_validate_pool.sh`

### Phase 4: Rekordbox Curation (T-20 to T-8)
- Import pool/ into Rekordbox
- Analyze tracks
- Build 5 intent playlists:
  - 10 PRIME
  - 20 CLUB RESERVE
  - 30 BRIDGE
  - 40 FAMILIAR VOCALS
  - 99 EMERGENCY
- Build 7 time-of-night playlists:
  - 00 Warmup
  - 01 Builders
  - 02 Peak A
  - 03 Peak B
  - 04 Left Turns / Vocals / Classics
  - 05 Reset / Breath
  - 06 Closing
- Stress-test transitions
- Fill out cheat_sheet.txt

### Phase 5: USB Export (T-8 to T-4)
- Export USB A from Rekordbox
- Verify USB A completely
- Export USB B
- Verify USB B separately

### Phase 6: Freeze (T-4 to gig)
- No more changes
- Only microscopic fixes to broken items

## Key Decision Points

### Plan Mode → Execute
Do NOT proceed to execute unless:
- Selected count is 90-150 tracks
- Pool supports all 5 intent layers (PRIME, CLUB RESERVE, BRIDGE, FAMILIAR VOCALS, EMERGENCY)
- Role/genre distribution is healthy
- No suspicious cache_action or pool_action warnings
- Filenames are legible

### Execute → Rekordbox Import
Do NOT import into Rekordbox unless:
- Execute completed with failed=0
- File count matches selected count
- Validation script passed
- Manual spot-check passed
- POOL_VERIFIED.txt exists

### Rekordbox → USB Export
Do NOT export USBs unless:
- All 5 intent playlists exist
- All 7 time-of-night playlists exist
- Every playlist has 3+ openers and 3+ exits
- Social transitions tested (PRIME↔BRIDGE, EMERGENCY→recovery)
- cheat_sheet.txt filled out

## Troubleshooting

### "Selected count is 0"
- Profile is too restrictive
- Check cohort_health.json for what's available
- Loosen one filter at a time

### "Too many transcode operations"
- Profile requires FLAC sources but cache doesn't have MP3s ready
- Either:
  - Pre-transcode high-priority tracks
  - Accept the time cost
  - Switch to tracks that already have MP3 cache

### "Role distribution is degenerate"
- Most tracks have null dj_set_role
- Switch profile layout from "by_role" to "by_genre"

### "Pool is too large/small after execute"
- Do NOT rerun execute immediately
- Analyze what went wrong in plan mode
- Adjust profile
- Rerun plan mode
- Only execute again when confident

## References

- [GIG_EXECUTION_PLAN_v3.3.md](./GIG_EXECUTION_PLAN_v3.3.md) - Complete detailed plan
- [tagslut dj documentation](../dj/) - DJ subsystem docs
- [pool-wizard CLI command](../../tagslut/cli/commands/dj.py) - CLI entry point (`dj pool-wizard` subcommand)
- [pool-wizard implementation](../../tagslut/exec/dj_pool_wizard.py) - Core execution logic
