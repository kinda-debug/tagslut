## Project Summary / Introduction

### Why this project exists

This repository is a response to three converging realities:

1. **Massive data loss and un‑auditable recovery**
   At some point, your library went through large‑scale copying, migration, and partial recovery that:

   - Introduced silent corruption and potential skips,
   - Produced unknown duplicates, mismatched versions, and inconsistent paths,
   - Destroyed any realistic possibility of **manual, track‑by‑track validation**.

   As a result, “what’s currently on disk” cannot be assumed to be correct or canonical. The project is fundamentally about **sanity, deduplication, and provenance** in the aftermath of that event.

2. **Post‑loss downloads as the seed of a new canonical library**
   Since that event, roughly **1–2 thousand tracks** have been freshly downloaded in a more controlled way (especially via Beatport and bpdl). These recent, well‑sourced files:

   - Have better, more consistent metadata,
   - Are more likely to be intact and non‑corrupt,
   - Reflect your current taste and DJ priorities.

   **Promoting these recent downloads to “first‑class citizens”** is the **germ of the new library**. They should form the **initial canonical core**, into which legacy material will be selectively merged, replaced, or discarded.

3. **Scale and specialization make manual management impossible**
   The collection is:

   - Too **large** for manual curation,
   - Too **specialized** (electronic, DJ‑oriented) for generic tools like iTunes to handle at this scale and complexity,
   - Too **critical for DJ use** to tolerate bad metadata, broken files, or unknown provenance.

   This makes automation, strict rules, and good documentation non‑optional.

------

Core Philosophy

1. **Rebuild from trusted sources instead of rescuing everything**
   Because of the unreliability and size of the legacy archive, the strategy is:

   - Use **Beatport via bpdl** as the **canonical source** for:
     - DJ‑critical tracks,
     - Many favorite albums,
     - High‑value catalog where precise metadata matters.
   - Treat a fresh Beatport download as **at least as good and usually better** than any ambiguous older copy.
   - Prefer “redownload and promote” over “try to save every legacy file at all costs.”

   However, this is balanced by your strong aversion to “tag‑then‑keep‑or‑discard audio” workflows that casually throw away original files. Any decision to discard or replace audio must be **deliberate and documented**, not accidental.

2. **Zero‑tolerance zone for DJ material**
   For DJ use:

   - **Tolerance for error is effectively zero.**
   - Bad BPM, wrong keys, mismatched versions, broken files, or wrong mixes are unacceptable.
   - DJ tracks and favorite albums may be **redownloaded** and **re‑promoted** from Beatport (or other reliable sources) when needed.

   For non‑DJ / background listening:

   - If a file has minor issues (possible skips/corruption) that you **cannot hear** and it is **not DJ material nor a key favorite**, then getting a pristine replacement is **not a priority**.

3. **Strict structure, not ad‑hoc fixes**
   The goal is a **single, predictable folder hierarchy** and a clear notion of **canonical paths**, with:

   - Move‑only semantics: **no leaving behind shadow copies or stray duplicates**.
   - Reproducible rules for how files move from:
     - Ingest / download areas →
     - Staging / verification →
     - Final canonical library (with clear DJ vs non‑DJ separation).

   The philosophy is that structure, not manual heroics, is what will keep the library sane in the long run.

------

bpdl and Metadata Strategy

1. **bpdl as the metadata engine**
   `bpdl` (BeatportDL) is the core tool for:

   - **Downloading** tracks (especially DJ material) from Beatport.
   - **Writing all possible, supported metadata fields** into FLAC (and potentially M4A) files:
     - Beatport track/release IDs and URLs,
     - Label, catalog number, UPC,
     - ISRC, release date, year,
     - Artists, remixers, album artists, track titles, mixes,
     - BPM, key, genres, and subgenres.

   The configuration’s goal is to **extract and persist every metadata field bpdl supports** that’s relevant to:

   - Roon (for rich library browsing),
   - Rekordbox (for DJ prep),
   - Your Audi’s media system (for consistent in‑car display and navigation).

