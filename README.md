# Recovery-First FLAC Deduplication

This repository is a recovery-first, evidence-preserving toolkit for scanning, auditing, and deduplicating large FLAC libraries. The workflow is **deterministic**, **resumable**, and **non-destructive** unless you explicitly approve changes.

## 🛠️ Project Structure

*   **`dedupe/`** — **The Engine**: Core library containing the unified CLI, hashing tiers, metadata extraction, and storage logic.
*   **`legacy/tools/`** — **Archived Workbench**: Legacy operational scripts kept for reference.
*   **`docs/`** — **The Library**: Technical manuals, system architecture, and archived history.

---

## 🚀 Quickstart (Current)

1. **Configure**: copy `.env.example` to `.env`, then `source .env`.
2. **Register new downloads**:
   - `poetry run dedupe index register <path> --source <bpdl|tidal|qobuz|legacy>`
3. **Pre-check duplicates before new ingest**:
   - `poetry run dedupe index check <path> --source <source>`
4. **One-command download + fast intake planning**:
   - `poetry run dedupe intake run --batch-root /Volumes/DJSSD/beatport <beatport-or-tidal-url>`
   - Underlying orchestrator: `tools/get-intake`
   - For Beatport URLs, this now runs a fast metadata prefilter against `/Volumes/MUSIC/LIBRARY` before downloading (skip with `--skip-beatport-prefilter`).
   - To generate a merged Roon M3U in the library after intake: add `--m3u --m3u-dir /Volumes/MUSIC/LIBRARY`.
   - Add `--execute` to apply promote/stash/quarantine moves after planning.
5. **M3U-only modes (no intake pipeline)**:
   - From Beatport URL: `poetry run dedupe intake run --m3u-only --url <beatport-url> --db <db> --m3u-dir /Volumes/MUSIC/LIBRARY`
   - From playlist file: `poetry run dedupe intake run --m3u-only --playlist-file <file> --db <db> --m3u-dir /Volumes/MUSIC/LIBRARY`
   - Missing handling: `--missing-policy ask|report|skip|download`
6. **Generate M3U playlists (Roon)**:
   - `poetry run dedupe report m3u <path>`
7. **Run metadata enrichment**:
   - `poetry run dedupe index enrich --db <db-path> --recovery --execute`
8. **Check auth/provider status**:
   - `poetry run dedupe auth status`

For a script-by-script map (canonical vs legacy), see:
- `docs/SCRIPT_SURFACE.md`

---

## 📘 Essential Documentation

For detailed technical information, please refer to:
*   **[GUIDE.md](GUIDE.md)** — **Operator Guide**: Tiered hashing, keeper selection logic, and full workflow details.
*   **[docs/MGMT_MODE.md](docs/MGMT_MODE.md)** — **Management & Recovery Modes**: Inventory tracking, duplicate checking, M3U generation, and file operations.
*   **[docs/METADATA_WORKFLOW.md](docs/METADATA_WORKFLOW.md)** — **Metadata Workflow**: End-to-end enrichment flow, modes, providers, and CLI usage.
*   **[docs/V2_ARCHITECTURE.md](docs/V2_ARCHITECTURE.md)** — **System Design**: How the unified package and CLI are structured.
*   **[docs/SCRIPT_SURFACE.md](docs/SCRIPT_SURFACE.md)** — **Current Script Surface**: Canonical commands, legacy wrappers, and archive policy.
*   **[docs/RESTORATION_PLAN.md](docs/RESTORATION_PLAN.md)** — **Data Recovery**: Detailed procedures for restoring files and resolving path conflicts.
*   **[docs/ROON_INTEGRATION.md](docs/ROON_INTEGRATION.md)** — **Roon Guide**: Managing your canonical library for Roon compatibility.

---

## 🎵 BeatportDL as Upstream Tool

**BeatportDL (bpdl)** is used as an upstream download tool that feeds the dedupe pipeline. It handles:
- Downloading tracks from Beatport with rich metadata
- Directory organization via `sort_by_context` and `*_directory_template` settings
- Filename formatting via `track_file_template`

**BeatportDL does NOT generate M3U playlists.** M3U generation is handled by `dedupe report m3u` or `tools/review/promote_by_tags.py` after downloads are registered to the inventory.

See [tools/beatportdl/bpdl/README.md](tools/beatportdl/bpdl/README.md) for BeatportDL configuration details.
