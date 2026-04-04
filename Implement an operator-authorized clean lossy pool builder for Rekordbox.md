# Implement an operator-authorized clean lossy pool builder for Rekordbox

## Status

Implemented.

Delivered:
- standalone script: `tools/centralize_lossy_pool`
- focused tests: `tests/tools/test_centralize_lossy_pool.py`
- operator docs updated in `docs/OPERATOR_QUICK_START.md` and `docs/WORKFLOWS.md`

Observed operator result:
- clean pool built at `/Volumes/MUSIC/MP3_LIBRARY_CLEAN`
- archive run at `/Volumes/MUSIC/_archive_lossy_pool/MP3_LIBRARY_CLEAN_20260403_212500`
- final audit: `invalid_audio_count = 0`, `exact_duplicate_files = 0`
- unresolved `conflict_isrc_duration`: `116` files across `44` groups
- no lossy files remained outside `/Volumes/MUSIC/MP3_LIBRARY_CLEAN` and `/Volumes/MUSIC/_archive_lossy_pool/*`

Work from repo root.

Read first:
- `AGENT.md`
- `PROJECT_DIRECTIVES.md`
- `docs/CORE_MODEL.md`
- `docs/DB_V3_SCHEMA.md`

Do not redesign the system. Implement the smallest coherent patch set that satisfies this spec.

## Task

Add a new non-interactive Python CLI script:

`tools/centralize_lossy_pool`

This is a **derived export/normalization utility** for Rekordbox preparation, not a new source of canonical truth. The clean pool is a **derived clean lossy root** for Rekordbox import only. Canonical truth remains in the DB.

This task is explicitly operator-authorized to write to `/Volumes/MUSIC` for this workflow only.

## Merge note

This spec had an appended duplicate block under `# MERGE WITH:`. Treat that appended block as merge input, not as a second separate task.

The only substantive addition from that appended block is the sequencing constraint below. All other duplicated sections are already covered by the main spec and should remain unified here.

## Sequencing note

This task comes **before** the next DJ-facing work. After this lands, the next planned feature is:
- a Rekordbox starter workflow on top of the clean lossy pool
- with Lexicon added strictly as a **read-only helper layer** for review, playlist assistance, and inspection

Do not implement the Rekordbox workflow or Lexicon helper in this task. This task is only for producing the clean lossy pool safely and deterministically.

## Goal

Build one clean, deduped, Rekordbox-importable lossy library by **moving** in-scope files from:

`/Volumes/MUSIC`

into:

`/Volumes/MUSIC/MP3_LIBRARY_CLEAN`

Everything excluded, invalid, or deduped-out must be **moved** into a timestamped archive folder for rollback, with a machine-readable manifest.

## Scope and safety model

This utility is an **external operator utility**, not a DB-truth workflow. Do not add or modify any DB truth model for this task. Do not invent identity writes, move receipts, or provenance events in this implementation.

Do not:
- redefine canonical identity
- infer authoritative identity from paths
- retag files
- transcode audio
- write anywhere outside the specified destination/archive roots

## Locked decisions

- Destination root:
  - `/Volumes/MUSIC/MP3_LIBRARY_CLEAN`
- Archive root:
  - `/Volumes/MUSIC/_archive_lossy_pool/MP3_LIBRARY_CLEAN_<YYYYMMDD_HHMMSS>/`
- Source scope:
  - all subtrees under `/Volumes/MUSIC`, excluding `dest-root` and `archive-root`
- Centralize method:
  - move, not copy
- Default mode:
  - dry-run
- Apply mode:
  - execute
- Keep rules:
  - MP3: detected bitrate exactly 320 kbps
  - M4A: AAC codec and detected bitrate >= 256 kbps
- Cross-format duplicates:
  - prefer MP3 over AAC, but only with high-confidence duplicate evidence
- Bad tags:
  - if file is otherwise eligible but missing artist or title, archive it; do not guess
- Album fallback:
  - normal release with missing album -> `Singles`
  - compilation with missing album -> `Compilations/Singles`
