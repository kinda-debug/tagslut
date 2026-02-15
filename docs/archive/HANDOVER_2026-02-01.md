> **Status: Archived / superseded by MGMT_MODE.md**
> This document contains historical session notes. For current mgmt/recovery semantics, see [docs/MGMT_MODE.md](./docs/MGMT_MODE.md).

# Handover — tagslut Repo

Date: 2026-02-01

## Summary (This Session)

Designed and documented the **Management & Recovery Mode** system for the tagslut CLI:

- **`tagslut mgmt`** — Management mode for inventory tracking, duplicate checking, and M3U generation
- **`tagslut recovery`** — Recovery mode for file operations with move-only semantics

This supports the new strategy: **build a small, super-sanitized library from fresh downloads** rather than rescuing legacy chaos.

## Files Created/Updated

### New
- `docs/MGMT_MODE.md` — Full specification of mgmt/recovery commands, flags, workflows, DB schema, logging

### Updated
- `REPORT.md` — Added "Management & Recovery Modes" section describing the new commands and workflow
- `AGENTS.md` — Added do/don't guidance for mgmt/recovery modes, updated tool reference table

## Key Design Decisions

### CLI Structure
```
tagslut mgmt [options]       # -m shorthand
tagslut recovery [options]   # -r shorthand
```

### `tagslut mgmt` Features
- Central inventory DB tracking all audio files from multiple sources (bpdl, qobuz, tidal)
- Pre-download duplicate checking (`--check`) with interactive prompt
- M3U playlist generation (`--m3u`, `--merge`) for Roon-compatible import
- Source tracking (`--source bpdl|qobuz|tidal|legacy`)

### `tagslut recovery` Features
- `--move` / `--no-move` — Explicit flag required for actual moves (default: dry-run)
- `--rename-only` — Rename in place without relocation
- Full JSON/TSV logging of all operations
- Zone-aware moves (`--zone accepted|staging|etc`)

### M3U Generation (tagslut mgmt Responsibility)

**Important:** M3U generation is handled by `tagslut mgmt`, NOT by BeatportDL or other downloaders. BeatportDL does not have a `--m3u` flag.

- `tagslut mgmt --m3u` generates one playlist per item
- `--merge` combines into single session playlist
- **Always checks existing files first** to prevent re-downloading recent tracks
- Alternative: `tools/review/promote_by_tags.py` can also generate M3U playlists

## Inventory DB Schema Extensions
```sql
download_source TEXT      -- bpdl, qobuz, tidal, legacy
download_date TEXT        -- ISO timestamp
original_path TEXT        -- path at registration
canonical_path TEXT       -- final destination
isrc TEXT                 -- for similarity matching
fingerprint TEXT          -- chromaprint
m3u_exported TEXT         -- last M3U export timestamp
mgmt_status TEXT          -- new → checked → verified → moved
```

## Workflow: Building Sanitized Library

1. Download from Beatport/Qobuz/Tidal
2. Register to inventory: `tagslut mgmt --source X --m3u --check`
3. Review M3U in Roon, verify tracks
4. Move verified tracks: `tagslut recovery --move --zone accepted`
5. Repeat — inventory prevents re-downloads

## Previous Session Summary (2026-01-31)

- Implemented zone subsystem (`tagslut/utils/zones.py`)
- Centralized keeper selection (`tagslut/core/keeper_selection.py`)
- Added CLI commands: `show-zone`, `explain-keeper`, `enrich-file`
- Created clean branch: `clean-v2`
- Docs: `docs/ZONES.md`, `docs/STANDALONE_TOOLS.md`

## Suggested Next Steps

1. **Implement CLI stubs** for `tagslut mgmt` and `tagslut recovery` in `tagslut/cli/main.py`
2. **Extend DB schema** with inventory fields (see schema above)
3. **Create M3U generator** utility for Roon-compatible playlists
4. **Integrate with bpdl** — wrapper script or post-download hook
5. **Test workflow** with a small batch of fresh downloads

## Open Questions

- Should `tagslut mgmt` wrap the actual downloader, or just process post-download?
- M3U naming convention: by date, by source, by release?
- Similarity threshold default (currently 0.85) — tune based on testing?

---

## Clarifications (2026-02-01 Update)

- **BeatportDL does NOT have a `--m3u` flag.** M3U generation is a `tagslut mgmt` responsibility.
- BeatportDL directory layout is controlled by `sort_by_context` and `*_directory_template` settings in `tools/beatportdl/bpdl/beatportdl-config.yml`.
- See `tools/beatportdl/bpdl/README.md` for full BeatportDL configuration reference.
- See `docs/MGMT_MODE.md` for current mgmt/recovery semantics.