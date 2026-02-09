# REPORT.md — Music Library Deduplication and Rebuild Project

## Project Summary / Introduction

### Project Name: dedupe (Music Library Deduplication and Rebuild)

This repository manages a comprehensive effort to **deduplicate, rebuild, and maintain** a large electronic music library after significant data loss. The project uses multiple tools—including **bpdl (Beatport Downloader)** for sourcing DJ-critical material, **Yate** for manual precision tagging, and custom scanning/hashing infrastructure—to create a clean, well-organized, metadata-rich library.

**bpdl is one tool within this project, not the project itself.**

---

### Why This Project Exists

This repository is a response to three converging realities:

1. **Massive data loss and un-auditable recovery**  
   At some point, the library went through large-scale copying, migration, and partial recovery that:
   - Introduced silent corruption and potential skips,
   - Produced unknown duplicates, mismatched versions, and inconsistent paths,
   - Destroyed any realistic possibility of **manual, track-by-track validation**.

   As a result, "what's currently on disk" cannot be assumed to be correct or canonical. The project is fundamentally about **sanity, deduplication, and provenance** in the aftermath of that event.

2. **Post-loss downloads as the seed of a new canonical library**  
   Since that event, roughly **1–2 thousand tracks** have been freshly downloaded in a more controlled way (especially via Beatport using bpdl). These recent, well-sourced files:
   - Have better, more consistent metadata,
   - Are more likely to be intact and non-corrupt,
   - Reflect current taste and DJ priorities.

   **Promoting these recent downloads to "first-class citizens"** is the **germ of the new library**. They should form the **initial canonical core**, into which legacy material will be selectively merged, replaced, or discarded.

3. **Scale and specialization make manual management impossible**  
   The collection is:
   - Too **large** for manual curation,
   - Too **specialized** (electronic, DJ-oriented) for generic tools like iTunes to handle at this scale and complexity,
   - Too **critical for DJ use** to tolerate bad metadata, broken files, or unknown provenance.

   This makes automation, strict rules, and good documentation non-optional.

---

## Core Philosophy

1. **Rebuild from trusted sources instead of rescuing everything**  
   Because of the unreliability and size of the legacy archive, the strategy is:

   - Use **Beatport via bpdl** as the **canonical source** for:
     - DJ-critical tracks,
     - Many favorite albums,
     - High-value catalog where precise metadata matters.
   - Treat a fresh Beatport download as **at least as good and usually better** than any ambiguous older copy.
   - Prefer "redownload and promote" over "try to save every legacy file at all costs."

   However, this is balanced by a strong aversion to "tag-then-keep-or-discard audio" workflows that casually throw away original files. Any decision to discard or replace audio must be **deliberate and documented**, not accidental.

2. **Zero-tolerance zone for DJ material**  
   For DJ use:
   - **Tolerance for error is effectively zero.**
   - Bad BPM, wrong keys, mismatched versions, broken files, or wrong mixes are unacceptable.
   - **Duration must match a trusted reference** before promotion; size/format never override a duration mismatch.
   - DJ tracks and favorite albums may be **redownloaded** and **re-promoted** from Beatport (or other reliable sources) when needed.

   For non-DJ / background listening:
   - If a file has minor issues (possible skips/corruption) that you **cannot hear** and it is **not DJ material nor a key favorite**, then getting a pristine replacement is **not a priority**.

3. **Strict structure, not ad-hoc fixes**  
   The goal is a **single, predictable folder hierarchy** and a clear notion of **canonical paths**, with:
   - Move-only semantics: **no leaving behind shadow copies or stray duplicates**.
   - Reproducible rules for how files move from:
     - Ingest / download areas →  
     - Staging / verification →  
     - Final canonical library (with clear DJ vs non-DJ separation).

   The philosophy is that structure, not manual heroics, is what will keep the library sane in the long run.

### Canonical Library Naming (FINAL_LIBRARY)

The canonical library uses a **single, strict layout** derived deterministically from tags:

```
FINAL_LIBRARY/
  <Album Artist>/
    (<Release Year>) <Album Title>/
      <Artist or Album Artist> – (<Release Year>) <Album Title> – <Disc><Track> <Track Title>.flac
```

