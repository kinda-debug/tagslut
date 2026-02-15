Here’s a finalized, consolidated report you can drop into `REPORT.md` (or use to replace the top-level narrative in `handover.md`). It’s written as a self-contained document for you and for future agents.

You can copy-paste this as-is:

---

## Project: dedupe — Library Recovery, Deduplication, and Rebuild

### 1. Why this project exists

This repository exists because your music library went through a **massive data loss** followed by **large-scale, poorly-audited copying and recovery**. That event:

- Introduced unknown **duplicates and mismatched versions**,  
- Likely caused **silent corruption and skips** in some files,  
- Left you with **inconsistent paths and folder structures**,  
- Destroyed any realistic possibility of **manual, track-by-track verification** at your scale.

As a result, **“what’s currently on disk” cannot be assumed to be canonical or correct**. The core mission of this repo is:

- **Sanity** — understanding what you have and where it is,  
- **Deduplication** — consolidating multiple copies into a clean canonical set,  
- **Provenance** — tracking where files came from and how trustworthy they are.

This is not a “bpdl project.”  
This is the **dedupe project**: a comprehensive, multi-tool effort to rebuild a clean, DJ-safe, metadata-rich library from a damaged, oversized legacy archive.

---

### 2. Post-loss downloads: seed of the new library

Since the data loss event, roughly **1–2 thousand tracks** have been downloaded in a more controlled way, especially via **Beatport** and **bpdl (Beatport Downloader)**. These post-loss downloads:

- Have **better, more consistent metadata**,  
- Are more likely to be **intact and non-corrupt**,  
- Reflect your **current DJ priorities and taste**.

These files should be treated as **first-class citizens** and form the **burgeon of the new canonical library**:

- They become the starting point for a **trusted core**.
- Legacy material is evaluated **against** this core and is selectively:
  - Promoted,
  - Replaced by a fresh Beatport download,
  - Or left in a quarantine/legacy zone.

A fresh, clean **Beatport download** is considered **at least as good and usually better** than any ambiguous older copy, especially for DJ-critical material.

---

### 3. Philosophy and constraints

#### 3.1 Rebuild from trusted sources

Because the legacy archive is large and unreliable:

- Prefer **re-downloading from Beatport** (via bpdl) for:
  - DJ-critical tracks,
  - Favorite albums,
  - High-value catalog where metadata and reliability matter.
- Use new Beatport downloads as the **trusted version**, not the old copies.
- Be deliberate about discarding: you will **replace**, but not accidentally destroy audio.

#### 3.2 Zero tolerance for DJ material

For **DJ use**:

- Tolerance for error is effectively **zero**.  
- Unacceptable issues:
  - Wrong or unstable BPM,
  - Incorrect keys,
  - Wrong versions/mixes,
  - Broken or skipping files,
  - Inconsistent or misleading metadata.

For **non-DJ / background listening**:

- Minor, inaudible imperfections are tolerated,
- Perfect metadata is less critical,
- Canonicalization still matters, but urgency is lower.

#### 3.3 Strict structure, not ad-hoc fixes

Long-term stability comes from **structure and rules**, not ad-hoc manual heroics. The project aims for:

- A **single, predictable folder hierarchy** with clearly defined canonical paths,
- **Move-only semantics**:
  - Files move from download → staging → canonical library,
  - No untracked copies or “shadow” duplicates,
  - When something is promoted, the old locations are cleaned up deliberately.
- A **documented pipeline** so that both you and future agents know:
  - Where files should live,
  - What each path means,
  - How a file graduates into the canonical library.

---

### 4. Tools and their roles

This project uses several tools and systems; each has a distinct role.

#### 4.1 bpdl (Beatport Downloader)

**bpdl** is the **Beatport downloader and metadata engine**, not the project itself.

Its responsibilities:

- Download tracks and releases from **Beatport** (and possibly other stores, if configured),
- Write **all possible supported metadata fields** into FLAC (and optionally M4A) files, including:
  - Beatport track/release IDs and URLs,
  - ISRC, label, catalog number, UPC,
  - Release date, year,
  - Artists, remixers, album artists, track titles, mix names,
  - BPM, key, genres/subgenres,
  - Artwork/cover images.