2. **Compatibility targets**

   Tags and structure should support:

   - **Roon:** Album/artist/label correctness, release date, IDs (ISRC, etc.), genres.
   - **Rekordbox:** Track titles, artists, BPM, key, cues later; reliability of file paths and tags.
   - **Audi media system:** Clean artist/title/album tags, consistent artwork, sane file and folder naming.

3. **Beyond Beatport: artist/album–level fetches (future feature)**
   You want the ability for bpdl (or related tooling) to:

   - Fetch not only by track/release URL but also **by album or even by artist**, so that:
     - You can systematically rebuild discographies,
     - Or at least key sections of an artist’s catalog.
   - The exact implementation is **TBD**, but the requirement is clear: **bulk, structured fetching at the album/artist level**, not only track‑by‑track one‑offs.

------

Scanning, Hashing, and Normalization

Given the scale and the messy legacy state, the repo must support a **fast, lightweight scanning pass** that can run end‑to‑end and give you a baseline view of the collection without doing heavy work on every file.

Planned features and requirements:

1. **Quick, light hashing of audio files**

   - Compute **fast, non‑cryptographic (or cached cryptographic)** hashes sufficient to:
     - Detect obvious duplicates,
     - Anchor files in a **basic inventory database** without re‑reading everything constantly.
   - This is not meant as a full forensic check; it’s a **practical fingerprint** to support higher‑level decisions.

2. **Basic database of file metadata**

   - Maintain a **lightweight database** (e.g., SQLite or equivalent) that stores:
     - File paths, hashes, sizes, modification times,
     - Parsed metadata: artist, album, title, BPM, key, label, release IDs, etc. where available,
     - Provenance flags: “Beatport canonical,” “Legacy unknown,” “Promoted to canonical library,” etc.
   - The database becomes the **source of truth** for deduplication and promotion decisions, not just the filesystem.

3. **Genre/style and naming normalization**
   To make the collection usable across tools and to avoid fragmentation:

   - Implement **normalization of artist names**, e.g.:
     - Handling aliases and case variants,
     - Avoiding multiple spellings / punctuation of the same artist.
   - Implement **genre/style normalization**, so that:
     - Beatport’s sometimes‑hyper‑granular genres can be mapped into a consistent internal schema,
     - You can use these normalized genres for browsing and DJ workflows.
   - This normalization should be driven by the scanning + database layer, so:
     - A single change to a normalization rule can propagate,
     - You avoid manually fixing the same issue in 100 different places.

   The first pass should still be **fast and light**: gather enough data to identify patterns and plan heavy operations later.

------

Desired Features and Future Direction

1. **Core pipeline (high‑level)**

   - Scan existing volumes for audio files with **light hashing + basic metadata extraction**.
   - Populate the **inventory database** with paths, hashes, and tags.
   - Identify obvious **Beatport‑matchable** material (by tag, filename, or manual mapping).
   - For DJ and high‑priority material:
     - Fetch/re‑fetch from Beatport via bpdl,
     - Tag with maximum metadata,
     - Place into well‑defined destination paths.
   - Promote verified files into the **canonical library** (DJ vs general listening clearly separated).
   - Keep the process repeatable and scriptable.

2. **Album/artist‑level fetching**

   - Introduce a feature (either in bpdl or a companion script) that can:
     - Fetch releases by album,
     - Potentially, fetch bodies of work by artist.
   - This is especially useful when:
     - Rebuilding favorite artists’ catalogs,
     - Converting partial or corrupted album collections into clean canonical sets.

3. **Documentation and agent‑readiness**
   All decisions, constraints, and patterns must be documented so that:

   - Future **you** can remember why things are the way they are.
   - Future **AI agents** can operate safely without guessing:
     - They should understand the “move‑only” policy,
     - The primacy of Beatport for DJ material,
     - The difference between “new canonical downloads” and “legacy residue,”
     - The role of the scanning + database + normalization layer.

   This is why both `REPORT.md` (high‑level state and strategy) and `AGENTS.md` (operational dos/don’ts) are critical.

