# Using --paths-from-file for Targeted Verification

## Problem

You have 16,000 files scanned. You want to verify integrity on **specific files only** without re-scanning everything.

## Solution

Use `--paths-from-file` to target exact files.

---

## Example: Verify only failed files

```bash
# 1. Extract paths of failed files
sqlite3 "$DEDUPE_DB" \
  "SELECT path FROM files WHERE integrity_state = 'corrupt' OR flac_ok = 0" \
  > failed_paths.txt

# 2. Run integrity check ONLY on those files
python3 tools/integrity/scan.py \
  --paths-from-file failed_paths.txt \
  --db "$DEDUPE_DB" \
  --check-integrity \
  --recheck \
  --verbose
```

**Result:** Verifies ~20 files instead of 16,000.

---

## Example: Verify a specific album

```bash
# Create a file with paths
cat > verify_these.txt <<EOF
/Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY/Artist/(2020) Album/01. Track.flac
/Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY/Artist/(2020) Album/02. Track.flac
EOF

# Verify just those
python3 tools/integrity/scan.py \
  --paths-from-file verify_these.txt \
  --db "$DEDUPE_DB" \
  --check-integrity \
  --verbose
```

---

## Example: Re-verify all suspect zone files

```bash
# Extract all suspect zone paths
sqlite3 "$DEDUPE_DB" \
  "SELECT path FROM files WHERE zone = 'suspect'" \
  > suspect_paths.txt

# Run full verification (hash + integrity)
python3 tools/integrity/scan.py \
  --paths-from-file suspect_paths.txt \
  --db "$DEDUPE_DB" \
  --check-integrity \
  --check-hash \
  --recheck \
  --progress \
  --verbose
```

---

## Rules

1. **One path per line** in the file
2. **Absolute paths** recommended
3. **--paths-from-file excludes LIBRARY_PATH** — you can't use both
4. **Combines with all flags**: `--check-integrity`, `--check-hash`, `--recheck`, etc.

---

## Why this exists

The original design had no way to say:

> "Only verify files I care about"

Every integrity check was global.

Now you can:
- Verify only failed files
- Verify only files from suspect sources
- Verify a manual list
- Verify based on DB queries

**This is forensic work, not bulk work.**
