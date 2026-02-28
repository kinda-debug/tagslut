# REPORT.md — Project Strategy & Current State

## Status: Recovery Phase COMPLETE

**Phases 0–4 (Recovery): COMPLETE as of February 2026.**

This project was born from the total loss of a 2TB hi-res lossless music library. What started as a rescue operation — r-Studio raw recovery, corrupt file triage, multi-source re-download from Beatport, Tidal, and Qobuz — became a year-long build of the tooling needed to make that operation tractable. That phase is over. The library is rebuilt. The rescue artifacts are archived under `legacy/`.

**tagslut v2+ is a forward-looking collection management tool. All recovery-era framing is retired.**

---

## What tagslut Is Now

A management toolkit for large hi-res music libraries, built specifically for **audiophile DJs**.

It maintains a single authoritative master FLAC library, enforces quality gates on every incoming download, and automatically derives a Rekordbox-linked MP3 DJ pool from that master — without ever touching the master files themselves.

---

## The Core Invariant

```
Master FLAC Library  ←  single source of truth, backed up, never modified by DJ workflows
        ↓  (if dj_flagged=true)
    MP3 DJ Pool       ←  derived, always regenerable, Rekordbox-linked
```

Every download goes through the master library. The DJ pool is a read-only derivative. Nothing enters Rekordbox that isn't in the master first.

---

## Pre-Download Intelligence (Core Workflow)

The fundamental operation is **pre-download resolution**, not post-download deduplication.

```
receive playlist/track URL
        ↓
resolve track identifiers (ISRC → provider IDs → fuzzy fallback)
        ↓
diff against master library inventory
        ↓
build filtered download manifest:
  - NEW:     not in library → download
  - UPGRADE: in library at lower quality rank → download, replace master
  - SKIP:    in library at equal or better quality → skip entirely
        ↓
execute download (only new + upgrades)
        ↓
intake → register → export DJ pool MP3 if dj_flagged
```

A full playlist download never touches disk for tracks the library already has at equal or better quality.

---

## Identifier Resolution Chain

Track identity is resolved in priority order:

| Priority | Identifier | Notes |
|---|---|---|
| 1 | **ISRC** | Format-agnostic, canonical across all providers |
| 2 | Beatport ID | Exact match within Beatport catalog |
| 3 | Tidal ID | Exact match within Tidal catalog |
| 4 | Qobuz ID | Exact match within Qobuz catalog |
| 5 | Fuzzy match | artist + title + duration ±2s (last resort) |

ISRC is the primary key in the inventory DB. Provider IDs are secondary lookup columns. Fuzzy matching (`rapidfuzz`) is a fallback, never a primary.

---

## Quality Rank Model

Downloads proceed only when the source offers equal or better quality than what is already in the master library.

| Rank | Format | Threshold |
|---|---|---|
| 1 | FLAC 32bit+ / DSD | Studio master |
| 2 | FLAC 24bit/96kHz+ | Hi-res lossless |
| 3 | FLAC 24bit/44.1kHz | Standard hi-res |
| 4 | FLAC 16bit/44.1kHz | CD quality lossless |
| 5 | AIFF/WAV 16bit | Uncompressed |
| 6 | MP3/AAC 320kbps | Lossy high |
| 7 | MP3/AAC <320kbps | Lossy degraded |

An incoming file at rank 3 replaces an existing file at rank 4. An incoming file at rank 4 is skipped if the library already holds rank 3.

---

## DJ Pool Export Contract

```
Master FLAC (immutable)
    ↓  tagslut export dj-pool --format mp3 --bitrate 320
    ↓  [only if dj_flag=true AND quality_rank ≤ 6]
MP3 DJ Pool
    ↓  filename: Artist - Title (Key) (BPM).mp3
    ↓  metadata: inherits ISRC, Beatport ID, label, BPM, key from FLAC master
Rekordbox import → analyzed → in crates
```

Key rules:
- Master FLAC is **never modified** by any DJ pool operation
- When master is upgraded (e.g. rank 4 → rank 2), the DJ pool MP3 is **automatically regenerated**
- Rekordbox is the terminal consumer — not a metadata source
- BPM and key analysis happens in Rekordbox; results are written back to master FLAC tags

---

## Canonical Command Surface (v2+)

```
tagslut intake    — pre-check + download orchestration (pre-download resolution)
tagslut index     — inventory management (register, check, enrich, duration-check)
tagslut decide    — quality-based planning (keep/upgrade/skip decisions)
tagslut execute   — move-only plan execution (never copies, never deletes without intent)
tagslut verify    — receipt and parity checks
tagslut report    — M3U, duration reports, DJ pool diff reports
tagslut auth      — provider credential management (Beatport, Tidal, Qobuz)
```

Retired (do not use):
- `dedupe` alias → retiring June 2026, use `tagslut`
- `mgmt`, `recover`, `scan`, `recommend`, `apply`, `promote`, `quarantine` → all retired

---

## Active Integrations

| Integration | Role | Status |
|---|---|---|
| Beatport | Primary download source, Beatport IDs | Active |
| Tidal | Hi-res lossless source, Tidal IDs | Active |
| Qobuz | Hi-res lossless source, Qobuz IDs | Active |
| Rekordbox | Terminal DJ pool consumer | Active (XML / via export) |
| Roon | Hi-fi listening library | Active (roonapi) |
| Yate | Manual precision tagger for edge cases | Active (external) |

---

## What Is Not This Tool

- Not a music player
- Not a streaming client
- Not a recommendation engine
- Not a general-purpose deduplicator (it is opinionated about music libraries specifically)
- Not a recovery tool (that phase is over — see `legacy/` for recovery-era artifacts)

---

## Open Architecture Decisions

These are tracked as issues and require explicit decisions before implementation:

1. **ISRC as primary DB key** — schema migration required (`tagslut/migrations/`)
2. **Flask web UI** — declared but never implemented. Intended use: local DJ pool browser / collection dashboard. Decision needed: build it or remove the dependency.
3. **Rekordbox sync mechanism** — direct XML manipulation vs. third-party bridge
4. **Zone model** — legacy zones (GOOD/BAD/QUARANTINE) should be replaced with (LIBRARY/DJPOOL/ARCHIVE) to match the new management framing

---

*Last updated: February 2026. Author: Georges Khawam.*