------

In summary, this project is:

- A **recovery and sanity layer** on top of a library damaged by massive, hard‑to‑audit changes.
- A **structured rebuild** centered on:
  - Beatport + bpdl for canonical, metadata‑rich DJ and favorite material,
  - A **new core library** seeded from the 1–2k post‑loss downloads,
  - A fast, database‑backed scan + hash + normalization tier.
- A **long‑term framework** for deduplicating, normalizing, and promoting tracks into a clean, tool‑friendly, DJ‑safe library—without ever going back to ad‑hoc, manual chaos.

If you’d like, I can next:

- Draft a concrete section describing the **exact scanning/hash database schema**, or
- Propose a **folder + naming convention** explicitly tuned for Roon/Rekordbox/Audi with examples.

### Why this project exists

This repository is a response to three converging realities:

1. **Massive data loss and un‑auditable recovery**  
   At some point, your library went through large‑scale copying, migration, and partial recovery that:
   - Introduced silent corruption and potential skips,
   - Produced unknown duplicates, mismatched versions, and inconsistent paths,
   - Destroyed any realistic possibility of **manual, track‑by‑track validation**.

   As a result, “what’s currently on disk” cannot be assumed to be correct or canonical. The project is fundamentally about **sanity, deduplication, and provenance** in the aftermath of that event.

2. **Post‑loss downloads as the seed of a new canonical library**  
   Since that event, roughly **1–2 thousand tracks** have been freshly downloaded in a more controlled way (especially via Beatport and bpdl). These recent, well‑sourced files:
   - Have better, more consistent metadata,
   - Are more likely to be intact and non‑corrupt,
   - Reflect your current taste and DJ priorities.

   **Promoting these recent downloads to “first‑class citizens”** is the **germ of the new library**. They should form the **initial canonical core**, into which legacy material will be selectively merged, replaced, or discarded.

3. **Scale and specialization make manual management impossible**  
   The collection is:
   - Too **large** for manual curation,
   - Too **specialized** (electronic, DJ‑oriented) for generic tools like iTunes to handle at this scale and complexity,
   - Too **critical for DJ use** to tolerate bad metadata, broken files, or unknown provenance.

   This makes automation, strict rules, and good documentation non‑optional.

---

Core Philosophy

1. **Rebuild from trusted sources instead of rescuing everything**  
   Because of the unreliability and size of the legacy archive, the strategy is:

   - Use **Beatport via bpdl** as the **canonical source** for:
     - DJ‑critical tracks,
     - Many favorite albums,
     - High‑value catalog where precise metadata matters.
   - Treat a fresh Beatport download as **at least as good and usually better** than any ambiguous older copy.
   - Prefer “redownload and promote” over “try to save every legacy file at all costs.”

   However, this is balanced by your strong aversion to “tag‑then‑keep‑or‑discard audio” workflows that casually throw away original files. Any decision to discard or replace audio must be **deliberate and documented**, not accidental.

2. **Zero‑tolerance zone for DJ material**  
   For DJ use:
   - **Tolerance for error is effectively zero.**
   - Bad BPM, wrong keys, mismatched versions, broken files, or wrong mixes are unacceptable.
   - DJ tracks and favorite albums may be **redownloaded** and **re‑promoted** from Beatport (or other reliable sources) when needed.

   For non‑DJ / background listening:
   - If a file has minor issues (possible skips/corruption) that you **cannot hear** and it is **not DJ material nor a key favorite**, then getting a pristine replacement is **not a priority**.

3. **Strict structure, not ad‑hoc fixes**  
   The goal is a **single, predictable folder hierarchy** and a clear notion of **canonical paths**, with:
   - Move‑only semantics: **no leaving behind shadow copies or stray duplicates**.
   - Reproducible rules for how files move from:
     - Ingest / download areas →  
     - Staging / verification →  
     - Final canonical library (with clear DJ vs non‑DJ separation).

   The philosophy is that structure, not manual heroics, is what will keep the library sane in the long run.

