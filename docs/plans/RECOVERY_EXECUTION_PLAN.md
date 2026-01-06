# Library Recovery: Execution Plan

## Database State (Jan 6, 2026)

**File:** `artifacts/db/music.db` (352 MB) | **Table:** `files` | **Rows:** 65,998

### Inventory by Library/Zone

| Library | Zone | Total | NOT_SCANNED | Scanned | Corrupt | Size (GB) |
|---------|------|------:|------------:|--------:|--------:|----------:|
| bad | suspect | 40,436 | 21,515 | 18,921 | 17 | 1,722.1 |
| recovery | accepted | 16,286 | 7,515 | 8,771 | 0 | 718.2 |
| commune | accepted | 5,804 | 3,641 | 2,163 | 9 | 248.4 |
| vault | suspect | 2,463 | 1,725 | 738 | 2 | 102.5 |
| commune | staging | 858 | 798 | 60 | 0 | 38.3 |
| recovery | (none) | 151 | 0 | 151 | 0 | — |
| **TOTAL** | | **65,998** | **35,194** | **30,804** | **28** | **~2.83 TB** |

### Scan Progress

- **Scanned:** 30,804 (46.7%)
- **NOT_SCANNED:** 35,194 (53.3%) ← **blocking**

### Duplicate Analysis (scanned only)

- Unique checksums: 10,702
- Total scanned: 30,804
- **Duplicates: 20,102 (65.3%)**

### Audio Quality

| Bit Depth | Count | Sample Rate | Count |
|----------:|------:|------------:|------:|
| 16-bit | 40,244 | 44.1 kHz | 53,493 |
| 24-bit | 25,717 | 96 kHz | 6,647 |
| 32-bit | 8 | 48 kHz | 3,804 |
| | | 192 kHz | 1,616 |

### Physical Volume Mapping

| Path Prefix | Files | Notes |
|-------------|------:|-------|
| `/Volumes/bad/` | 40,436 | Bad volume (library=bad) |
| `/Volumes/RECOVERY_TARGET/` | 16,437 | Recovery source |
| `/Volumes/COMMUNE/` | 6,662 | Canonical destination |
| `/Volumes/Vault/` | 2,463 | Older material |

### Critical Issues

1. **53% NOT_SCANNED** - Must complete before matching
2. **65% duplicates** among scanned files
3. **0% fingerprinted** - No AcoustID data
4. **28 corrupt files** - 17 on bad, 9 on commune, 2 on vault

---

## STEP 1: Complete Scanning

**Blocking:** 35,194 files need checksums.

### 1a. bad/suspect (21,515)

```bash
python3 scripts/scan_not_scanned.py bad suspect 5000
```

### 1b. recovery/accepted (7,515)

```bash
python3 scripts/scan_not_scanned.py recovery accepted 5000
```

### 1c. commune/accepted (3,641)

```bash
python3 scripts/scan_not_scanned.py commune accepted 5000
```

### 1d. vault/suspect (1,725)

```bash
python3 scripts/scan_not_scanned.py vault suspect 5000
```

### 1e. commune/staging (798)

```bash
python3 scripts/scan_not_scanned.py commune staging 5000
```

### 1f. Verify complete

```bash
python3 -c "import sqlite3; conn = sqlite3.connect('artifacts/db/music.db'); cur = conn.cursor(); cur.execute(\"SELECT COUNT(*) FROM files WHERE checksum LIKE 'NOT_SCANNED%'\"); print(f'NOT_SCANNED remaining: {cur.fetchone()[0]}'); conn.close()"
```

**Expected:** `NOT_SCANNED remaining: 0`

---

## STEP 2: Check canonical library

```bash
python3 -c "import sqlite3; conn = sqlite3.connect('artifacts/db/music.db'); cur = conn.cursor(); cur.execute(\"SELECT COUNT(*) FROM files WHERE library='commune' AND zone='accepted' AND checksum NOT LIKE 'NOT_SCANNED%'\"); print(f'Canonical library files: {cur.fetchone()[0]}'); conn.close()"
```

---

## STEP 3: Match bad files vs canonical

```bash
python3 -m dedupe.matcher \
  --db artifacts/db/music.db \
  --source-library bad \
  --source-zone suspect \
  --canonical-library commune \
  --canonical-zone accepted \
  --threshold 0.55 \
  --output artifacts/reports/bad_vs_canonical_matches.csv
```

**What this does:**
- Compares all bad/suspect files against commune/accepted (canonical)
- Scores matches using filename (60%), size (25%), duration (15%)
- Classifications: exact / truncated / potential_upgrade / ambiguous / orphan
- Writes CSV with match scores and recommendations

