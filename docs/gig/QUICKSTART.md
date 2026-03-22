# Gig Prep Quick Reference

**For:** March 13, 2026 Bar Gig  
**Timeline:** 36 hours (T-36 to T-0)  
**Current time:** Check with `date`

## One-Page Checklist

### ☐ T-36 to T-34: Phase 0
```bash
bash scripts/gig/00_verify_environment.sh
```
- [ ] All paths accessible
- [ ] DB readable
- [ ] Disk space sufficient
- [ ] CLI working

### ☐ T-34 to T-30: Plan Mode
```bash
# Copy templates first
mkdir -p "$VOLUME_WORK/gig_runs/gig_2026_03_13"
cp docs/gig/templates/* "$VOLUME_WORK/gig_runs/gig_2026_03_13/"

# Run plan
bash scripts/gig/01_plan_mode.sh
```
- [ ] Inspect cohort_health.json
- [ ] Check selected.csv (90-150 tracks?)
- [ ] Review plan.csv (no red flags?)
- [ ] Pool supports PRIME/BRIDGE/CLUB RESERVE/FAMILIAR VOCALS/EMERGENCY?

### ☐ T-30 to T-24: Tightening (if needed)
- [ ] Edit profile.json (ONE axis at a time)
- [ ] Rerun plan mode
- [ ] Stop when pool shape is right

### ☐ T-24: CUTOFF - No more profile changes after this

### ☐ T-24 to T-20: Execute
```bash
bash scripts/gig/02_execute.sh
```
- [ ] Execute completed (failed=0)
- [ ] File count matches selected count

### ☐ T-24 to T-20: Validate
```bash
# Use the exact "Resolved execute run directory" printed by 02_execute.sh
RUN_DIR="/absolute/path/to/gig_2026_03_13_<timestamp>"
bash scripts/gig/03_validate_pool.sh "$RUN_DIR"
```
- [ ] No zero-byte files
- [ ] No truncated files
- [ ] No non-MP3 files
- [ ] Manual spot-check: 3-5 files play correctly
- [ ] Create `POOL_VERIFIED.txt` in run directory

### ☐ T-20 to T-14: Rekordbox Import & Analysis
- [ ] Import pool/ directory ONLY
- [ ] Analyze all tracks
- [ ] Fix critical beatgrids only
- [ ] Add hot cues on pressure tracks only

### ☐ T-14 to T-8: Build Playlists

**Intent playlists first:**
- [ ] 10 PRIME (35-60 tracks)
- [ ] 20 CLUB RESERVE (10-20 tracks)
- [ ] 30 BRIDGE (15-25 tracks)
- [ ] 40 FAMILIAR VOCALS (8-15 tracks)
- [ ] 99 EMERGENCY (10-20 tracks)

**Time-of-night playlists second:**
- [ ] 00 Warmup (15-25)
- [ ] 01 Builders (15-25)
- [ ] 02 Peak A (15-20)
- [ ] 03 Peak B (15-20)
- [ ] 04 Left Turns/Vocals/Classics (8-15)
- [ ] 05 Reset/Breath (8-12)
- [ ] 06 Closing (8-12)

**Stress-test:**
- [ ] PRIME → BRIDGE transition
- [ ] BRIDGE → PRIME transition
- [ ] EMERGENCY → recovery
- [ ] Every playlist has 3+ openers, 3+ exits

**Fill cheat sheet:**
- [ ] 10 openers
- [ ] 10 bridge tracks
- [ ] 10 peak weapons
- [ ] 10 emergency rescues

### ☐ T-8 to T-4: USB Export
- [ ] Export USB A
- [ ] Verify USB A (all playlists, random sample plays)
- [ ] Export USB B
- [ ] Verify USB B separately
- [ ] Record verification times in cheat sheet

### ☐ T-4 to T-0: FREEZE
- [ ] No more changes
- [ ] Both USBs in bag
- [ ] Cheat sheet printed or on phone
- [ ] Rekordbox backup noted

## Emergency Contacts

**Venue:** _____________  
**Sound tech:** _____________  
**Backup contact:** _____________  

## Critical Paths

**Run directory:**  
`<resolved_execute_run_dir>/`

**Pool location:**  
`<run_directory>/pool/`

**Profile:**  
`$VOLUME_WORK/gig_runs/gig_2026_03_13/profile.json`

**Cheat sheet:**  
`$VOLUME_WORK/gig_runs/gig_2026_03_13/cheat_sheet.txt`

## If Things Go Wrong

**"Selected count is 0"**  
→ Profile too tight. Check cohort_health.json. Loosen one filter.

**"Execute failed"**  
→ Check run.log. Do NOT rerun without understanding why.

**"Pool feels wrong after import"**  
→ Do NOT immediately regenerate. Use what you have. Rebuild is last resort.

**"USB won't export"**  
→ Check Rekordbox preferences. USB formatted FAT32? Enough space?

**"Forgot to fill cheat sheet"**  
→ Do it now from Rekordbox before leaving house.

## Definition of Done

✓ Both USBs verified  
✓ All 12 playlists exist (5 intent + 7 time-of-night)  
✓ Cheat sheet filled  
✓ POOL_VERIFIED.txt exists  
✓ 99 EMERGENCY can carry the night alone  
✓ Social transitions tested  
✓ You can name 10 openers, 10 bridges, 10 peaks, 10 emergencies from memory
