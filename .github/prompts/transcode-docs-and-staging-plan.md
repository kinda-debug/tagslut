# transcode-docs-and-staging-plan

## Do not recreate or overwrite any existing files without reading them first.
## Do not run the full test suite.

---

## Part 1 — Document the transcode scripts

### Context

Two scripts exist at `/Users/georgeskhawam/Projects/tagslut/scripts/`:

- `transcode_m4a_to_flac_lossless.sh`
- `verify_transcodes.sh`

Read both scripts in full before writing any documentation.

### Task

Add both scripts to `docs/SCRIPT_SURFACE.md`. Read the file first to find the correct
insertion point (likely the `tools/` or `scripts/` section). Add an entry for each
script with: path, purpose, flags, and one-line example. Do not rewrite the file —
use targeted `edit_block` to insert only the new entries.

Add both scripts to `CHANGELOG.md` under an appropriate entry (check the file first for
the current format). If the changelog uses sections like `## Unreleased` or date headers,
insert there. If no unreleased section exists, add one.

Commit:
```
docs(scripts): document transcode_m4a_to_flac_lossless and verify_transcodes in SCRIPT_SURFACE and CHANGELOG
```

---

## Part 2 — Staging triage plan

### Current state of /Volumes/MUSIC/staging (surveyed 2026-04-13)

The following directories need action. Read this carefully — different dirs need
different treatment.

#### A. Ready for `tagslut intake process-root` (FLAC/audio present, no log file)

These dirs contain FLAC files with no SpotiFLAC log. Use `tagslut intake process-root`.

| Directory | Contents | Notes |
|-----------|----------|-------|
| `bpdl/` | 92 .flac, 3.95GB | beatportdl output, flat layout |
| `StreamripDownloads/` | 84 .flac, 4.50GB | streamrip output, mixed layout |
| `This Is bbno$/` | 45 .flac, 0.81GB | SpotiFLACnext playlist output folder |
| `Groove It Out EP/` | 3 .flac, 0.07GB | |
| `Pareidolia (feat. Amanda Zamolo) [Frazer Ray Remix]/` | 1 .flac, 0.09GB | |
| `Sounds Of Blue (Gui Boratto Remix)/` | 2 .flac, 0.12GB | |

#### B. SpotiFLACnext output — requires transcode first, then intake

`SpotiFLACnext/` contains 59 .m4a and 56 .flac (5.22GB total).
The .m4a files are a mix of FLAC-in-M4A (codec=flac) and AAC.
AAC files are 5× AAC-LC ~262–274 kbps (Apple Music quality) — acceptable for 320k MP3 DJ use.
These must be transcoded before intake:

```bash
# ALAC→FLAC + AAC-LC→MP3 (5 files, ~262–274 kbps LC — quality acceptable)
scripts/transcode_m4a_to_flac_lossless.sh \
  --scan-path /Volumes/MUSIC/staging/SpotiFLACnext \
  --lossy-to-mp3
```

After transcoding, run intake via `tagslut intake spotiflac` using the `.txt` log at
`/Volumes/MUSIC/staging/SpotiFLACnext/Berlin Underground Selection (Finest Electronic Music).txt`.
The M3U8 for path resolution is `Berlin Underground Selection (Finest Electronic Music).m3u8`
(prefer non-`_converted` variant).
For `This Is Purple Disco Machine` playlist use its own `.m3u8`.

#### C. SpotiFLAC (old format) — ready for intake now

Two log files exist with no adjacent M3U8 — use `--base-dir` for path resolution:

```bash
tagslut intake spotiflac \
  /Volumes/MUSIC/staging/SpotiFLAC/SpotiFLAC_20260403_015329.txt \
  --base-dir /Volumes/MUSIC/staging/SpotiFLAC \
  --dry-run

tagslut intake spotiflac \
  /Volumes/MUSIC/staging/SpotiFLAC/spotiflac_20260403_170006.txt \
  --base-dir /Volumes/MUSIC/staging/SpotiFLAC \
  --dry-run
```

Drop `--dry-run` once path resolution looks correct.

#### D. tidal/ — mixed, needs transcode

`tidal/` contains 49 .m4a (26 FLAC-in-M4A + 23 AAC), 8 .flac, 9 .mp3 (2.49GB).
Also 31 `tmp*` extensionless files (orphaned atomic-write temps from tiddl/SpotiFLAC
interrupted runs — mix of m4a and flac containers).