**Time estimate:** 5-10 minutes for 40k files

**Output file:** `artifacts/reports/bad_vs_canonical_matches.csv`

---

## STEP 3a: Match vault files vs canonical

```bash
python3 -m dedupe.matcher \
  --db artifacts/db/music.db \
  --source-library vault \
  --source-zone suspect \
  --canonical-library commune \
  --canonical-zone accepted \
  --threshold 0.55 \
  --output artifacts/reports/vault_vs_canonical_matches.csv
```

---

## STEP 3b: Match recovery files vs canonical

```bash
python3 -m dedupe.matcher \
  --db artifacts/db/music.db \
  --source-library recovery \
  --source-zone accepted \
  --canonical-library commune \
  --canonical-zone accepted \
  --threshold 0.55 \
  --output artifacts/reports/recovery_vs_canonical_matches.csv
```

---

## STEP 4: Review match results

```bash
python3 -c "import csv; matches = list(csv.DictReader(open('artifacts/reports/bad_vs_canonical_matches.csv'))); print(f'Total matches: {len(matches)}'); from collections import Counter; counts = Counter(m['classification'] for m in matches); print('\nBy classification:'); [print(f'  {k}: {v}') for k, v in sorted(counts.items())]"
```

**This shows:** How many exact matches, upgrades, ambiguous cases, orphans, etc.

**What to look for:**
- High `exact` count = good (duplicates found in canonical)
- High `orphan` count = files unique to bad volume (worth keeping?)
- High `ambiguous` = may need fingerprinting for confidence

---

## STEP 5: Generate decision plan

**COMMAND:**

```bash
python3 -m dedupe.decide.plan \
  --db artifacts/db/music.db \
  --matches artifacts/reports/bad_vs_canonical_matches.csv \
  --output artifacts/plans/recovery_decision.json \
  --zone-priority accepted,staging,suspect,quarantine
```

**What this does:**
- Reads match CSV from Step 3
- Applies decision rules: integrity > zone > quality
- Outputs JSON plan with KEEP/DROP/REVIEW actions

**Decision logic:**
- `exact` match + canonical is valid FLAC = DROP bad file (duplicate)
- `potential_upgrade` + bad file is better quality = KEEP bad, drop canonical
- `ambiguous` or identity conflict = REVIEW (manual decision)
- `orphan` = KEEP (unique to bad volume)

**Output file:** `artifacts/plans/recovery_decision.json`

---

## STEP 6: Review decision summary

**COMMAND:**

```bash
python3 -c "import json; plan = json.load(open('artifacts/plans/recovery_decision.json')); actions = [f['action'] for f in plan['files']]; from collections import Counter; counts = Counter(actions); print('\nDecision summary:'); [print(f'  {k}: {v}') for k, v in sorted(counts.items())]; print(f'\nTotal files: {len(plan[\"files\"])}')"
```

**This shows:** How many KEEP / DROP / REVIEW decisions were made.

**Next action depends on output:**
- Many REVIEW? → Run Step 7 (fingerprinting) for ambiguous cases
- Few REVIEW? → Skip to Step 8 (verify winners)

---

## STEP 7: [OPTIONAL] Fingerprint ambiguous cases for higher confidence

**Only run if Step 6 shows many REVIEW cases.**

**COMMAND:**

```bash
python3 tools/integrity/fingerprint.py \
  --db artifacts/db/music.db \
  --filter "library='bad' AND zone='suspect'" \
  --workers 8
```

**What this does:**
- Runs `fpcalc` on bad volume files
- Generates Chromaprint acoustic fingerprints
- Adds fingerprints to database

**Time estimate:** ~2-4 hours for 40k files (parallelized)

**After fingerprinting:** Re-run Step 3 (matching) with fingerprints enabled for better acoustic similarity scoring.

---

## STEP 8: Verify integrity of KEEP winners

**COMMAND:**

```bash
python3 tools/integrity/verify_winners.py \
  --db artifacts/db/music.db \
  --plan artifacts/plans/recovery_decision.json \
  --workers 8 \
  --update-db
```

**What this does:**
- Runs `flac -t` ONLY on files marked KEEP
- Updates `flac_ok` and `integrity_state` in database
- Moves corrupt winners to REVIEW status

**Time estimate:** ~5-10 minutes (only verifying keepers, not all files)

**Why this matters:** Don't relocate corrupt files to canonical library.

---

## STEP 9: Review REVIEW cases (manual decision required)

**COMMAND:**