- Destination preflight:
  - abort if `dest-root` exists and is non-empty

## CLI contract

Required:
- `--source-root /Volumes/MUSIC`
- `--dest-root /Volumes/MUSIC/MP3_LIBRARY_CLEAN`
- `--archive-root /Volumes/MUSIC/_archive_lossy_pool/MP3_LIBRARY_CLEAN_<stamp>`
- `--dry-run` or default dry-run behavior
- `--execute`

Optional but implemented and documented:
- `--mp3-kbps 320`
- `--aac-min-kbps 256`
- `--manifest <path>` defaulting under archive root
- `--duration-tolerance-seconds 2`
- `--limit-root <subpath>` for smoke testing
- `--resume` for continuing an interrupted execute run with the same roots
- `--verbose` for per-file planning / move / audit output

Rules:
- execution must require explicit `--execute`
- `--resume` is valid only with `--execute`
- dry-run must not create a final-looking executed archive tree; keep dry-run artifacts clearly separated from executed archive state
- fail loudly if required volumes are not mounted
- do not fall back to guessed local paths

## Scan rules

Include:
- regular files only
- extensions `.mp3`, `.m4a`

Exclude:
- symlinks
- hidden files and hidden directories
- anything under `dest-root`
- anything under `archive-root`

Implementation note:
- the hidden-path rule is literal. A directory name such as `...` is treated as hidden and is skipped unless renamed before the run.

Never follow symlinks.

## Media inspection rules

### MP3

Use `mutagen.mp3.MP3` / `MPEGInfo`.

Collect:
- bitrate
- bitrate mode
- duration
- sketchy parse flag

Eligibility:
- parse must succeed
- `sketchy` must be false
- bitrate must equal configured MP3 bitrate exactly

If parse fails, bitrate mismatches, or file is sketchy:
- archive with explicit reason

### M4A

Use `ffprobe`.

Collect:
- codec name
- duration
- bitrate

Bitrate lookup order:
1. audio stream codec
2. audio stream bitrate
3. format bitrate fallback only if stream bitrate is absent

Eligibility:
- codec must be `aac`
- bitrate must be >= configured AAC minimum

If codec is not AAC:
- archive with codec-policy reason

If bitrate remains unavailable after fallback:
- archive with explicit reason

Do not treat `.m4a` container as proof of AAC.

## Tags and path derivation

Use tags only to derive export layout, never as authoritative identity truth.

### Sanitization

Apply to all path segments and filenames:
- trim
- collapse whitespace
- strip trailing dots
- replace invalid characters `<>:"/\\|?*` with `_`

If a segment becomes empty after sanitization, use fixed fallbacks such as:
- `Unknown Artist`
- `Singles`
- `Compilations`

### Tag mapping

MP3 / ID3:
- Artist = `TPE1`
- Title = `TIT2`
- Album = `TALB`
- TrackNo = `TRCK`
- AlbumArtist = `TPE2`
- ISRC = `TSRC`
- Label = `TXXX:LABEL`, then fallback `TPUB`
- Compilation = `TCMP`

M4A / MP4:
- Artist = `©ART`
- Title = `©nam`
- Album = `©alb`
- TrackNo = `trkn`
- AlbumArtist = `aART`
- Compilation = `cpil`
- ISRC = `----:com.apple.iTunes:ISRC`
- Label = `----:com.apple.iTunes:LABEL`

### Required tags

If otherwise eligible by media policy:
- require artist
- require title

If missing:
- archive with `missing_required_tags`

### Compilation detection

Compilation is true if:
- MP3 `TCMP` is truthy, or album artist equals one of `Various Artists`, `VA`, `Various` case-insensitively
- M4A `cpil` is truthy, or album artist matches the same set

### Output layout

Normal release:
- `Artist/Album/<NN - >Title.ext`

Compilation / VA / label compilation:
- `Label/Album/<NN - >Artist - Title.ext`

If compilation label missing:
- `Compilations/Album/<NN - >Artist - Title.ext`