---

bpdl and Metadata Strategy

1. **bpdl as the metadata engine**  
   `bpdl` (BeatportDL) is the core tool for:

   - **Downloading** tracks (especially DJ material) from Beatport.
   - **Writing all possible, supported metadata fields** into FLAC (and potentially M4A) files:
     - Beatport track/release IDs and URLs,
     - Label, catalog number, UPC,
     - ISRC, release date, year,
     - Artists, remixers, album artists, track titles, mixes,
     - BPM, key, genres, and subgenres.

   The configuration’s goal is to **extract and persist every metadata field bpdl supports** that’s relevant to:
   - Roon (for rich library browsing),
   - Rekordbox (for DJ prep),
   - Your Audi’s media system (for consistent in‑car display and navigation).

2. **Compatibility targets**

   Tags and structure should support:

   - **Roon:** Album/artist/label correctness, release date, IDs (ISRC, etc.), genres.
   - **Rekordbox:** Track titles, artists, BPM, key, cues later; reliability of file paths and tags.
   - **Audi media system:** Clean artist/title/album tags, consistent artwork, sane file and folder naming.

3. **Beyond Beatport: artist/album–level fetches (future feature)**  
   You want the ability for bpdl (or related tooling) to:

   - Fetch not only by track/release URL but also **by album or even by artist**, so that:
     - You can systematically rebuild discographies,
     - Or at least key sections of an artist’s catalog.
   - The exact implementation is **TBD**, but the requirement is clear: **bulk, structured fetching at the album/artist level**, not only track‑by‑track one‑offs.

---

Scanning, Hashing, and Normalization

Given the scale and the messy legacy state, the repo must support a **fast, lightweight scanning pass** that can run end‑to‑end and give you a baseline view of the collection without doing heavy work on every file.

Planned features and requirements:

1. **Quick, light hashing of audio files**  
   - Compute **fast, non‑cryptographic (or cached cryptographic)** hashes sufficient to:
     - Detect obvious duplicates,
     - Anchor files in a **basic inventory database** without re‑reading everything constantly.
   - This is not meant as a full forensic check; it’s a **practical fingerprint** to support higher‑level decisions.

2. **Basic database of file metadata**  
   - Maintain a **lightweight database** (e.g., SQLite or equivalent) that stores:
     - File paths, hashes, sizes, modification times,
     - Parsed metadata: artist, album, title, BPM, key, label, release IDs, etc. where available,
     - Provenance flags: “Beatport canonical,” “Legacy unknown,” “Promoted to canonical library,” etc.
   - The database becomes the **source of truth** for deduplication and promotion decisions, not just the filesystem.

3. **Genre/style and naming normalization**  
   To make the collection usable across tools and to avoid fragmentation:

   - Implement **normalization of artist names**, e.g.:
     - Handling aliases and case variants,
     - Avoiding multiple spellings / punctuation of the same artist.
   - Implement **genre/style normalization**, so that:
     - Beatport’s sometimes‑hyper‑granular genres can be mapped into a consistent internal schema,
     - You can use these normalized genres for browsing and DJ workflows.
   - This normalization should be driven by the scanning + database layer, so:
     - A single change to a normalization rule can propagate,
     - You avoid manually fixing the same issue in 100 different places.

   The first pass should still be **fast and light**: gather enough data to identify patterns and plan heavy operations later.

---

Desired Features and Future Direction

1. **Core pipeline (high‑level)**  
   - Scan existing volumes for audio files with **light hashing + basic metadata extraction**.
   - Populate the **inventory database** with paths, hashes, and tags.
   - Identify obvious **Beatport‑matchable** material (by tag, filename, or manual mapping).
   - For DJ and high‑priority material:
     - Fetch/re‑fetch from Beatport via bpdl,
     - Tag with maximum metadata,
     - Place into well‑defined destination paths.
   - Promote verified files into the **canonical library** (DJ vs general listening clearly separated).
   - Keep the process repeatable and scriptable.