```bash
python3 -c "import json; plan = json.load(open('artifacts/plans/recovery_decision.json')); review = [f for f in plan['files'] if f['action'] == 'REVIEW']; print(f'Files needing manual review: {len(review)}'); print('\nFirst 10:'); [print(f'{i+1}. {r[\"path\"]} - Reason: {r[\"reason\"]}') for i, r in enumerate(review[:10])]"
```

**This shows:** Which files need human decision and why.

**Manual process:**
- Listen to files if needed
- Check metadata mismatches
- Update plan JSON: change `REVIEW` → `KEEP` or `DROP`
- Save modified plan

---

## STEP 10: Execute relocation plan (DRY RUN FIRST)

**COMMAND (DRY RUN):**

```bash
python3 -m dedupe.hrm_relocation \
  --db artifacts/db/music.db \
  --plan artifacts/plans/recovery_decision.json \
  --dest /Volumes/COMMUNE/20_ACCEPTED \
  --manifest artifacts/logs/recovery_moves_manifest.tsv \
  --dry-run
```

**What this does:**
- Shows what WOULD be moved (doesn't actually move)
- Generates manifest TSV preview
- Checks for conflicts (duplicate destinations)

**Review manifest:** Open `artifacts/logs/recovery_moves_manifest.tsv` and verify moves look correct.

---

## STEP 11: Execute relocation (FOR REAL)

**COMMAND (REAL EXECUTION):**

```bash
python3 -m dedupe.hrm_relocation \
  --db artifacts/db/music.db \
  --plan artifacts/plans/recovery_decision.json \
  --dest /Volumes/COMMUNE/20_ACCEPTED \
  --manifest artifacts/logs/recovery_moves_manifest.tsv \
  --verify-checksums
```

**What this does:**
- Moves KEEP files to `Artist/(YYYY) Album/Track. Title.flac` structure
- Verifies checksums before/after move
- Logs all moves to manifest TSV
- Updates database with new paths

**Time estimate:** Depends on file count and disk speed (5-30 minutes)

**Rollback:** If needed, use manifest to reverse moves.

---

## STEP 12: Archive DROP files

**COMMAND:**

```bash
python3 -c "import json; plan = json.load(open('artifacts/plans/recovery_decision.json')); drops = [f['path'] for f in plan['files'] if f['action'] == 'DROP']; print(f'Files to archive: {len(drops)}'); with open('artifacts/tmp/files_to_archive.txt', 'w') as out: out.write('\n'.join(drops)); print('Written to: artifacts/tmp/files_to_archive.txt')"
```

**Then:**

```bash
mkdir -p /Volumes/COMMUNE/90_REJECTED/bad_volume_duplicates
rsync -av --files-from=artifacts/tmp/files_to_archive.txt / /Volumes/COMMUNE/90_REJECTED/bad_volume_duplicates/
```

**What this does:**
- Moves DROP files (duplicates, lower quality) to rejection archive
- Preserves directory structure
- Keeps files for potential future review

---

## STEP 13: Update canonical library index

**COMMAND:**

```bash
python3 -m dedupe.cli scan-library \
  --root /Volumes/COMMUNE/20_ACCEPTED \
  --db artifacts/db/music.db \
  --library commune \
  --zone accepted \
  --incremental \
  --progress
```

**What this does:**
- Rescans canonical library to pick up newly relocated files
- Updates database with final state
- Verifies all moved files are in correct locations

---

## SUCCESS METRICS

```bash
python3 -c "import sqlite3; conn = sqlite3.connect('artifacts/db/music.db'); cur = conn.cursor(); cur.execute(\"SELECT library, zone, COUNT(*) FROM files WHERE flac_ok=1 GROUP BY library, zone\"); print('\\n=== VERIFIED GOOD FILES ==='); [print(f'{row[0]}/{row[1]}: {row[2]} files') for row in cur.fetchall()]; conn.close()"
```

**Recovery complete when:**
- NOT_SCANNED = 0
- All KEEP files relocated
- All DROP files archived
- Canonical library rescanned

---

## Schema Reference

| Column | Type | Description |
|--------|------|-------------|
| `path` | TEXT | Primary key - absolute path |
| `library` | TEXT | bad/commune/recovery/vault |
| `zone` | TEXT | accepted/staging/suspect |
| `checksum` | TEXT | STREAMINFO MD5 or NOT_SCANNED_* |
| `duration` | REAL | Seconds |
| `bit_depth` | INTEGER | 16/24/32 |
| `sample_rate` | INTEGER | Hz |
| `size` | INTEGER | Bytes |
| `metadata_json` | TEXT | Tags JSON |
| `flac_ok` | INTEGER | 1=valid, 0=corrupt |
| `integrity_state` | TEXT | valid/corrupt |
| `acoustid` | TEXT | Fingerprint (empty) |