AAC breakdown (23 files):

- **22 files @ 96kbps HE-AAC** — low-quality streaming tier (Danny Howells, Kim Ann Foxman,
  Fred Everything, Blue 6, etc.). HE-AAC 96k → MP3 320k is a quality loss, not a gain.
  **Do not transcode. Leave untouched. Flag for re-acquisition from TIDAL lossless or Qobuz.**
- **1 file @ 320kbps AAC-LC** — `The Man With The Red Face (Video).m4a`. Acceptable quality.
  Include with `--lossy-to-mp3` if DJ pool inclusion is desired; otherwise skip.

Transcode .m4a (ALAC→FLAC only; omit `--lossy-to-mp3` to leave 96k HE-AAC files untouched):

```bash
# ALAC→FLAC only — the 22 HE-AAC 96k files will be skipped automatically
scripts/transcode_m4a_to_flac_lossless.sh \
  --scan-path /Volumes/MUSIC/staging/tidal
```

If `The Man With The Red Face (Video).m4a` (320k LC) is wanted in the DJ pool, transcode
it separately or move it aside and run with `--lossy-to-mp3` scoped to that file only.

After transcode, intake via `tagslut intake process-root --root /Volumes/MUSIC/staging/tidal`.

The `tmp*` files: check each with ffprobe and either rename with correct extension or
delete if corrupt/incomplete. Do not pass them to intake without renaming.

#### E. Apple/ — MP3s + metadata, different pipeline

`Apple/` contains 136 .mp3, 50 .jpg, 109 .lrc (1.72GB). These are Apple Music exports.
Route through `tagslut intake process-root` with mp3-aware flags, or the
`intake-mp3-to-sort-staging` command if appropriate. Do not attempt FLAC promotion.

#### F. mp3_to_sort_intake/ — 38 MP3s

Use `tagslut intake process-root` or `intake-mp3-to-sort-staging`. 0.51GB.

#### G. Empty / stale / orphan directories — safe to remove after confirming

These directories contain only M3U8 playlist files or empty artist folder skeletons
(SpotiFLACnext wrote the directory structure but audio failed to download):

- `Blaze Away (Deluxe Version)/` — 0 audio files, just .m3u8 + empty artist subdirs
- `Top Streamed Tracks 2025 Downtempo/` — 0 audio files, just .m3u8 + empty artist subdirs
- `Miami Bass EP/` — empty
- `Deep & Minimal/` — 1 .flac (Jake Antonio "goes like this"), rest are empty `({year)]`
  placeholder dirs. Keep the 1 FLAC, clean empty dirs.
- `tiddl/Electronic Classics/` — empty dir
- `qobuz-dl/` — empty
- `tdn/` — 4 .lrc + 1 .m3u + 2 noext (Playlists subfolder). These are TDN playlist
  exports. Not audio — safe to delete or archive.

#### H. Ghost files

546 `._*` macOS resource fork files identified across staging. Clean them:
```bash
find /Volumes/MUSIC/staging -name "._*" -delete
```
Run this before any intake pass.

---

## Part 3 — Write the staging ops runbook

Create a new file `docs/STAGING_OPS.md` documenting the standard procedure for
clearing staging after a batch acquisition session. Read existing docs files first
to match formatting conventions (use `list_directory /Users/georgeskhawam/Projects/tagslut/docs`
and read any relevant existing docs).

The runbook must cover:
1. Pre-intake: ghost file cleanup, m4a codec detection, transcode step
2. Source-specific intake commands (SpotiFLACnext, SpotiFLAC legacy, tiddl, bpdl,
   streamrip, Apple Music MP3s)
3. Post-intake: verify DB registration, confirm staging dirs emptied
4. Known hazards: `({year)]` template bug in SpotiFLACnext paths, `tmp*` orphan files,
   `._*` resource forks

Commit:
```
docs(staging): add STAGING_OPS runbook with intake procedures per source type
```

---

## Part 4 — Codex must not

- Touch any volume-mounted files directly (no writes to /Volumes/)
- Delete any audio files from staging
- Run intake commands — document the commands only; operator runs them
- Modify `tagslut/storage/v3/schema.py` or any migration files

---

## Final commit order

1. `docs(scripts): document transcode scripts`
2. `docs(staging): add STAGING_OPS runbook`

Use targeted `edit_block` for SCRIPT_SURFACE.md and CHANGELOG.md. Create STAGING_OPS.md
as a new file. No other files modified.
