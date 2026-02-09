# Metadata + Trust Scan Workflow (Start Over, Clean)

This is the **single, clean workflow** to start over from scratch when you **do not have a main library yet**.
It uses a **trust score before scanning**, lets **scan results override it**, then enables **metadata recovery**, **canonization**, and **structured promotion**.

---

## 0) Environment (always first)

```bash
cd /Users/georgeskhawam/Projects/dedupe
python3 scripts/auto_env.py   # refreshes .env with latest EPOCH_* DB
source .env
mkdir -p "$(dirname "$DEDUPE_DB")"
```

Sanity check:
```bash
echo "$DEDUPE_DB"
echo "$DEDUPE_ZONES_CONFIG"
```

---

## 1) Zones (required)

```bash
mkdir -p ~/.config/dedupe
cp config.example.yaml ~/.config/dedupe/zones.yaml
$EDITOR ~/.config/dedupe/zones.yaml
export DEDUPE_ZONES_CONFIG=~/.config/dedupe/zones.yaml
```

Verify:
```bash
dedupe show-zone /Volumes/DJSSD/DRPBX --zones-config ~/.config/dedupe/zones.yaml
```

---

## 2) Trust‑aware scan (pre/post prompts)

You assign a **trust score** for the batch *before* scanning (0–3). The scan then overrides bad files.
After the scan, you re‑score and re‑apply zones.

```bash
python tools/review/scan_with_trust.py /Volumes/DJSSD/DRPBX \
  --db "$DEDUPE_DB" \
  --create-db \
  --check-integrity \
  --check-hash \
  --progress
```

Trust score meanings:
- **0** = known bad → quarantine
- **1** = likely bad → suspect
- **2** = maybe good → staging
- **3** = new/likely good → staging (accepted only if `--allow-accepted`)

Overrides:
- integrity fail / corrupt / recoverable → **suspect**

---

## 3) Hoard all tags (inventory)

Run a tag hoard to get a full inventory of embedded tags (useful before canonizing/promoting):

```bash
python3 tools/review/hoard_tags.py "/Volumes/DJSSD/DRPBX" \
  --out "/Volumes/DJSSD/_TAG_HOARD" \
  --db "$DEDUPE_DB" \
  --db-add
```

Outputs:
- `tags_summary.json`
- `tags_values.csv`
- `tags_keys.txt`
- `files_tags.jsonl` (if `--dump-files`)

---

## 4) Metadata recovery (duration truth)

For duration‑based health checks, use **Beatport + iTunes** (fast, broad):

```bash
./.venv/bin/dedupe metadata enrich \
  --db "$DEDUPE_DB" \
  --recovery \
  --providers beatport,itunes \
  --zones suspect \
  --retry-no-match \
  --execute
```

Afterwards, pull a mismatch report:
```bash
sqlite3 -header -csv "$DEDUPE_DB" \
"SELECT path,
        duration AS measured_s,
        canonical_duration AS trusted_s,
        ROUND(ABS(duration - canonical_duration), 3) AS delta_s,
        canonical_duration_source,
        metadata_health,
        metadata_health_reason
 FROM files
 WHERE canonical_duration IS NOT NULL
 ORDER BY delta_s DESC;" \
> /Users/georgeskhawam/Projects/dedupe/duration_mismatches.csv
```

---

## 5) Canonize tags (optional before promote)

```bash
python tools/review/canonize_tags.py /Volumes/DJSSD/DRPBX --canon-dry-run
python tools/review/canonize_tags.py /Volumes/DJSSD/DRPBX --execute
```

---

## 6) Promote (canonized by default)

`promote_by_tags.py` now applies canonical rules by default and writes tags to the promoted files.

```bash
python tools/review/promote_by_tags.py \
  /Volumes/DJSSD/DRPBX \
  --dest /Volumes/DJSSD/Library \
  --execute
```

Disable canon if needed:
```bash
python tools/review/promote_by_tags.py \
  /Volumes/DJSSD/DRPBX \
  --dest /Volumes/DJSSD/Library \
  --no-canon \
  --execute
```

---

## 7) Dedupe plan (after you have a stable library)

```bash
dedupe recommend --db "$DEDUPE_DB" --output plan.json
dedupe apply plan.json --confirm
```

---

## Notes
- This workflow assumes **no main library** at the start.
- Trust scores are a **prior**, scan results are the **final authority**.
- Canon rules come from `tools/rules/library_canon.json` and are shared with Picard.
- Use `--db-add` on inventory tools (like `hoard_tags.py`) to append to an existing DB.
- If you need a single, clean path: **follow this document only**.