Track number:
- zero-pad to 2 digits if present
- omit prefix if absent

## Dedupe rules

The utility must avoid silently collapsing distinct edits or versions.

### 1. Exact duplicates

Safe auto-collapse by full-file hash.

Implementation:
- use `blake2b`
- treat size mismatch as hard nonduplicate
- hash only same-size candidate groups to reduce cost

For each exact-hash group:
- keep one canonical file
- archive others under duplicate reason

### 2. Cross-format duplicates

Only safe auto-collapse with strong evidence.

Identity rule:
- same normalized ISRC
- duration difference <= configured tolerance

If both are true:
- treat as same track
- prefer MP3 over AAC
- if no MP3 exists in group, keep best AAC

If ISRC matches but duration difference exceeds tolerance:
- do not dedupe
- record `conflict_isrc_duration`

Do not auto-collapse using artist/title/duration fuzzy matching alone.

## Deterministic canonical selection

Within a duplicate group, choose the canonical file in this order:

For ISRC groups:
1. prefer MP3 over AAC
2. prefer file with more complete metadata among:
   - album
   - track number
   - album artist
   - label
3. prefer larger filesize
4. lexical sort of full source path as final tie-break

For exact-hash groups:
- use steps 2 through 4 above

## Destination collision handling

If computed destination path already exists:
- if content hash matches, treat source as duplicate and archive it
- otherwise write as:
  - `<base>__<HASH8>.<ext>`

No overwrites.

## Disposition classes

Use explicit reasons/classes, not vague archive labels:

- `keep`
- `archive_duplicate_hash`
- `archive_duplicate_isrc`
- `conflict_isrc_duration`
- `invalid_media`
- `bitrate_policy_reject`
- `codec_policy_reject`
- `missing_required_tags`
- `path_collision_renamed`
- `error_unreadable`
- `dest_nonempty_abort`

## Behavior

### 1. Preflight

- abort if `dest-root` exists and is non-empty
- ensure source root exists
- validate volume availability
- exclude `dest-root` and `archive-root` from traversal
- in dry-run, write artifacts to a clearly marked dry-run artifact directory, not the final execute archive tree

Resume exception:
- on `--execute --resume`, allow an existing non-empty `dest-root` and an existing non-empty run artifact root, but keep using the same archive run and never overwrite destination files

### 2. Discovery pass

For each candidate file:
- collect path, size, extension
- inspect audio properties
- extract tags
- classify into:
  - keep candidate
  - exclusion class

### 3. Group and dedupe planning

- group keep-candidates by size, then hash where needed
- group ISRC-bearing candidates by normalized ISRC
- resolve exact duplicates
- resolve ISRC-safe cross-format duplicates
- leave ISRC conflicts uncollapsed and log them

### 4. Execute moves

Only with `--execute`.

For each canonical keeper:
- compute destination path
- ensure parent directories exist
- move source to destination

For each archived file:
- move into:
  - `<archive-root>/<reason>/<relative_path_from_source_root>`

Never delete.

### 5. Outputs

Write JSONL manifest with one row per source file containing at least:
- `source`
- `action`
- `dest`
- `archive`
- `reason`
- `ext`
- `size`
- `hash`
- `bitrate_kbps`
- `bitrate_source`
- `bitrate_mode`
- `codec`
- `duration_seconds`
- `sketchy`
- `isrc`
- extracted tags used for pathing

Print short stdout summary:
- total scanned
- kept
- archived
- counts by reason
- duplicate counts
- conflict counts

## Validation step

After execution, reuse existing validator in audit-only mode against:

`/Volumes/MUSIC/MP3_LIBRARY_CLEAN`

with manifests written under the archive run folder, not inside the repo.

Expected result:
- invalid audio == 0
- no exact duplicates remain
- any unresolved ISRC conflicts are visible in manifest output, not silently lost

## Operator runbook

1. Ensure destination root does not exist or is empty.
2. Run dry-run on full source or `--limit-root`.
3. Review summary and manifest.
4. Spot-check representative normal-release and compilation paths.
5. Run execute.
6. Run validator in audit-only mode on the clean pool.
7. Start fresh in Rekordbox using only `/Volumes/MUSIC/MP3_LIBRARY_CLEAN`.

