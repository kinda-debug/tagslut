# AGENTS.md — Agent Guidance for dedupe Repo

## Philosophy

This repository manages a **music library deduplication and rebuild effort** following massive data loss. The project is fundamentally about **sanity, deduplication, and provenance**—not about any single tool.

### Project vs. Tools

- **The project is "dedupe"** — a comprehensive effort to rebuild a clean, well-organized, metadata-rich music library from a corrupted/duplicated legacy state.
- **bpdl (Beatport Downloader)** is one tool used for downloading DJ-critical tracks from Beatport with rich metadata.
- **Yate** is the manual precision tagger for edge cases and high-value material.
- **Custom scanning/hashing infrastructure** provides the inventory database, duplicate detection, and normalization layer.

**bpdl is a tool within this project, not the project itself.**

### Core Goals

1. **Rebuild from trusted sources**: Use Beatport (via bpdl) as the canonical source for DJ-critical material; treat fresh downloads as better than ambiguous legacy copies.
2. **Seed from post-loss downloads**: The ~1–2k tracks downloaded since the data loss event form the initial canonical core.
3. **Scanning + DB + normalization**: Fast, lightweight scanning with hashing and a metadata database to support deduplication and promotion decisions.
4. **DJ vs non-DJ separation**: Zero tolerance for errors in DJ material; relaxed standards for background listening.
5. **Strict structure**: Single predictable folder hierarchy with move-only semantics.

**Move-only policy**: All file operations must use MOVE semantics. No duplicate copies left behind; sources are removed only after verified moves. Temporary staging files are allowed but must be deleted after success.

---

## Areas for Improvement Checklist

Agents working on this repo should prioritize the following:

### Scanning & Database Infrastructure
- [ ] Implement fast, light hashing for duplicate detection
- [ ] Build/extend the inventory database (paths, hashes, metadata, provenance flags)
- [ ] Add artist name and genre normalization rules
- [ ] Create anomaly detection for items needing manual attention

### bpdl Config & Metadata
- [ ] Configure `sort_by_context: true` for organized directory output
- [ ] Set `*_directory_template` values (release, playlist, chart, label, artist)
- [ ] Configure `track_file_template` for consistent naming
- [ ] Define artwork/cover settings (`cover_size`, `keep_cover`)
- [ ] Set `track_exists` behavior (update/skip/overwrite/error)
- [ ] Future: Album/artist-level fetch capability

**Note:** BeatportDL does NOT have a `--m3u` flag. M3U generation is handled by `dedupe mgmt` or `tools/review/promote_by_tags.py`.

### Folder Structures & Canonical Paths
- [ ] Define canonical folder hierarchy (by label, genre, date, or hybrid)
- [ ] Update `downloads_directory` to reflect the chosen structure
- [ ] Document the folder structure in REPORT.md

### DJ vs Non-DJ Separation
- [ ] Create separate download paths or post-processing for DJ tracks
- [ ] Define tagging or naming convention to distinguish DJ-curated tracks
- [ ] Consider a `dj/` subfolder or separate config profile

### Yate Integration
- [ ] Document workflow for flagged items → Yate → re-scan
- [ ] Define when Yate should be used vs. automated tagging

### Redownload/Rebuild Automation
- [ ] Create a script to re-tag existing files with updated config
- [ ] Build a manifest system to track downloaded releases
- [ ] Add automation for periodic library refresh

### Documentation
- [ ] Keep REPORT.md updated with detailed decisions and rationale
- [ ] Use this AGENTS.md as the quick-reference for agents

---

## Dos and Don'ts for Agents

### ✅ DO:
- Read REPORT.md before making structural changes
- Preserve existing metadata mappings unless explicitly asked to change
- Use consistent naming conventions across all configs and scripts
- Test config changes on a small subset before bulk operations
- Use move-only operations (no copies); verify before removing sources
- Document any changes made in REPORT.md
- Use `dedupe mgmt --check` before downloading to avoid duplicates
- Use `dedupe recovery --no-move` (dry-run) before any actual moves
- Generate M3U playlists via `dedupe mgmt --m3u` (NOT via BeatportDL)
- Refer to `postman/bpdl/README.md` for BeatportDL directory settings (`sort_by_context`, `*_directory_template`)

