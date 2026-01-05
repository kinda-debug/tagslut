# Fast Deduplication Workflow

**Goal**: Minimize expensive operations by using intelligent 3-phase hashing.

---

## Hashing Strategy (The Secret Sauce)

### Why You Still Need Hashing

Hashing gives you **content identity** independent of:
- filenames
- folders  
- tags
- Yate / Picard / past mistakes

Without a hash, you can only guess duplicates.  
With a hash, you **know**.

### The Problem: Full Hashing is Expensive

Full-file SHA-256:
- Reads every byte
- Slow on spinning disks  
- Redundant when many files are garbage anyway

### The Solution: 3-Phase Intelligent Hashing

---

## Phase 1: Fast Inventory (STREAMINFO MD5)

**Goal**: Build a global map of "what exists where"

**Hash used**: FLAC STREAMINFO MD5
- Already embedded in FLAC metadata block
- ~100x faster than full-file hash
- Identifies identical decoded audio

**What to collect**:
- ✅ `streaminfo_md5` (fast, embedded)
- ✅ `path`, `size`, `mtime`
- ✅ `duration`, `sample_rate`, `bit_depth` (from header)
- ❌ NO full-file cryptographic hash
- ❌ NO integrity decoding (`flac -t`)

**Clustering logic**:
If two files have:
- same STREAMINFO MD5
- same duration
- same sample rate / bit depth

They are **almost certainly identical audio**.

### Command:

```bash
DB=~/Projects/dedupe_db/music.db

# Fast scan with STREAMINFO MD5 (default)
python3 tools/integrity/scan.py \
  /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY \
  --db $DB \
  --library recovery \
  --zone accepted \
  --no-check-integrity \
  --incremental \
  --progress

# Older vault material
python3 tools/integrity/scan.py \
  /Volumes/Vault \
  --db $DB \
  --library vault \
  --zone suspect \
  --no-check-integrity \
  --incremental \
  --progress

# Known problematic sources
python3 tools/integrity/scan.py \
  /Volumes/bad \
  --db $DB \
  --library bad \
  --zone quarantine \
  --no-check-integrity \
  --incremental \
  --progress
```

**What this does:**
- Extracts metadata (duration, sample rate, bit depth, tags)
- Calculates SHA-256 checksums
- **Skips** `flac -t` verification (saves hours)
- Tags each file with library/zone

---

## Phase 2: Clustering & Decisions

**Goal**: Group likely duplicates

**Uses**:
- `streaminfo_md5`
- `duration`
- `sample_rate` / `bit_depth`
- `size` (sanity check)

**No integrity checks yet.**

Analyze the DB to find exact duplicates:

```bash
python3 tools/decide/recommend.py \
  --db $DB \
  --output plan.json
```

**Output:** JSON plan with duplicate groups and recommended actions.
Phase 3: Verify Winners Only

**Goal**: Ensure long-term safety

**Only for**:
- Chosen canonical files
- Maybe 1 backup per cluster

**Run**:
- `flac -t` (integrity check)
- Full cryptographic hash (`--check-hash`)

This turns a **16k-file integrity nightmare into a few hundred checks**.

###
**Decision rules (strict order):**
1. **Zone priority**: accepted > suspect > quarantine
2. **Audio quality**: Higher sample rate/bit depth preferred
3. **Provenance confidence**

(Integrity is not yet a factor because we haven't checked it.)

---

## Step 3: Extract Winner Paths

From the plan, extract only the files marked as `"action": "keep"`:

```bash
cat plan.json | \
  jq -r '.plan[].decisions[] | select(.action == "keep") | .path' \
  > winners.txt
```

---

## Step 4: Verify Winners Only

Now run integrity checks **only** on the winning candidates:

```bash
# Create a temporary library list for winners
while IFS= read -r path; do
  python3 tools/integrity/scan.py \
    "$path" \
    --db $DB \
    --check-integrity \
    --recheck
done < winners.txt
```

Or, if you have a distinct subset directory:

```bash
python3 tools/integrity/scan.py \
  /path/to/winners \
  --db $DB \
  --check-integrity \
  --recheck \
  --progress
```

**What this does:**
- Updates the DB with `flac_ok` and `integrity_state` columns
- Only verifies files you're likely to keep
- Dramatically reduces verification time

---

## Step 5: Re-Run Decision With Integrity Data

Now that winners have been verified, re-run the decision engine:

---

## Performance Comparison

**Traditional workflow** (verify everything + full hash):
- 50,000 files × 3s/file = ~42 hours

**Phase 1 only** (STREAMINFO MD5):
- 50,000 files × 0.1s/file = ~1.4 hours

**Phase 1 + Phase 3** (STREAMINFO + verify winners):
- Fast scan: 50,000 files × 0.1s/file = ~1.4 hours
- Dedup analysis: ~5 minutes
- Verify 5,000 winners × 3s/file = ~4.2 hours
- **Total: ~5.6 hours** (87% faster)

---

## Hash Strategy Summary

| Phase | Hash Type | Speed | Purpose |
|-------|-----------|-------|---------|
| Phase 1 | STREAMINFO MD5 | Fast (embedded) | Clustering duplicates |
| Phase 2 | (analysis only) | Instant | Decision-making |
| Phase 3 | SHA-256 + `flac -t` | Slow | Verify winners |

**Clear rule of thumb**:

| Question | Answer |
|----------|--------|
| Skip hashing entirely? | ❌ No |
| Skip integrity checks now? | ✅ Yes |
| Use lightweight hashing now? | ✅ Yes (STREAMINFO MD5) |
| Full hashes on everything? | ❌ No |
| Full hashes on winners? | ✅ Yes |

---

## Implementation Notes

The scanner automatically:
- Extracts STREAMINFO MD5 from FLAC metadata (no `--check-hash` needed)
- Stores checksum as `streaminfo:<hex>` in DB
- Only runs full-file SHA-256 when `--check-hash` is used (Phase 3)

You don't skip hashing — you **downgrade it intelligently**.

---

## Performance Guarante
## Performance Comparison

**Traditional workflow** (verify everything):
- 50,000 files × 2s/file = ~28 hours

**Fast workflow** (verify winners only):
- Fast scan: 50,000 files × 0.1s/file = ~1.4 hours
- Dedup analysis: ~5 minutes
- Verify 5,000 winners × 2s/file = ~2.8 hours
- **Total: ~4.2 hours** (85% faster)

---

## Notes

- `--incremental` allows you to resume scans if interrupted
- `--recheck` forces re-verification even if mtime/size unchanged
- Winners list can be manually curated before verification
- The final plan (`plan_verified.json`) is authoritative for next steps

---

## Next Steps

After verification:
- Promote winners to COMMUNE
- Generate "safe to delete" lists for losers
- Produce missing-album reacquisition manifests

See [SYSTEM_SPEC.md](SYSTEM_SPEC.md) for complete system documentation.
