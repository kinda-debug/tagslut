# dedupe Tooling Usage Guide

This guide summarizes the updated command-line interfaces for the audio
deduplication and repair helpers.

## Prerequisites

* Python 3.11+.
* [Chromaprint `fpcalc`](https://acoustid.org/chromaprint) on ``PATH`` for
  fingerprint generation.
* [`ffmpeg`](https://ffmpeg.org/) for decoding/transcoding and playlist repair.
* [`flac`](https://xiph.org/flac/) is optional but can speed up some validation
  and repair fallbacks.

## `dd_flac_dedupe_db.py`

Run a dedupe scan against the music library. Example:

```bash
python dd_flac_dedupe_db.py --root /Volumes/dotad/MUSIC --workers 6 --skip-broken
```

### Diagnostics

* Diagnostic dumps default to ``/Volumes/dotad/.dedupe_diagnostics``. If the
  directory is not writable the tool falls back to
  ``$XDG_RUNTIME_DIR/dedupe_diagnostics`` (or the system temp directory). Use
  ``--diagnostic-root`` to override the location.
* Fingerprint, decode, and watchdog dumps are enabled by default. Toggle with
  ``--no-dump-fpcalc``, ``--no-dump-decode``, or ``--no-dump-watchdog``. You can
  re-enable with the corresponding ``--dump-*`` flag.
* Inspect the latest fingerprint dump without scanning:

  ```bash
  python dd_flac_dedupe_db.py --fpcalc-dump-latest
  python dd_flac_dedupe_db.py --check-fpcalc  # Prints the most recent dump
  ```

### Broken playlists

* Broken files are appended to the playlist specified by ``--broken-playlist``
  (default: ``/Volumes/dotad/MUSIC/broken_files_unrepaired.m3u``).
* The dedupe run also populates ``_BROKEN_FILES.txt`` inside the scan root for
  downstream tooling.

## `repair_flacs.py`

Repairs FLAC files either from a playlist or a single path. The pipeline is
non-destructive unless ``--overwrite`` is explicitly set.

### Example commands

```bash
# Repair all files listed in the default broken playlist into a repair folder
python repair_flacs.py --output /Volumes/dotad/MUSIC/REPAIRED --capture-stderr

# Repair a single file with full pipeline and allow overwriting in-place
python repair_flacs.py --file /Volumes/dotad/MUSIC/broken/song.flac \
  --output /Volumes/dotad/MUSIC --overwrite --backup-dir /Volumes/dotad/MUSIC/BACKUPS
```

### Pipeline overview

1. Lenient ``ffmpeg`` transcode (respects ``--ffmpeg-args``).
2. Decode to WAV and re-encode to FLAC with size sanity checks.
3. Optional tail trim (default 10 seconds, configure via ``--trim-seconds``).

Disable individual stages with ``--disable-transcode``, ``--disable-reencode``,
or ``--disable-trim``. Intermediate files live in a temporary directory; use
``--temp-dir`` to reuse a persistent location. Per-step stderr logs are written
under ``<output>/logs`` when ``--capture-stderr`` is provided. Log filenames are
sanitized and include a deterministic short hash to avoid collisions.

When ``--overwrite`` is used the original file is backed up (optionally into
``--backup-dir``) before repair attempts begin. Failed runs automatically restore
the backup.

## `make_broken_playlist.py`

Convert ``_BROKEN_FILES.txt`` into an M3U playlist:

```bash
python make_broken_playlist.py --root /Volumes/dotad/MUSIC

# Custom input/output
python make_broken_playlist.py --input /tmp/custom_broken.txt \
  --output /tmp/custom_playlist.m3u
```

The script defaults to ``<root>/_BROKEN_FILES.txt`` as input and writes the
playlist to ``<root>/broken_files_unrepaired.m3u``.