## Tests

Use fixture/temp trees only.

Required tests:
- MP3 exact 320 accepted
- MP3 non-320 rejected
- MP3 unreadable/sketchy rejected
- AAC 256 and AAC 320 accepted
- AAC below threshold rejected
- non-AAC `.m4a` rejected
- exact duplicate archived
- ISRC-backed cross-format duplicate collapses safely
- ISRC same but duration conflict does not collapse
- missing artist/title archives file
- normal-release pathing works
- compilation pathing works
- collision suffixing is deterministic
- dry-run does not perform moves
- execute performs expected moves
- destination nonempty abort works

## Constraints

- no new Python dependencies unless absolutely necessary and documented
- no transcoding
- no retagging
- no fuzzy title-only duplicate collapse
- keep implementation narrow and operator-focused

## Deliverables

Return:
1. exact files changed
2. tests run and results
3. dry-run artifact format
4. execute artifact format
5. any follow-up risks or edge cases still needing manual operator review

For each candidate file:
- collect path, size, extension
- inspect audio properties
- extract tags
- classify into:
  - keep candidate
  - exclusion class

### 3. Group and dedupe planning

- group keep-candidates by size, then hash where needed
- group ISRC-bearing candidates by normalized ISRC
- resolve exact duplicates
- resolve ISRC-safe cross-format duplicates
- leave ISRC conflicts uncollapsed and log them

### 4. Execute moves

Only with `--execute`.

For each canonical keeper:
- compute destination path
- ensure parent directories exist
- move source to destination

For each archived file:
- move into:
  - `<archive-root>/<reason>/<relative_path_from_source_root>`

Never delete.

### 5. Outputs

Write JSONL manifest with one row per source file containing at least:
- `source`
- `action`
- `dest`
- `archive`
- `reason`
- `ext`
- `size`
- `hash`
- `bitrate_kbps`
- `bitrate_source`
- `bitrate_mode`
- `codec`
- `duration_seconds`
- `sketchy`
- `isrc`
- extracted tags used for pathing

Print short stdout summary:
- total scanned
- kept
- archived
- counts by reason
- duplicate counts
- conflict counts

## Validation step

After execution, reuse existing validator in audit-only mode against:

`/Volumes/MUSIC/MP3_LIBRARY_CLEAN`

with manifests written under the archive run folder, not inside the repo.

Expected result:
- invalid audio == 0
- no exact duplicates remain
- any unresolved ISRC conflicts are visible in manifest output, not silently lost

## Operator runbook

1. Ensure destination root does not exist or is empty.
2. Run dry-run on full source or `--limit-root`.
3. Review summary and manifest.
4. Spot-check representative normal-release and compilation paths.
5. Run execute.
6. Run validator in audit-only mode on the clean pool.
7. Start fresh in Rekordbox using only `/Volumes/MUSIC/MP3_LIBRARY_CLEAN`.

## Tests

Use fixture/temp trees only.

Required tests:
- MP3 exact 320 accepted
- MP3 non-320 rejected
- MP3 unreadable/sketchy rejected
- AAC 256 and AAC 320 accepted
- AAC below threshold rejected
- non-AAC `.m4a` rejected
- exact duplicate archived
- ISRC-backed cross-format duplicate collapses safely
- ISRC same but duration conflict does not collapse
- missing artist/title archives file
- normal-release pathing works
- compilation pathing works
- collision suffixing is deterministic
- dry-run does not perform moves
- execute performs expected moves
- destination nonempty abort works

## Constraints

- no new Python dependencies unless absolutely necessary and documented
- no transcoding
- no retagging
- no fuzzy title-only duplicate collapse
- keep implementation narrow and operator-focused

## Deliverables

Return:
1. exact files changed
2. tests run and results
3. dry-run artifact format
4. execute artifact format
5. any follow-up risks or edge cases still needing manual operator review
