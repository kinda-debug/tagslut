# Tagslut Project Document

Report Date: February 23, 2026

## Table of Contents
1. Executive Summary
2. System Architecture & Constraints
3. Problem Statement
4. Goals and Non-Goals
5. Current Implementation (Tagslut)
6. DJ Pipeline Details
7. Data Model & Artifacts
8. Operational Workflow (Step-by-Step)
9. Command Reference
10. Known Gaps and Risks
11. Roadmap
12. Reference Inputs

---

## 1. Executive Summary
Tagslut is a Python-based music library management system designed for large FLAC archives with a DJ-first workflow. It provides deterministic scanning, policy-based curation, metadata enrichment, and DJ-ready export. The primary target outcome is a repeatable, auditable pipeline that turns a 25,000-track FLAC master library into a gig-ready USB in Pioneer-compatible MP3 format while minimizing manual curation overhead.

This document consolidates goals, constraints, architecture, current capabilities, workflow steps, and remaining work into a single long-form project reference for developers and operators.

---

## 2. System Architecture & Constraints

### 2.1 Hardware & Software Stack
- Master library: `/Volumes/MUSIC/LIBRARY` (FLAC, 25k+ tracks)
- DJ USB target: `/Volumes/DJUSB` (MP3 320 CBR, Pioneer compatible)
- DJ analysis tools: Lexicon + Rekordbox
- Primary hardware: Pioneer XDJ (FLAC unsupported)
- OS context: macOS (volumes mounted locally)

### 2.2 Critical Constraints
- **Format constraint:** Pioneer XDJ does not support FLAC or ALAC. MP3 is the required output format.
- **Metadata constraint:** ID3v2.3 is preferred (BPM/TKEY compatibility).
- **Scale constraint:** 25k+ tracks is too large for full manual auditioning.
- **Curation constraint:** Track-level decisions matter (remixes, edits, versions).

### 2.3 Compatibility Matrix (Simplified)
- **Input:** FLAC (master library)
- **Analysis:** Lexicon (BPM, key, energy)
- **Export:** MP3 320 CBR
- **Playback:** Pioneer XDJ

---

## 3. Problem Statement

### 3.1 Format Gap
The master library is FLAC-only, but Pioneer hardware requires MP3. DJUSB contains FLAC files that are unplayable, representing a workflow break.

### 3.2 Curation Contamination
The DJUSB collection accumulates non-DJ tracks, snippets, and orphaned files. Without consistent curation, the set becomes unreliable for live use.

### 3.3 Mining Scale
The master library contains significant DJ-worthy material, but the volume (25k+ tracks) makes discovery and audition impractical without automation.

### 3.4 Metadata Inconsistency
Genre, BPM, and key are missing or inconsistent across files. This reduces utility in Rekordbox and Lexicon unless normalized.

### 3.5 Workflow Fragmentation
Historically, the workflow was split across scripts and manual steps, creating inconsistencies and duplication. Tagslut consolidates this into a single toolchain.

---

## 4. Goals and Non-Goals

### 4.1 Goals (G1–G6)
- **G1 - Format Pipeline:** Repeatable FLAC → MP3 conversion with preserved DJ tags.
- **G2 - Curation Quality:** Reduce non-DJ contamination with scoring + review buckets.
- **G3 - Scale:** Automate classification for 25k tracks with minimal false positives.
- **G4 - USB Readiness:** Pioneer-compatible USB output with correct metadata and paths.
- **G5 - Auditability:** Decisions are recorded and reproducible.
- **G6 - Operator Efficiency:** One-command daily/weekly sync with minimal manual steps.

### 4.2 Non-Goals
- Real-time waveform or beatgrid analysis (handled by Rekordbox/Lexicon).
- Replacing Lexicon or Rekordbox database logic.
- Automated creative decisions beyond clear DJ suitability signals.

---

## 5. Current Implementation (Tagslut)

### 5.1 Code Structure
- `tagslut/cli/commands`: Click command wrappers
- `tagslut/core`: scanning, hashing, matching
- `tagslut/decide`: deterministic planner
- `tagslut/exec`: execution engine
- `tagslut/metadata`: enrichment providers and pipeline
- `tagslut/dj`: curation, export, transcode, key detection, classifier
- `tools/`: operational scripts (e.g., DJUSB sync)