2. **Album/artist‑level fetching**  
   - Introduce a feature (either in bpdl or a companion script) that can:
     - Fetch releases by album,
     - Potentially, fetch bodies of work by artist.
   - This is especially useful when:
     - Rebuilding favorite artists’ catalogs,
     - Converting partial or corrupted album collections into clean canonical sets.

3. **Documentation and agent‑readiness**  
   All decisions, constraints, and patterns must be documented so that:
   - Future **you** can remember why things are the way they are.
   - Future **AI agents** can operate safely without guessing:
     - They should understand the “move‑only” policy,
     - The primacy of Beatport for DJ material,
     - The difference between “new canonical downloads” and “legacy residue,”
     - The role of the scanning + database + normalization layer.

   This is why both `REPORT.md` (high‑level state and strategy) and `AGENTS.md` (operational dos/don’ts) are critical.

------

**Yate’s Role in the Project**

While bpdl and the scanning/database pipeline aim to automate as much as possible, **there will always be edge cases and high‑value material** where you want complete control over tags. That’s where **Yate** comes in.

Yate should be treated as:

1. **The manual gold‑standard tag editor**

   - Use **Yate** for:

     - Hand‑correcting high‑value albums and DJ essentials,
     - Fixing edge cases where automated metadata (even from Beatport) is wrong or incomplete,
     - Precise control over fields that different players interpret differently (Album Artist vs Artist, compilation flags, etc.).

   - For “DJ‑critical” and “favorite albums,” once they’re:

     - Downloaded with bpdl,
     - Mapped into your canonical folder structure,
     - Imported into your inventory DB,

     you can run a

      

     Yate pass

      

     to:

     - Clean up artist names,
     - Fix capitalization and punctuation,
     - Adjust album/track titles when needed,
     - Ensure genres and comments are exactly what you want in Roon/Rekordbox/Audi.

2. **The bridge between automated metadata and human judgment**

   - bpdl + Beatport give you consistent, machine‑readable metadata.
   - The scanner + DB layer tracks what exists, where it lives, and its provenance.
   - **Yate is where your taste and judgment override everything else.**
     - If Beatport’s genre is technically correct but not how you think about it, Yate can enforce your schema.
     - If an album should be treated as a compilation or not, Yate is where you lock that in.
   - For tracks that **don’t match Beatport well** (obscurities, promos, older rips), Yate is likely the place where you:
     - Repair tags from whatever sources you have,
     - Normalize them into the same schema that the rest of the pipeline uses.

3. **Integration with the normalization strategy**
   The project already aims for:

   - Light scanning,
   - Basic database,
   - Normalization of artist names and genres.

   Yate can integrate with that by:

   - Being the tool you use when the DB flags:
     - “Suspicious” or inconsistent artist strings,
     - Weird genre values,
     - Collisions where two different tag sets claim to describe the same track (same ISRC/Beatport ID but different text).
   - In an ideal flow:
     - Scanner detects anomalies and writes them into the DB,
     - You get a list of “items needing manual attention,”
     - You open those files in Yate, fix them according to your rules,
     - Then re‑scan or update the DB to capture the corrected state.

4. **Yate vs. bpdl: clear division of labor**

   - **bpdl’s job:**
     - Fetch from Beatport,
     - Write all machine‑available metadata into the file,
     - Do it consistently and repeatably at scale.
   - **Yate’s job:**
     - Refine and correct what matters most to *you*,
     - Resolve subjective or aesthetic decisions,
     - Provide a rich interactive environment for the cases automation can’t fully solve.

   You’re not trying to turn Yate into the primary bulk engine; you’re using it as the **surgical tool on top of an automated conveyor belt**.

   -------













