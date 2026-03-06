# Archived: DJ Track Classification Script v2 Changelog

# DJ Track Classification Changelog

## v2 (2026-02-27): Hybrid Genre Fallback + Softer Scoring

### Overview
Fixed circular bias in v1 by implementing genre fallback (sparse → rich) and softer penalty scoring. **Results are dataset-specific** (your library: club 0.7%→37%, remove 75%→26%; adjust thresholds if deploying to other catalogs).

### What Changed
- **Genre fallback**: Resolve sparse `canonical_sub_genre` (312 values) to rich `canonical_genre` (22K+ values)
- **Soft scoring**: Only explicit ANTI_DJ keywords (ambient, classical, etc.) penalized; missing/unknown genres = 0 (not -2)
- **Non-destructive**: New `classification_v2` column created; `classification` (v1) preserved for audit trail
- **Regression guards**: Automated tripwires monitor remove% and genre_blank% for future breaks

### Results (Your Dataset)
- **Distribution**: club 0.7% → 37%, bar 24% → 37%, remove 75% → 26%
- **Genre coverage**: 1.3% → 94.1% (CSV now shows readable genres)
- **Divergence**: 71.4% of 23,460 tracks reclassified (old sparse penalty removed)
- **Directional risk**: Validated; 3,352 remove→club flips all have legitimate genres (House, Electronica, Dance/Pop)

### How to Deploy

#### 1. Preview (read-only, safe to test)
```bash
python3 classify_tracks_sqlite.py \
  --db /path/to/music.db \
  --table files \
  --no-db-update \
  --csv-out /tmp/test_v2.csv
```
Review output CSV and playlists. If satisfied, proceed to step 2.

#### 2. Write classification_v2 to DB
```bash
python3 classify_tracks_sqlite.py \
  --db /path/to/music.db \
  --table files
```
This creates `classification_v2` column and populates 23,460 rows. Idempotent; safe to rerun.

#### 3. Promote v2 to Primary (When Ready)
**⚠️ IMPORTANT: SQLite version requirement**

Check your SQLite version:
```bash
sqlite3 /path/to/music.db "SELECT sqlite_version();"
```

**Option A: SQLite ≥ 3.25 (RECOMMENDED)**
```bash
sqlite3 /path/to/music.db << 'SQL'
BEGIN;
ALTER TABLE files RENAME COLUMN classification TO classification_v1;
ALTER TABLE files RENAME COLUMN classification_v2 TO classification;
COMMIT;
SQL
```
This atomically swaps v2 → primary and archives v1 as backup. RENAME COLUMN updates all indexes and views automatically.

**Option B: SQLite < 3.25 (Classic Migration)**
If RENAME COLUMN fails, use the manual approach:
```bash
# Backup first
cp /path/to/music.db /path/to/music.db.backup

sqlite3 /path/to/music.db << 'SQL'
BEGIN;
-- Create new table with v2 as primary classification
CREATE TABLE files_new AS SELECT * FROM files;
ALTER TABLE files_new RENAME TO files_old;

-- Recreate files table with v2 promoted
CREATE TABLE files AS SELECT
  * REPLACE (classification_v2 as classification)
  FROM files_old;

-- Verify row count matches
SELECT COUNT(*) FROM files;
SELECT COUNT(*) FROM files_old;

DROP TABLE files_old;
COMMIT;
SQL
```
(Or simply keep v2 as parallel indefinitely if promotion feels risky.)

### Rollback (If Needed)
**If ≥ 3.25:**
```bash
sqlite3 /path/to/music.db << 'SQL'
BEGIN;
ALTER TABLE files RENAME COLUMN classification TO classification_v2;
ALTER TABLE files RENAME COLUMN classification_v1 TO classification;
COMMIT;
SQL
```

**If < 3.25 or manual migration used:**
```bash
cp /path/to/music.db.backup /path/to/music.db
```

### Verification
After any migration step:
```bash
sqlite3 /path/to/music.db << 'SQL'
-- Check distribution
SELECT classification, COUNT(*) FROM files GROUP BY classification;

-- Check genre coverage
SELECT
  ROUND(100.0 * SUM(CASE WHEN TRIM(genre)='' THEN 1 ELSE 0 END) / COUNT(*), 1) as genre_blank_pct
FROM (SELECT genre FROM files LIMIT 100);
SQL
```

### Regression Tripwires
The script includes automated checks that fail loudly if:
- `remove%` exceeds 80% (suggests fallback didn't work)
- `genre_blank%` exceeds 20% (suggests enrichment failed)

If either tripwire fires, check:
1. Is `canonical_genre` column present and populated?
2. Did migration skip rows (check stdout for "skipped X rows")?
3. Are there NULL mismatches? (Check stderr for "ERROR: N rows have NULL classification_v2")

### Known Limitations
- ANTI_DJ_KEYWORDS (ambient, classical) affects 0.8%–1.4% of your library. If these are DJ-usable in your sets, consider removing from list or narrowing match criteria (v3 refinement).
- Energy bucketing uses genre keywords only; could be improved with ML clustering (v3+).
- No A/B testing framework yet for comparing old/new classifications (future improvement).

### Files
- Script: `scripts/classify_tracks_sqlite.py`
- Patch (for provenance): `PATCH_v2.patch`
- Audit: `.claude/audit_corrections_summary.md`

### Next Steps
1. ✅ Deploy v2 classification to DB (read-only first)
2. ✅ Review playlists for quality (club_playlist.m3u8, etc.)
3. ⏳ Promote v2 → primary when confident
4. ⏳ Update DJ curation pipelines to use new classifications
5. ⏳ Gather listening feedback and refine thresholds if needed (v3)
