# feat(intake): ingest SpotiFLAC batch output into tagslut pipeline

## Do not recreate existing files. Do not modify schema.py directly.

## Context

SpotiFLAC produces three output files per batch that together form a complete intake
manifest. Tagslut needs a command to ingest these and run each downloaded FLAC through
the standard intake pipeline (identity resolution → enrich → transcode → admit).

Output files:
1. **Main log** (`SpotiFLAC_YYYYMMDD_HHMMSS.txt`) — timestamped structured log
2. **Failed report** (`SpotiFLAC_YYYYMMDD_HHMMSS_Failed.txt`) — per-track errors
3. **M3U8 playlist** (`{PlaylistName}.m3u8`) — relative paths to downloaded FLACs

## Log format specification

Line format: `[HH:MM:SS] [level] message`
Levels: `debug`, `error`, `success`, `info`, `warning`

**ISRC extraction:** SpotiFLAC always tries Qobuz first. The Qobuz error line always
contains the ISRC — present for every track regardless of which provider succeeded:
```
[HH:MM:SS] [error] qobuz error: track not found for ISRC: US83Z2476192
[HH:MM:SS] [debug] trying tidal for: Track Title - Artists
```
Associate each ISRC with the display_title on the next `trying {provider} for:` line.

**Provider success:**
```
[HH:MM:SS] [success] tidal: Track Title - Artists
[HH:MM:SS] [success] downloaded: Track Title - Artists
```

**Failed track:** `[HH:MM:SS] [error] failed: Track Title - Artists`

**Failed report format:**
```
N. Track Title - Mix - Artists (Album)
   Error: [Qobuz] message | [Tidal] message | [Amazon] message
```

**M3U8 format:** Paths relative to M3U8 parent with leading `../`:
```
#EXTM3U
../Playlist Name/Artists/[Year] Album/Track Title - Artists.flac
```
Resolve absolute paths as: `Path(m3u8_path).parent / relative_path`

## Step 1 — Read existing code first

Before writing any code, read:
1. The existing intake pipeline entry point (how a downloaded FLAC is handed to
   indexing/identity resolution)
2. How `ingestion_method`, `ingestion_source`, `ingestion_confidence` are written
3. How the `files` table is populated from a FLAC path (the index step)

## Step 2 — Parser module

Create `tagslut/intake/spotiflac_parser.py` (new file).

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ProviderName = Literal["tidal", "qobuz", "amazon", "unknown"]

@dataclass
class SpotiflacTrack:
    display_title: str       # "Track - Artists" as logged by SpotiFLAC
    isrc: str | None         # from qobuz error line
    provider: ProviderName   # which provider delivered the file
    file_path: Path | None   # resolved absolute path from M3U8
    failed: bool
    failure_reason: str | None