### ❌ DON'T:
- Copy music files or leave duplicates behind
- Overwrite or delete music files without explicit confirmation
- Change the `downloads_directory` without updating related scripts
- Remove tag mappings that are actively used
- Create duplicate configs without clear purpose
- Assume folder structures—always verify with `find` or `ls` first
- Use `dedupe recovery --move` without first running `--no-move` to preview
- Skip the inventory check—always register downloads to the DB
- Bypass the M3U generation step when building the new library
- Assume BeatportDL has M3U generation (it does NOT—use `dedupe mgmt --m3u`)

---

## Management & Recovery Mode Guidelines

### Using `dedupe mgmt` (Management Mode)

Management mode maintains the central inventory and prevents duplicate downloads.

**Always:**
- Register new downloads: `dedupe mgmt --source <source> --register <path>`
- Check before downloading: `dedupe mgmt --check --source <source> <path>`
- Generate M3U for Roon: `dedupe mgmt --m3u [--merge] <path>` (or use `tools/review/promote_by_tags.py`)

#TODO: Implement M3U generation in `dedupe mgmt --m3u`
#TODO: Log every decision (checks, waivers, moves) to JSON audit log
#TODO: Implement interactive prompt when similar files exist (skip/download/replace)

**When prompted about similar files:**
- **Skip** if the existing file is from a trusted source (bpdl) and recent
- **Download anyway** if the new version has better quality (e.g., hi-res)
- **Replace** only if the existing file is from legacy/unknown source

### Using `dedupe recovery` (Recovery Mode)

Recovery mode handles file operations with strict move-only semantics.

**Always:**
- Preview first: `dedupe recovery --no-move <path>`
- Check the log output before committing
- Use `--rename-only` for normalization passes without relocation

**Move operations:**
- `--move` is required to actually move files (safe default is dry-run)
- Files are hash-verified before source removal
- All operations logged to JSON for auditability

**Exceptions to move-only:**
- Temporary staging directories (cleaned after success)
- M3U playlist files (these are generated, not moved)
- Log files (append-only, never moved)

---

## Tool Reference

| Tool | Role | When to Use |
|------|------|-------------|
| **dedupe CLI** | Scanning, hashing, DB, deduplication | Bulk library operations |
| **dedupe mgmt** | Inventory, duplicate check, M3U generation | Before/after downloads |
| **dedupe recovery** | File moves, renames, logging | Building canonical library |
| **bpdl** | Beatport download + metadata | DJ-critical tracks, catalog rebuilds |
| **Yate** | Manual precision tagging | Edge cases, high-value albums, anomalies |

---

## Reference

- **[REPORT.md](./REPORT.md)** — High-level strategy and rationale
- **[docs/MGMT_MODE.md](./docs/MGMT_MODE.md)** — Full mgmt/recovery mode specification
- **[docs/ZONES.md](./docs/ZONES.md)** — Zone system documentation
- **[postman/bpdl/README.md](./postman/bpdl/README.md)** — BeatportDL configuration reference

---

## BeatportDL Configuration Reference

BeatportDL directory layout is controlled by these settings in `beatportdl-config.yml`:

| Setting | Purpose |
|---------|---------|
| `sort_by_context` | Create directories for releases, playlists, charts, labels, artists |
| `sort_by_label` | Use label names as parent directories (requires `sort_by_context`) |
| `force_release_directories` | Create release dirs inside chart/playlist folders |
| `release_directory_template` | Template for release folder names |
| `playlist_directory_template` | Template for playlist folder names |
| `chart_directory_template` | Template for chart folder names |
| `label_directory_template` | Template for label folder names |
| `artist_directory_template` | Template for artist folder names |
| `track_file_template` | Template for track filenames |

**BeatportDL does NOT generate M3U playlists.** Use `dedupe mgmt --m3u` or `tools/review/promote_by_tags.py` instead.

See `postman/bpdl/README.md` for full documentation.