### 5.2 DJ Modules
- **Transcode:** `tagslut/dj/transcode.py` (FFmpeg MP3 320 CBR)
- **Key Detection:** `tagslut/dj/key_detection.py` (KeyFinder CLI)
- **Curation:** `tagslut/dj/curation.py` (filters + scoring)
- **Export:** `tagslut/dj/export.py` (curate → key detect → transcode)
- **Classifier:** `tagslut/dj/classify.py` (safe/block/review)
- **USB Sync:** `tools/dj_usb_sync.py` (classify + promote + report)

---

## 6. DJ Pipeline Details

### 6.1 Input Sources
- XLSX manifests (e.g., `/Users/georgeskhawam/Desktop/DJ_YES.xlsx`)
- Folder scans (e.g., `/Volumes/MUSIC/LIBRARY`)
- M3U/M3U8 playlists

### 6.2 Scoring Model
Signals and weights (current implementation):
- **BPM 120–135** → +3
- **BPM outside 100–175** → -2
- **Duration 240–480s** → +1
- **Duration <120s or >720s** → -2
- **Trusted remix** (remixer appears in library) → +2
- **DJ-positive genres** (house, tech house, techno, melodic house & techno, indie dance) → +2
- **Anti-DJ genres** (classical, spoken word, ambient, pop) → -3

Decision thresholds:
- **Score ≥ 4** → safe
- **Score ≤ -2** → block
- **Else** → review

### 6.3 Outputs
- **Overrides:** `config/dj/track_overrides.csv`
- **Crates:** `config/dj/crates/safe.m3u8`, `review.m3u8`
- **USB Output:** `/Volumes/DJUSB` MP3s
- **Sync Report:** `/Volumes/DJUSB/sync_report.csv`

---

## 7. Data Model & Artifacts

### 7.1 Database
- `tag_hoard_files`: raw per-file tag dump (`tags_json`)
- Provider enrichment tables (Beatport/Tidal/Deezer)

### 7.2 Files
- `config/dj/track_overrides.csv`
- `config/dj/crates/*.m3u8`
- `output/` and `artifacts/` (generated outputs)

### 7.3 Metadata Preservation
- MP3 transcode uses `-map_metadata 0` and ID3v2.3.
- Output paths mirror artist/album structure.

---

## 8. Operational Workflow (Step-by-Step)

### 8.1 Daily/Weekly Sync
1. Add new FLACs to `/Volumes/MUSIC/LIBRARY`.
2. Optional: `tagslut index register` to update DB inventory.
3. Optional: `tagslut index enrich --hoarding` for provider metadata.
4. Run classification:
   - `tagslut dj classify --input /Volumes/MUSIC/LIBRARY --output-crates --append-overrides`
5. Promote safe tracks:
   - `tagslut dj classify --input /Volumes/MUSIC/LIBRARY --promote --output-root /Volumes/DJUSB`
6. Import into Lexicon/Rekordbox for beatgrid/cue analysis.

### 8.2 Review Loop
- Review `config/dj/crates/review.m3u8`
- Promote only after manual confirmation

---

## 9. Command Reference

### Classification
```
poetry run tagslut dj classify --input /Volumes/MUSIC/LIBRARY --output-crates --append-overrides
```

### Promotion (Transcode)
```
poetry run tagslut dj classify --input /Volumes/MUSIC/LIBRARY --promote --output-root /Volumes/DJUSB --jobs 4
```

### DJ USB Orchestrator
```
python tools/dj_usb_sync.py --source /Volumes/MUSIC/LIBRARY --usb /Volumes/DJUSB --policy config/dj/dj_curation.yaml
```

### Metadata Enrichment
```
poetry run python -m tagslut _metadata enrich --db <db> --path "/Volumes/MUSIC/LIBRARY/%" --hoarding --execute
```

---

## 10. Known Gaps and Risks
- Pioneer finalize steps not yet automated (ID3v2.3 enforcement, artwork cap, path sanitization, Rekordbox copy).
- `tagslut dj export` hang still under investigation.
- Blocklist manager tool not yet implemented.
- Docs consolidation incomplete.

---

## 11. Roadmap
1. Pioneer finalize integration in `tools/dj_usb_sync.py`.
2. Blocklist manager tool (interactive add/analyze/bulk with fuzzy match).
3. CLI evacuation (Phase 2: reduce `cli/main.py`).
4. Architecture foundations (zones module, migrations cleanup, dependency trimming).
5. Docs consolidation to final structure.

---

## 12. Reference Inputs
- DJ_Library_Technical_Report.docx
- Tagslut Progress Report.docx
- Tagslut Restructuring Plan_ Phased Execution Guide.md
- Repository health audit notes (2026-02)