```

Functions to implement:

`parse_log(log_path: Path) -> list[SpotiflacTrack]`
- Buffer most recent ISRC from qobuz error lines
- Associate buffered ISRC with display_title on next `trying {provider} for:` line
- Mark succeeded on `downloaded:` line, failed on `failed:` line

`parse_m3u8(m3u8_path: Path) -> dict[str, Path]`
- Strip leading `../`, resolve relative to m3u8_path.parent
- Key is filename stem (without .flac) for matching

`parse_failed_report(failed_path: Path) -> dict[str, str]`
- Returns dict mapping display_title to raw error string

`build_manifest(log_path, m3u8_path=None, failed_path=None) -> list[SpotiflacTrack]`
- Combines all three sources
- Match log titles to M3U8 stems: exact first, then normalized (strip punctuation,
  lowercase) if no exact match
- Auto-detect: look for `_Failed.txt` and `.m3u8` siblings with same timestamp prefix

Edge cases:
- ISRC absent if Qobuz was not attempted — guard for it
- Failed tracks still have ISRC from main log (they were attempted before failing)
- M3U8 stems may differ slightly from log titles — use normalized comparison


## Step 3 — CLI command

Add `tagslut intake spotiflac` to the intake command group.

```
tagslut intake spotiflac <log_file> [--base-dir <dir>] [--dry-run] [--failed-only]
```

- `log_file`: path to `SpotiFLAC_YYYYMMDD_HHMMSS.txt`
- `--base-dir`: root where SpotiFLAC wrote files. If omitted, infer from M3U8.
  Fail clearly if not resolvable.
- `--dry-run`: parse and print what would be ingested, write nothing
- `--failed-only`: report on failed tracks only (for retry planning), do not ingest

Command behavior:
1. Call `build_manifest(log_path)` — auto-detect M3U8 and _Failed.txt siblings
2. Print: `N tracks parsed, N with ISRC, N with resolved file path, N failed`
3. For each `failed=False` and `file_path is not None`:
   - Verify `file_path.exists()` — if not, log warning and skip
   - Hand FLAC path to existing intake pipeline (index step)
   - If ISRC available, inject as hint to identity resolution
   - Set provenance: `ingestion_method='spotiflac_import'`,
     `ingestion_source=f'spotiflac:{log_path.name}'`,
     `ingestion_confidence='high'`
   - Log: `[ingested] {title} ({isrc or "no ISRC"}) via {provider}`
4. For each `failed=True`, classify failure reason:
   - `"permission denied"` or `"input/output error"` → `[retryable]`
   - `"track not found"` across all providers → `[unavailable]`
   - Print: `[failed/{classification}] {title} — {failure_reason}`
5. Print: `N ingested, N skipped (file not found), N failed (N retryable)`

## Step 4 — Provenance vocabulary

Add `'spotiflac_import'` to the ingestion_method controlled vocabulary in
`docs/INGESTION_PROVENANCE.md`. Do not modify any SQL CHECK constraints.

## Step 5 — Tests

`tests/intake/test_spotiflac_parser.py` — use these fixtures directly in the file:

```python
SAMPLE_LOG = """\
[00:54:07] [debug] trying qobuz for: Urmel - okuma
[00:54:08] [error] qobuz error: track not found for ISRC: DEPQ62201210
[00:54:08] [debug] trying tidal for: Urmel - okuma
[00:54:48] [success] tidal: Urmel - okuma
[00:54:48] [success] downloaded: Urmel - okuma
[00:54:53] [debug] trying qobuz for: Low Battery - Atric, Frida Darko
[00:54:54] [error] qobuz error: track not found for ISRC: DEY472275018
[00:54:54] [debug] trying amazon for: Low Battery - Atric, Frida Darko
[00:54:55] [success] amazon: Low Battery - Atric, Frida Darko
[00:54:55] [success] downloaded: Low Battery - Atric, Frida Darko
[01:27:08] [debug] trying qobuz for: Wirrwarr - NUAH Remix - Air Horse One, NUAH
[01:27:09] [error] qobuz error: track not found for ISRC: US83Z2476192
[01:27:09] [debug] trying tidal for: Wirrwarr - NUAH Remix - Air Horse One, NUAH
[01:27:10] [error] tidal error: failed to write file: write /Volumes/SAD/...: input/output error
[01:27:10] [error] failed: Wirrwarr - NUAH Remix - Air Horse One, NUAH
"""

SAMPLE_M3U8 = """\
#EXTM3U
../Playlist/okuma/[2022] Urmel Kalkutta/Urmel - okuma.flac
../Playlist/Atric, Frida Darko/[2022] Low Battery/Low Battery - Atric, Frida Darko.flac
"""
```

Assert:
- `Urmel - okuma`: isrc=`DEPQ62201210`, provider=`tidal`, failed=False
- `Low Battery - Atric, Frida Darko`: isrc=`DEY472275018`, provider=`amazon`, failed=False
- `Wirrwarr - NUAH Remix - Air Horse One, NUAH`: isrc=`US83Z2476192`, failed=True,
  failure_reason contains `input/output error`, classified as `retryable`

## Commit sequence

```
feat(intake): add spotiflac log/m3u8/failed-report parser
feat(intake): add `tagslut intake spotiflac` command
docs(provenance): register spotiflac_import ingestion_method
test(intake): add spotiflac parser unit tests
```