- Enforce consistent **filename and folder templates**, aligned with your canonical structure.
- Serve as the **primary ingestion source** for:
  - DJ-critical tracks,
  - Favorite albums,
  - High-value catalog that you decide to rebuild.

You want bpdl configured so that:

- **Every metadata field it supports** that is useful for:
  - **Roon** (rich library browsing),
  - **Rekordbox** (DJ prep),
  - **Your Audi’s media system** (in-car browsing),
- Is actually written into the tags on disk.

#### 4.2 Scanning, hashing, and the inventory database

Given the size and messiness of your archive, you need a **fast, lightweight scanning pass** that can run end-to-end and give you a baseline view without expensive per-file work.

Planned capabilities:

1. **Quick, light hashing**
   - Compute **fast, non-cryptographic** (or cached cryptographic) hashes for audio files.
   - Use them to:
     - Detect obvious duplicates,
     - Anchor files in an **inventory database** so you don’t need to re-read files constantly.

2. **Inventory database**
   - Maintain a **lightweight DB** (likely SQLite) that stores:
     - File paths, sizes, modification times,
     - Hashes (fast hash, optional strong hash),
     - Parsed metadata: artist, album, title, BPM, key, label, store IDs, etc.,
     - **Provenance and trust flags**, e.g.:
       - `beatport_canonical`,
       - `legacy_unknown`,
       - `promoted_to_canonical`,
       - `suspected_duplicate`,
       - `needs_manual_review`.

   - The DB becomes the **source of truth** for:
     - Deduplication decisions,
     - Promotion / replacement logic,
     - Automation workflows.

3. **Normalization**
   - Use the DB to drive **normalization**:
     - **Artist names**:
       - Handle aliases and case variants,
       - Unify punctuation and spacing.
     - **Genres/styles**:
       - Map Beatport’s micro-genres into a consistent internal schema,
       - Maintain a manageable set of genres for Roon/Rekordbox/Audi.
   - Centralize normalization rules so:
     - One change propagates across many files,
     - You avoid hand-editing the same issue thousands of times.

#### 4.3 Yate — the manual gold-standard tagger

**Yate** is your **manual precision tag editor** for high-value and edge-case material. Its role:

- **Gold-standard editing** for:
  - DJ-critical tracks,
  - Favorite albums,
  - Albums or tracks that automation can’t tag correctly.
- Resolve subjective or nuanced decisions:
  - Exactly how artist names should appear,
  - Whether something is treated as a compilation,
  - Your personal genre taxonomy,
  - Comments and notes fields that matter to you.

Yate integrates with the normalization and database layer by:

1. The scanner/DB identifies anomalies:
   - Suspicious artist variants,
   - Conflicting metadata between files with the same IDs,
   - Outliers in genres or labels,
   - High-priority items with incomplete tags.
2. You open these flagged items in Yate and:
   - Fix tags according to your schema,
   - Apply consistent patterns and rules.
3. The DB is updated (via re-scan or targeted updates) to reflect the corrected state.

Yate is **not** your bulk engine; it is the **surgical tool** used **after** bpdl and the scanner have done the heavy lifting.

---

### 5. Desired future features

#### 5.1 Album- and artist-level fetching

You want the ability (likely via bpdl or companion tooling) to:

- Fetch content **not only** by individual track or release URLs, but also:
  - By **album**,
  - Potentially by **artist**,
  - To rebuild:
    - Complete or near-complete **discographies**,
    - Key sections of an artist’s catalog.

This is especially important when:

- Rebuilding favorite artists’ bodies of work,
- Converting partial or inconsistent album collections into **clean, canonical sets**.

The exact implementation is **TBD**, but the requirement is clear:  
**bulk, structured album/artist-level fetching**, driven by the inventory DB and manifest logic.

#### 5.2 Structured rescans and re-tags

Once the pipeline is stable, you want to:

- Periodically **re-scan** to:
  - Pick up new files,
  - Re-hash changed ones,
  - Refresh normalized fields from updated rules.
- Potentially **re-tag files** using updated bpdl config or normalization rules.

---

### 6. State of conservation (today)

Summarizing where things stand conceptually:

- The **legacy archive**:
  - Large, partly