- **Album Artist is authoritative** for folders and filenames, except **Various Artists** albums where the filename uses **Track Artist** (also treats pathological comma-list albumartist values as Various Artists).
- Promotion is **move-only** and automated:
  - Plan: `tools/review/plan_promote_to_final_library.py`
  - Execute moves: `tools/review/move_from_plan.py` (using the generated plan CSV)
  - Direct mover (dry-run by default): `tools/review/promote_by_tags.py --final-library`

---

## Tools and Their Roles

### bpdl (Beatport Downloader) — Automated Download & Tagging

`bpdl` is the core tool for **downloading** tracks from Beatport and **writing rich metadata** into audio files. It is **one component** of this project, not the project itself.

**bpdl handles:**
- **Downloading** tracks (especially DJ material) from Beatport.
- **Writing all possible, supported metadata fields** into FLAC (and potentially M4A) files:
  - Beatport track/release IDs and URLs,
  - Label, catalog number, UPC,
  - ISRC, release date, year,
  - Artists, remixers, album artists, track titles, mixes,
  - BPM, key, genres, and subgenres.
- **Directory organization** via `sort_by_context` and `*_directory_template` settings.
- **Filename formatting** via `track_file_template`.

The configuration's goal is to **extract and persist every metadata field bpdl supports** that's relevant to:
- **Roon** (for rich library browsing),
- **Rekordbox** (for DJ prep),
- **Audi media system** (for consistent in-car display and navigation).

**Important:** BeatportDL does NOT generate M3U playlists. M3U generation is handled by `dedupe mgmt --m3u` or `tools/review/promote_by_tags.py` after downloads are registered to the inventory.

**Future feature: Album/artist-level fetches**  
The ability for bpdl (or companion tooling) to fetch not only by track/release URL but also **by album or even by artist**, enabling:
- Systematic discography rebuilds,
- Bulk, structured fetching at the album/artist level, not only track-by-track one-offs.

---

### Yate — Manual Precision Tagging

While bpdl and the scanning/database pipeline aim to automate as much as possible, **there will always be edge cases and high-value material** where complete control over tags is needed. That's where **Yate** comes in.

**Yate is used for:**
- Hand-correcting high-value albums and DJ essentials,
- Fixing edge cases where automated metadata (even from Beatport) is wrong or incomplete,
- Precise control over fields that different players interpret differently (Album Artist vs Artist, compilation flags, etc.).

**Yate's role in the workflow:**
- bpdl + Beatport give consistent, machine-readable metadata.
- The scanner + DB layer tracks what exists, where it lives, and its provenance.
- **Yate is where taste and judgment override everything else.**
  - If Beatport's genre is technically correct but not how you think about it, Yate can enforce your schema.
  - If an album should be treated as a compilation or not, Yate is where you lock that in.
- For tracks that **don't match Beatport well** (obscurities, promos, older rips), Yate is where you:
  - Repair tags from whatever sources you have,
  - Normalize them into the same schema that the rest of the pipeline uses.

**Integration with normalization:**
- Scanner detects anomalies and writes them into the DB,
- You get a list of "items needing manual attention,"
- You open those files in Yate, fix them according to your rules,
- Then re-scan or update the DB to capture the corrected state.

**bpdl vs Yate — Division of labor:**
- **bpdl's job:** Fetch from Beatport, write all machine-available metadata, do it consistently at scale.
- **Yate's job:** Refine and correct what matters most to *you*, resolve subjective decisions, provide a rich interactive environment for cases automation can't fully solve.

Yate is the **surgical tool on top of an automated conveyor belt**, not the primary bulk engine.

---

## Scanning, Hashing, and Normalization

Given the scale and the messy legacy state, the project must support a **fast, lightweight scanning pass** that can run end-to-end and give a baseline view of the collection without doing heavy work on every file.

### Planned Features

1. **Quick, light hashing of audio files**  
   - Compute **fast, non-cryptographic (or cached cryptographic)** hashes sufficient to:
     - Detect obvious duplicates,
     - Anchor files in a **basic inventory database** without re-reading everything constantly.
   - This is not meant as a full forensic check; it's a **practical fingerprint** to support higher-level decisions.

2. **Basic database of file metadata**  
   - Maintain a **lightweight database** (e.g., SQLite or equivalent) that stores:
     - File paths, hashes, sizes, modification times,
     - Parsed metadata: artist, album, title, BPM, key, label, release IDs, etc. where available,
     - Provenance flags: "Beatport canonical," "Legacy unknown," "Promoted to canonical library," etc.
   - The database becomes the **source of truth** for deduplication and promotion decisions, not just the filesystem.

