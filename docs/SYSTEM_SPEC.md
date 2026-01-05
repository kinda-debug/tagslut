# FLAC Deduplication System

A curator-first Python system for verifying, indexing, and auditing large FLAC collections recovered from heterogeneous sources.

**COMMUNE** is the future canonical library layout.  
**Yate** remains the metadata authority after ingestion.  
**The dedupe layer never deletes or mutates audio or tags.**  
It produces reviewable, resumable decisions only.

---

## Core Principles (Non-Negotiable)

1. **Content beats provenance**
   - Decisions are based on decoded audio validity and hashes, not folder names.

2. **Scan once, decide later**
   - Scanning is destructive to nothing, resumable, and additive.

3. **Everything is explainable**
   - Every recommendation must be traceable to DB facts.

4. **No auto-deletes**
   - The system emits plans, not actions.

---

## Architecture

Refactored (2025) into a strict layered design:

- **`dedupe/core/`**
  - Hashing strategies
  - Integrity evaluation
  - Quality comparison
  - Decision scoring

- **`dedupe/storage/`**
  - SQLite schema
  - Migrations
  - Indexes

- **`dedupe/utils/`**
  - Parallel execution
  - File walkers
  - Logging / progress

- **`tools/`**
  - Explicit CLIs
  - No hidden side effects

---

## Database Model (Reality, Not Theory)

A single long-lived SQLite DB aggregates all scans.

**Typical location:**
```
~/Projects/dedupe_db/music.db
```

The DB is:
- append-only
- resumable
- multi-library aware

**Key Concepts Stored:**
- absolute path
- library tag (recovery, vault, bad, etc.)
- zone (accepted, suspect, quarantine)
- FLAC integrity status
- audio hash
- technical properties (SR, BD, channels)
- timestamps and scan generations

---

## Libraries vs Zones (Important Distinction)

**Library = provenance**  
**Zone = trust level**

### Example mapping:

| Library    | Meaning                       |
|------------|-------------------------------|
| recovery   | R-Studio recovered material   |
| vault      | Older curated stash           |
| bad        | Known trash / collisions      |

| Zone       | Meaning                       |
|------------|-------------------------------|
| accepted   | Preferred reference material  |
| suspect    | Valid but lower confidence    |
| quarantine | Broken / lossy / junk         |

---

## Configuration

```toml
[library]
name = "COMMUNE"
root = "/Volumes/COMMUNE"

[library.zones]
staging = "10_STAGING"
accepted = "20_ACCEPTED"

[decisions]
zone_priority = ["accepted", "staging", "suspect", "quarantine"]
```

**Yate is never invoked during scanning.**  
Tag reading is passive only.

---

## Step-0: Canonical Ingestion (This Is the Real System)

Step-0 is where all chaos enters and nothing leaves.

### Scan (resumable, multi-source)

```bash
python3 tools/integrity/scan.py \
  /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY \
  --db ~/Projects/dedupe_db/music.db \
  --library recovery \
  --zone accepted \
  --check-integrity \
  --incremental \
  --progress \
  --verbose
```

Then extend the same DB:

```bash
python3 tools/integrity/scan.py \
  /Volumes/Vault \
  --db ~/Projects/dedupe_db/music.db \
  --library vault \
  --zone suspect \
  --check-integrity \
  --incremental \
  --progress

python3 tools/integrity/scan.py \
  /Volumes/bad \
  --db ~/Projects/dedupe_db/music.db \
  --library bad \
  --zone quarantine \
  --check-integrity \
  --incremental \
  --progress
```

**Nothing is copied. Nothing is renamed.**

---

## Performance Guarantees (Why This Scales)

### Parallelism
- File discovery: streaming walker
- Audio verification: bounded worker pool
- Hashing: only after integrity passes

### SQLite tuning (mandatory)

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;
PRAGMA cache_size=-200000;
```

### Hash Strategy (Explicit Tradeoffs)

| Hash Type   | Purpose                         | Cost |
|-------------|---------------------------------|------|
| FLAC MD5    | Fast corruption detection       | Low  |
| PCM SHA-256 | Canonical audio identity        | High |
| Path hash   | Incremental short-circuiting    | Low  |

**PCM hash is:**
- computed only once
- cached forever
- reused across all libraries

---

## Decision Phase (Read-Only)

```bash
python3 tools/decide/recommend.py \
  --db ~/Projects/dedupe_db/music.db \
  --output plan.json
```

### Decision rules (strict order):
1. Integrity
2. Zone priority
3. Audio quality
4. Provenance confidence

**Output:**
- JSON plan
- human-readable explanations
- no side effects

---

## Artifact Indexing (You Already Have This)

Recovered systems leave debris. These are indexed, not ignored.

```bash
python3 tools/ingest/run.py artifacts \
  --inputs /Volumes/RECOVERY_TARGET/Root/artifacts \
  --db ~/Projects/dedupe_db/music.db
```

**Examples:**
- `.DOTAD_*`
- old SQLite DBs
- audit reports
- dedupe logs

These inform decisions, they don't contaminate them.

---

## What This Explicitly Does NOT Do

- ❌ Rename files
- ❌ Edit tags
- ❌ Trust folder names
- ❌ Delete anything
- ❌ Require Yate, Picard, or Roon

**Those come after COMMUNE exists.**

---

## Where You Are Now (Reality Check)

You are past design and inside execution.

- DB exists (or will)
- Scans are resumable
- `/Volumes/bad` is correctly quarantined
- `/Volumes/COMMUNE` is future-only

### Next meaningful steps, when you say so:
- promote winners to COMMUNE
- generate "safe to delete" sets
- produce missing-album reacquisition lists

**No more rewrites.**  
**No more prompts.**  
**Just controlled reduction of entropy.**
