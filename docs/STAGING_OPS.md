# Staging Ops Runbook

Standard procedure for clearing `/Volumes/MUSIC/staging` after a batch acquisition session.

## Safety / scope

- Do not delete audio files from staging as part of routine cleanup.
- Do not pass unknown or extensionless files to intake until they are identified (e.g., `tmp*` orphan files).

## Pre-intake

### 1) Remove macOS resource forks (`._*`)

Run before any intake pass:

```bash
find /Volumes/MUSIC/staging -name "._*" -delete
```

### 2) Identify `.m4a` codecs (lossless vs AAC)

Spot-check a file:

```bash
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of default=nk=1:nw=1 "/path/to/file.m4a"
```

Scan a staging subtree:

```bash
find /Volumes/MUSIC/staging/SpotiFLACnext -type f -iname '*.m4a' ! -name '._*' -print0 \
  | while IFS= read -r -d '' f; do
      codec="$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of default=nk=1:nw=1 "$f" | head -n 1 || true)"
      printf '%s\t%s\n' "${codec:-unknown}" "$f"
    done
```

Expected:
- `alac` or `flac`: lossless, safe to promote to FLAC.
- `aac`: lossy; decide whether to keep as-is or transcode to MP3 (lossy→lossy).

### 3) Transcode `.m4a` batches to intake-friendly formats

Use the repo scripts:

```bash
scripts/transcode_m4a_to_flac_lossless.sh \
  --scan-path /Volumes/MUSIC/staging/SpotiFLACnext \
  --lossy-to-mp3
```

Optional verification pass:

```bash
scripts/verify_transcodes.sh \
  --scan-path /Volumes/MUSIC/staging/SpotiFLACnext \
  --lossy-mp3
```

## Source-specific intake

### Ready-for-intake roots (FLAC/audio present, no SpotiFLAC log)

Use `process-root`:

```bash
poetry run tagslut intake process-root --root /Volumes/MUSIC/staging/bpdl --dry-run
poetry run tagslut intake process-root --root /Volumes/MUSIC/staging/bpdl
```

Typical candidates: beatportdl (`bpdl/`), streamrip (`StreamripDownloads/`), and one-off folders that already contain audio.

### SpotiFLACnext (new format)

1) Transcode `.m4a` in-place first (see Pre-intake).
2) Intake from the `.txt` log:

```bash
poetry run tagslut intake spotiflac "/Volumes/MUSIC/staging/SpotiFLACnext/<playlist>.txt" --dry-run
poetry run tagslut intake spotiflac "/Volumes/MUSIC/staging/SpotiFLACnext/<playlist>.txt"
```

Path resolution prefers adjacent `.m3u8` playlist files; prefer the non-`_converted` variant when both exist.

### SpotiFLAC (legacy)

When the log has no adjacent `.m3u8`, use `--base-dir` for path resolution:

```bash
poetry run tagslut intake spotiflac /Volumes/MUSIC/staging/SpotiFLAC/SpotiFLAC_*.txt \
  --base-dir /Volumes/MUSIC/staging/SpotiFLAC \
  --dry-run

poetry run tagslut intake spotiflac /Volumes/MUSIC/staging/SpotiFLAC/SpotiFLAC_*.txt \
  --base-dir /Volumes/MUSIC/staging/SpotiFLAC
```

### `tidal/` (mixed `.m4a`, `.flac`, `.mp3`, and `tmp*` orphans)

1) Transcode `.m4a` first:

```bash
scripts/transcode_m4a_to_flac_lossless.sh \
  --scan-path /Volumes/MUSIC/staging/tidal \
  --lossy-to-mp3
```

2) Do not intake `tmp*` until each file is identified (ffprobe) and either renamed to the correct extension or discarded if corrupt/incomplete.
3) Intake the root:

```bash
poetry run tagslut intake process-root --root /Volumes/MUSIC/staging/tidal --dry-run
poetry run tagslut intake process-root --root /Volumes/MUSIC/staging/tidal
```

### Apple Music exports (`Apple/`, MP3-only)

Do not attempt FLAC promotion. Route via an MP3-aware intake path:

```bash
poetry run tagslut intake process-root --root /Volumes/MUSIC/staging/Apple --dry-run
poetry run tagslut intake process-root --root /Volumes/MUSIC/staging/Apple
```

If using the dedicated MP3-to-sort staging workflow (`intake-mp3-to-sort-staging`), run that instead.

## Post-intake

### 1) Confirm DB registration

One lightweight pattern is to re-scan the staging root in dry-run mode and ensure there is nothing left that *would* be registered:

```bash
poetry run tagslut index register /Volumes/MUSIC/staging/bpdl --source bpdl
poetry run tagslut index register /Volumes/MUSIC/staging/tidal --source tidal
```

### 2) Confirm staging is clear

- Ensure each processed staging directory is empty (or contains only expected non-audio leftovers such as `.m3u8`).
- Move/archive playlist-only remnants as desired (do not delete audio as part of routine cleanup).

## Known hazards

- SpotiFLACnext path template bug: stray `({year)]` placeholder directories; clean empty placeholders but keep any real audio.
- `tmp*` orphan files (extensionless): verify with `ffprobe` before renaming or discarding.
- `._*` resource forks: delete early (see Pre-intake) to avoid confusing scans and intake.
