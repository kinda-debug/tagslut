# Recovery-First FLAC Deduplication

This repository is a recovery-first, evidence-preserving toolkit for scanning, auditing, and deduplicating large FLAC libraries. The workflow is **deterministic**, **resumable**, and **non-destructive** unless you explicitly approve changes.

## 🛠️ Project Structure

*   **`dedupe/`** — **The Engine**: Core library containing the unified CLI, hashing tiers, metadata extraction, and storage logic.
*   **`legacy/tools/`** — **Archived Workbench**: Legacy operational scripts kept for reference.
*   **`docs/`** — **The Library**: Technical manuals, system architecture, and archived history.

---

## 🚀 Quickstart (V2)

1.  **Configure**: Copy `.env.example` to `.env` and update your volume paths and database location.
2.  **Scan**: `python3 -m dedupe scan /path/to/music` (Builds your library index).
3.  **Recommend**: `python3 -m dedupe recommend --output plan.json` (Finds duplicates).
4.  **Apply**: `python3 -m dedupe apply plan.json --confirm` (Quarantines duplicates).

---

## 📘 Essential Documentation

For detailed technical information, please refer to:
*   **[GUIDE.md](GUIDE.md)** — **Operator Guide**: Tiered hashing, keeper selection logic, and full workflow details.
*   **[docs/METADATA_WORKFLOW.md](docs/METADATA_WORKFLOW.md)** — **Metadata Workflow**: End-to-end enrichment flow, modes, providers, and CLI usage.
*   **[docs/V2_ARCHITECTURE.md](docs/V2_ARCHITECTURE.md)** — **System Design**: How the unified package and CLI are structured.
*   **[docs/RESTORATION_PLAN.md](docs/RESTORATION_PLAN.md)** — **Data Recovery**: Detailed procedures for restoring files and resolving path conflicts.
*   **[docs/ROON_INTEGRATION.md](docs/ROON_INTEGRATION.md)** — **Roon Guide**: Managing your canonical library for Roon compatibility.
