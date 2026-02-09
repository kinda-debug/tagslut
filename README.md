# Tagslut (Formerly Dedupe)

This repository is a recovery-first, evidence-preserving toolkit for scanning, auditing, and deduplicating large FLAC libraries. The workflow is **deterministic**, **resumable**, and **non-destructive** unless you explicitly approve changes.

Primary CLI brand:
- `tagslut` (preferred)
- `dedupe` (compatibility alias)
- `taglslut` (typo-tolerant alias)

Rebrand runbook and command migration map:
- `docs/REBRAND_TAGSLUT_2026-02-09.md`

## 🛠️ Project Structure

*   **`dedupe/`** — **The Engine**: Core library containing the unified CLI, hashing tiers, metadata extraction, and storage logic.
*   **`legacy/tools/`** — **Archived Workbench**: Legacy operational scripts kept for reference.
*   **`docs/`** — **The Library**: Technical manuals, system architecture, and archived history.

---

## 🚀 Quickstart (Current)

1. **Configure**: copy `.env.example` to `.env`, then `source .env`.
2. **Register new downloads**:
   - `poetry run tagslut index register <path> --source <bpdl|tidal|qobuz|legacy>`
3. **Pre-check duplicates before new ingest**:
   - `poetry run tagslut index check <path> --source <source>`
4. **One-command download + fast intake planning**:
   - `poetry run tagslut intake run --batch-root /Volumes/DJSSD/beatport <beatport-or-tidal-url>`
   - Underlying orchestrator: `tools/get-intake`
   - Beatport convenience wrappers:
     - `tools/get <beatport-url>` = sync mode (download missing + build playlist)
     - `tools/get-sync <beatport-url>` = explicit sync mode
     - `tools/get-report <beatport-url>` = report-only (no download)
   - For Beatport URLs, this now runs a fast metadata prefilter against `/Volumes/MUSIC/LIBRARY` before downloading (skip with `--skip-beatport-prefilter`).
   - To generate a merged Roon M3U in the library after intake: add `--m3u --m3u-dir /Volumes/MUSIC/LIBRARY`.
   - Add `--execute` to apply promote/stash/quarantine moves after planning.
5. **M3U-only modes (no intake pipeline)**:
   - From Beatport URL: `poetry run tagslut intake run --m3u-only --url <beatport-url> --db <db> --m3u-dir /Volumes/MUSIC/LIBRARY`
   - From playlist file: `poetry run tagslut intake run --m3u-only --playlist-file <file> --db <db> --m3u-dir /Volumes/MUSIC/LIBRARY`
   - Missing handling: `--missing-policy ask|report|skip|download`
   - M3U filename defaults to the chart/playlist slug when URL context is available.
6. **Generate M3U playlists (Roon)**:
   - `poetry run tagslut report m3u <path>`
7. **Run metadata enrichment**:
   - `poetry run tagslut index enrich --db <db-path> --recovery --execute`
8. **Check auth/provider status**:
   - `poetry run tagslut auth status`

For a script-by-script map (canonical vs legacy), see:
- `docs/SCRIPT_SURFACE.md`

---

## 📘 Essential Documentation

For detailed technical information, please refer to:
*   **[GUIDE.md](GUIDE.md)** — **Operator Guide**: Canonical v3 workflow across intake/index/decide/execute/verify/report/auth.
*   **[docs/SCRIPT_SURFACE.md](docs/SCRIPT_SURFACE.md)** — **Current Script Surface**: Canonical commands, legacy wrappers, and archive policy.
*   **[docs/SURFACE_POLICY.md](docs/SURFACE_POLICY.md)** — **Surface Contract**: Command lifecycle, decommission policy, and validation gates.
*   **[docs/README.md](docs/README.md)** — **Docs Index**: Actively maintained runbooks and references.
*   **[docs/REDESIGN_TRACKER.md](docs/REDESIGN_TRACKER.md)** — **Program Tracker**: Current phase, milestones, and decision log.
*   **[docs/REBRAND_TAGSLUT_2026-02-09.md](docs/REBRAND_TAGSLUT_2026-02-09.md)** — **Rebrand Plan**: Name decision, command migration, and compatibility policy.
*   **[docs/PHASE5_LEGACY_DECOMMISSION.md](docs/PHASE5_LEGACY_DECOMMISSION.md)** — **Decommission Runbook**: Wrapper retirement status and gate criteria.
*   **[docs/PHASE5_VERIFICATION_2026-02-09.md](docs/PHASE5_VERIFICATION_2026-02-09.md)** — **Verification Evidence**: Phase 5 closure validation.
*   **[docs/archive/README.md](docs/archive/README.md)** — **Archive Index**: What is archived and where to find it.
*   **[docs/archive/legacy-workflows-2026-02-09/](docs/archive/legacy-workflows-2026-02-09/)** — **Archived Legacy Workflows**: Historical docs no longer part of active CLI flow.
*   **[docs/archive/inactive-docs-2026-02-09/](docs/archive/inactive-docs-2026-02-09/)** — **Archived Inactive Docs**: Reference notes kept outside active workflow surface.
*   **[docs/archive/inactive-root-docs-2026-02-09/](docs/archive/inactive-root-docs-2026-02-09/)** — **Archived Root Notes**: Superseded planning and handover docs moved out of repo root.

---

## 🎵 BeatportDL as Upstream Tool

**BeatportDL (bpdl)** is used as an upstream download tool that feeds the dedupe pipeline. It handles:
- Downloading tracks from Beatport with rich metadata
- Directory organization via `sort_by_context` and `*_directory_template` settings
- Filename formatting via `track_file_template`

**BeatportDL does NOT generate M3U playlists.** M3U generation is handled by `tagslut report m3u` or `tools/review/promote_by_tags.py` after downloads are registered to the inventory.

See [tools/beatportdl/bpdl/README.md](tools/beatportdl/bpdl/README.md) for BeatportDL configuration details.