3. **Genre/style and naming normalization**  
   To make the collection usable across tools and to avoid fragmentation:

   - Implement **normalization of artist names**, e.g.:
     - Handling aliases and case variants,
     - Avoiding multiple spellings / punctuation of the same artist.
   - Implement **genre/style normalization**, so that:
     - Beatport's sometimes-hyper-granular genres can be mapped into a consistent internal schema,
     - You can use these normalized genres for browsing and DJ workflows.
   - This normalization should be driven by the scanning + database layer, so:
     - A single change to a normalization rule can propagate,
     - You avoid manually fixing the same issue in 100 different places.

   The first pass should still be **fast and light**: gather enough data to identify patterns and plan heavy operations later.

---

## Core Pipeline (High-Level)

1. Scan existing volumes for audio files with **light hashing + basic metadata extraction**.
2. Populate the **inventory database** with paths, hashes, and tags.
3. Identify obvious **Beatport-matchable** material (by tag, filename, or manual mapping).
4. For DJ and high-priority material:
   - Fetch/re-fetch from Beatport via bpdl,
   - Tag with maximum metadata,
   - Place into well-defined destination paths.
5. Promote verified files into the **canonical library** (DJ vs general listening clearly separated).
6. Keep the process repeatable and scriptable.

---

## Compatibility Targets

Tags and structure should support:

- **Roon:** Album/artist/label correctness, release date, IDs (ISRC, etc.), genres.
- **Rekordbox:** Track titles, artists, BPM, key, cues later; reliability of file paths and tags.
- **Audi media system:** Clean artist/title/album tags, consistent artwork, sane file and folder naming.

---

## Documentation and Agent-Readiness

All decisions, constraints, and patterns must be documented so that:
- Future **you** can remember why things are the way they are.
- Future **AI agents** can operate safely without guessing:
  - They should understand the "move-only" policy,
  - The primacy of Beatport for DJ material,
  - The difference between "new canonical downloads" and "legacy residue,"
  - The role of the scanning + database + normalization layer.

