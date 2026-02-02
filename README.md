# Recovery-First FLAC Deduplication

This repository is a recovery-first, evidence-preserving toolkit for scanning, auditing, and deduplicating large FLAC libraries. The workflow is **deterministic**, **resumable**, and **non-destructive** unless you explicitly approve changes.

## 🛠️ Project Structure

*   **`dedupe/`** — **The Engine**: Core library containing the unified CLI, hashing tiers, metadata extraction, and storage logic.
*   **`legacy/tools/`** — **Archived Workbench**: Legacy operational scripts kept for reference.
*   **`docs/`** — **The Library**: Technical manuals, system architecture, and archived history.

---

## 🚀 Quickstart (V2)

1.  **Configure**: Copy `.env.example` to `.env` and update your volume paths and database location.
    ```bash
    source .env
    ```
2.  **Scan**: `python3 -m dedupe scan /path/to/music` (Builds your library index).
3.  **Recommend**: `python3 -m dedupe recommend --output plan.json` (Finds duplicates).
4.  **Apply**: `python3 -m dedupe apply plan.json --confirm` (Quarantines duplicates).

If you want the **clean, start-over workflow** (trust-based scan, metadata recovery, canonized promotion), follow:
- `docs/WORKFLOW_METADATA.md`

---

## 📘 Essential Documentation

For detailed technical information, please refer to:
*   **[GUIDE.md](GUIDE.md)** — **Operator Guide**: Tiered hashing, keeper selection logic, and full workflow details.
*   **[docs/MGMT_MODE.md](docs/MGMT_MODE.md)** — **Management & Recovery Modes**: Inventory tracking, duplicate checking, M3U generation, and file operations.
*   **[docs/METADATA_WORKFLOW.md](docs/METADATA_WORKFLOW.md)** — **Metadata Workflow**: End-to-end enrichment flow, modes, providers, and CLI usage.
*   **[docs/V2_ARCHITECTURE.md](docs/V2_ARCHITECTURE.md)** — **System Design**: How the unified package and CLI are structured.
*   **[docs/RESTORATION_PLAN.md](docs/RESTORATION_PLAN.md)** — **Data Recovery**: Detailed procedures for restoring files and resolving path conflicts.
*   **[docs/ROON_INTEGRATION.md](docs/ROON_INTEGRATION.md)** — **Roon Guide**: Managing your canonical library for Roon compatibility.

---

## 🎵 BeatportDL as Upstream Tool

**BeatportDL (bpdl)** is used as an upstream download tool that feeds the dedupe pipeline. It handles:
- Downloading tracks from Beatport with rich metadata
- Directory organization via `sort_by_context` and `*_directory_template` settings
- Filename formatting via `track_file_template`

**BeatportDL does NOT generate M3U playlists.** M3U generation is handled by `dedupe mgmt` or `tools/review/promote_by_tags.py` after downloads are registered to the inventory.

See [tools/beatportdl/bpdl/README.md](tools/beatportdl/bpdl/README.md) for BeatportDL configuration details.
