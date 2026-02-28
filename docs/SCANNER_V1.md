# Scanner v1 (Initial DB Build)

This document defines the goals, invariants, and phased implementation outline for the **first-run library scanner**.

## Why this exists
The library can contain corrupt, truncated, stitched, mis-tagged, duplicated, or otherwise untrusted audio files.
The scanner runs (ideally) once in non-disaster scenarios to build a DB that downstream workflows can trust.

## Core invariants
- **Instrumentation-only on first run:** no user overrides, pre-labels, whitelists, or manual classifications.
- **Read-only:** never modify, move, delete, retag, or rewrite source files.
- **Evidence-first:** every classification must store measurable evidence (durations, decode errors, checksums, etc.).
- **Resumable:** an interrupted scan must continue, not restart.
- **Path-independent memory:** metadata and evidence are keyed by checksum so knowledge survives file moves/deletions.

## Multi-ISRC policy
Real libraries sometimes contain **multiple ISRC values** in a single file's metadata.
- The scanner must **collect and store all ISRC candidates** (normalized list).
- The scanner must **not** choose a canonical ISRC when multiple candidates exist.
- ISRC-based dedupe is allowed only when the file has **exactly one** candidate and meets a confidence threshold.

## What gets stored (before any later discard)
The scanner does not delete files, but it must persist enough information to safely delete later via a separate decision/execution flow.

Minimum archive payload (keyed by checksum):
- Raw tag snapshot (verbatim)
- Technical snapshot (bit depth, sample rate, bitrate, codec/container)
- Durations (tagged + measured) and deltas
- ISRC candidates list
- Scan issues with evidence JSON (append-only)
- Path history

## Classification model
Each file gets:
- A **primary status** (`scan_status`) such as `CLEAN`, `CORRUPT`, `TRUNCATED`, `EXTENDED`, `DUPLICATE`.
- Zero or more **issues** in `scan_issues` (stackable), each with `{code, severity, evidence_json}`.

## Phased implementation outline

### Phase 1 — Schema & models
Add additive tables for scan runs, scan queue, issues, append-only metadata archive, and path history.
Add additive scan columns to `files`.

### Phase 2 — ISRC candidate extraction
Implement robust extraction/normalization that supports multiple values and garbage input.

### Phase 3 — Stage 0/1: Discovery + tags/tech + checksum
Discover supported audio files, extract raw tags and technical parameters, compute checksum + quality rank, write archive.

### Phase 4 — Stage 2: Validation (fast probes)
Use `ffprobe` for measured duration and `ffmpeg` edge decode probing (both mocked in tests).
Record duration mismatches and decode corruption as issues with evidence.

### Phase 5 — Classification + dedupe election
Compute identity confidence (instrumentation-only), derive primary status, and elect canonical copies deterministically.
No deletion.

### Phase 6 — Runner (resumable, single-writer)
Implement a scan runner that processes `scan_queue`, supports resume, and writes to SQLite safely.

### Phase 7 — CLI surface
Add `tagslut scan init|resume|status|issues`.

## Definition of done
- `poetry run pytest -v` green.
- `tagslut scan --help` works.
- Scanning a mixed fixture library produces expected issues and an archive record for every file.

*Last updated: 2026-02-28*