This is why both `REPORT.md` (high-level state and strategy) and `AGENTS.md` (operational dos/don'ts) are critical.

### Redesign Proposal (2026-02-09)

A radical redesign proposal (architecture, data model v3, policy engine, CLI convergence, and migration phases) is documented at:

- `docs/PROPOSAL_RADICAL_REDESIGN_2026-02-09.md`
- Execution tracker: `docs/REDESIGN_TRACKER.md`
- Move executor compatibility contract (Phase 0 baseline):
  - `docs/MOVE_EXECUTOR_COMPAT.md`
  - Adapter module: `dedupe/exec/compat.py`
  - Current adapter consumers:
    - `tools/review/move_from_plan.py`
    - `tools/review/quarantine_from_plan.py`
  - Additional active move path with structured audit logging:
    - `tools/review/promote_by_tags.py` (via `dedupe/utils/file_operations.py`, `--move-log`)
- Phase 1 runbook:
  - `docs/PHASE1_V3_DUAL_WRITE.md`
- Phase 1 verification report:
  - `docs/PHASE1_VERIFICATION_2026-02-09.md`
- Phase 2 runbook:
  - `docs/PHASE2_POLICY_DECIDE.md`
- Phase 2 verification report:
  - `docs/PHASE2_VERIFICATION_2026-02-09.md`
- Phase 3 runbook:
  - `docs/PHASE3_EXECUTOR.md`
- Phase 3 verification report:
  - `docs/PHASE3_VERIFICATION_2026-02-09.md`
- Phase 4 runbook:
  - `docs/PHASE4_CLI_CONVERGENCE.md`
- Phase 4 verification report:
  - `docs/PHASE4_VERIFICATION_2026-02-09.md`
- Phase 5 decommission plan:
  - `docs/PHASE5_LEGACY_DECOMMISSION.md`
  - Legacy and compatibility wrapper decommission (`scan/recommend/apply/promote/quarantine/mgmt/metadata/recover`) executed on February 9, 2026.
- Phase 5 verification report:
  - `docs/PHASE5_VERIFICATION_2026-02-09.md`

---

## Management & Recovery Modes (New)

The dedupe CLI now supports two primary operational modes for building a clean, sanitized library from fresh downloads:

### `dedupe mgmt` — Management Mode

Management mode maintains a **central inventory database** of all audio files from multiple download sources (bpdl, qobuz-dl, tidal-dl, etc.) and provides:

- **Pre-download duplicate checking**: Before downloading, query the inventory for similar tracks by artist/title, ISRC, or fingerprint. Prevents accidentally re-downloading tracks from yesterday.
- **Interactive diagnosis**: When a similar file is found, display specs (quality, source, date) and prompt: Skip / Download anyway / Replace.
- **M3U playlist generation**: The `--m3u` flag generates Roon-compatible playlists for downloaded content. Use `--merge` for a single combined playlist or one-per-item by default. (Note: This is a `dedupe mgmt` feature, NOT a BeatportDL feature.)
- **Source tracking**: Every file is tagged with its download source and date for provenance.

#TODO: Implement M3U generation in `dedupe mgmt --m3u`
#TODO: Log every decision (checks, waivers, moves) to JSON audit log
#TODO: Implement interactive prompt when similar files exist (skip/download/replace)

Example:
```bash
# Register downloads and check for duplicates
dedupe mgmt --source bpdl --check ~/Downloads/bpdl/
# Generate M3U playlist (separate step - M3U is a dedupe mgmt feature, not bpdl)
dedupe mgmt --m3u ~/Downloads/bpdl/
```

### `dedupe recovery` — Recovery Mode

Recovery mode handles actual file operations with strict move-only semantics:

- **`--move` / `--no-move`**: Explicit flag required to actually move files (default: dry-run).
- **`--rename-only`**: Rename files in place without relocating—useful for normalization passes.
- **Full logging**: Every operation logged in JSON/TSV for auditability and potential rollback.
- **Zone-aware**: Move files to specific zones (accepted, staging, etc.).

Example:
```bash
# Preview moves
dedupe recovery --no-move --zone accepted /staging/

# Execute moves
dedupe recovery --move --zone accepted --source bpdl /staging/

# Rename-only pass
dedupe recovery --rename-only --move /accepted/
```

### Central Inventory Database

The inventory DB extends the existing `files` table with:
- `download_source`: bpdl, qobuz, tidal, legacy
- `download_date`: When the file was registered
- `original_path` / `canonical_path`: Track file movement
- `isrc`, `fingerprint`: For similarity matching
- `m3u_exported`, `m3u_path`: M3U tracking
- `mgmt_status`: new → checked → verified → moved

This database is the **single source of truth** for what exists, where it came from, and where it should go.

### Workflow: Building a Sanitized Library

The new workflow for building a clean library from fresh downloads:

1. **Download** from Beatport using bpdl (directory layout controlled by `sort_by_context` and `*_directory_template`)
2. **Register** to inventory with `dedupe mgmt --source bpdl --check <path>`
3. **Generate M3U** with `dedupe mgmt --m3u <path>` (or use `tools/review/promote_by_tags.py`)
4. **Review** M3U in Roon, verify tracks
5. **Move** verified tracks with `dedupe recovery --move --zone accepted`
6. **Repeat** — inventory prevents re-downloads

**Note:** BeatportDL does NOT have a `--m3u` flag. M3U generation is a `dedupe mgmt` responsibility.

This replaces the old "rescue everything" approach with a controlled, inventory-driven build of a small, super-sanitized core library.

See [docs/MGMT_MODE.md](./docs/MGMT_MODE.md) for full specification.

---

## Summary

This project is:

- A **recovery and sanity layer** on top of a library damaged by massive, hard-to-audit changes.
- A **structured rebuild** centered on:
  - Beatport + bpdl as one tool for canonical, metadata-rich DJ and favorite material,
  - A **new core library** seeded from the 1–2k post-loss downloads,
  - A fast, database-backed scan + hash + normalization tier,
  - Yate for manual precision tagging of edge cases and high-value material.
  - **Management mode** for inventory-driven download tracking, duplicate prevention, and M3U generation.
  - **Recovery mode** for controlled, logged file operations with move-only semantics.
- A **long-term framework** for deduplicating, normalizing, and promoting tracks into a clean, tool-friendly, DJ-safe library—without ever going back to ad-hoc, manual chaos.

**bpdl is a tool (for downloading). dedupe mgmt handles M3U generation and inventory. The project is dedupe.**
