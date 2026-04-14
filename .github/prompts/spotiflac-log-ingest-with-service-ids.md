# spotiflac-log-ingest-with-service-ids

Do not recreate existing files. Read them first; modify only what is described.

## Context

Log to ingest: `/Users/georgeskhawam/Projects/tagslut/_ingest/spotiflac_logs/2026-04-14__08-56-21__spotiflac.log`

This is a legacy-format SpotiFLACnext log (timestamped `[HH:MM:SS] [level] msg`).
It contains two batches:

**Batch 1 — Spotify resolver mode**
- Album: *Peace Is The Mission : Extended*
- Source URL: `https://open.spotify.com/album/2U0b5MfkMUgzdvRUI69mya`
- 14 tracks. Providers: apple (10 tracks), tidal (4 tracks).
- Mode: `[debug] url: https://open.spotify.com/album/...`

**Batch 2 — Qobuz direct-link mode**
- Album: *Lazy Days Re:Mixed*
- Source URL: `https://open.qobuz.com/album/ldgvxrkvvvfpb`
- 10 tracks. Provider: qobuz (all).
- Mode: `[info] fetching direct link metadata...` + `[debug] url: https://open.qobuz.com/album/...`

---

## Part 1 — Parser changes (`tagslut/intake/spotiflac_parser.py`)

### 1.1 Add `album_source_url: str | None` to `SpotiflacTrack`

Add this field to the dataclass with default `None`. It carries the resolved album URL (Spotify or Qobuz or Tidal) for the batch this track belongs to.

### 1.2 Extract batch-level service URLs in `parse_log()`

The legacy log emits, per batch:
```
[HH:MM:SS] [info] fetching album metadata...        # OR: fetching direct link metadata...
[HH:MM:SS] [debug] url: <URL>
```

Within `parse_log()`, track the current batch's source URL. When a `[debug] url:` line is seen, capture the URL. Assign it to every `SpotiflacTrack` in that batch (i.e. all tracks appended after that URL is set, until a new URL appears).

**URL → service ID extraction rules:**

| URL pattern | ID field in `SpotiflacTrack` | Value |
|---|---|---|
| `open.spotify.com/album/<id>` | `spotify_id` (existing field) | album-level |
| `open.qobuz.com/album/<id>` | new field `qobuz_album_id: str | None = None` | album-level |
| `tidal.com/album/<id>` or `listen.tidal.com/album/<id>` | new field `tidal_album_id: str | None = None` | album-level |

Add `qobuz_album_id` and `tidal_album_id` fields to `SpotiflacTrack` (default `None`).

Populate all three from the batch URL. Do not overwrite an already-set ISRC or provider from later lines.

### 1.3 No changes to `parse_log_next()` or `build_manifest()`

Do not touch the `next`-format parser. `build_manifest()` needs no changes — it calls `parse_log()`.

---

## Part 2 — Intake command changes (`tagslut/cli/commands/intake.py`)

Find the `intake spotiflac` command. It currently calls `dual_write_registered_file(...)` with:
```python
ingestion_method_override="spotiflac_fallback",
ingestion_confidence_override="high",
```

### 2.1 Correct `ingestion_method_override`

Change the logic:
- If `track.provider` is known (not `"unknown"`) → `ingestion_method_override = "provider_api"`
- Otherwise → keep `"spotiflac_fallback"`

This reflects that the audio came from a provider API (apple, tidal, qobuz), not from an unknown fallback path.

### 2.2 Enrich `ingestion_source_override`

Currently: `ingestion_source = f"spotiflac:{log_path.name}"`

Change to encode the album source URL when available. For each track, build:
```
spotiflac_log:<log_filename>|source:<album_source_url>
```
where `album_source_url` is `track.album_source_url` if set, else omit the `|source:` suffix.

### 2.3 Pass service IDs into `provider_id_hints`

Currently:
```python
provider_hints = {"isrc": track.isrc} if track.isrc else None
```

Extend to include all known service IDs:
```python
provider_hints = {}
if track.isrc:
    provider_hints["isrc"] = track.isrc
if track.spotify_id:
    provider_hints["spotify_album_id"] = track.spotify_id
if track.qobuz_album_id:
    provider_hints["qobuz_album_id"] = track.qobuz_album_id
if track.tidal_album_id:
    provider_hints["tidal_album_id"] = track.tidal_album_id
provider_hints = provider_hints if provider_hints else None
```

`dual_write_registered_file` forwards `provider_id_hints` to `identity_service`. The identity service stores what it recognizes; unknown hint keys are ignored. Do not change `identity_service.py`.

### 2.4 MP3 routing and M3U output

After the ingestion loop (after writing to DB), add a post-processing step for MP3 files. Read the env:
- `MP3_LIBRARY = Path(os.environ.get("MP3_LIBRARY", "/Volumes/MUSIC/MP3_LIBRARY"))`

For every successfully ingested track where `track.file_path` exists and suffix is `.mp3`:
1. Determine destination: `MP3_LIBRARY / track.file_path.name`
2. If destination does not exist, copy the file (do not move — staging is not deleted here).
3. Collect destination paths into a list.

After processing all tracks, if any MP3 destinations were written, write two M3U files:

**Batch M3U** (tracks from this log run only):
```
_ingest/spotiflac_logs/<log_stem>__mp3.m3u
```
One absolute path per line, in ingestion order.

**Global pool append** (`DJ_POOL = Path(os.environ.get("DJ_POOL_M3U", "/Volumes/MUSIC/MP3_LIBRARY/dj_pool.m3u"))`):
Append any new entries (skip if already present in the file) to the global pool M3U.

If `MP3_LIBRARY` is not mounted (`not MP3_LIBRARY.exists()`), emit a `[warning]` and skip the MP3 copy + M3U steps without failing.

Do NOT touch FLAC/MASTER_LIBRARY routing here — that is handled by `process-root`. This step only handles MP3 copies.

---

## Part 3 — Tests (`tests/intake/test_spotiflac_parser.py`)

Read the existing test file. Add or extend:

### 3.1 `test_parse_log_extracts_spotify_album_id`

Fixture: a minimal legacy log with:
```
[08:38:51] [info] fetching album metadata...
[08:38:51] [debug] url: https://open.spotify.com/album/2U0b5MfkMUgzdvRUI69mya
[08:39:05] [debug] trying qobuz for: Track One - Artist A
[08:39:08] [success] qobuz: Track One - Artist A
[08:39:08] [success] downloaded: Track One - Artist A
```

Assert:
- `tracks[0].spotify_id == "2U0b5MfkMUgzdvRUI69mya"`
- `tracks[0].album_source_url == "https://open.spotify.com/album/2U0b5MfkMUgzdvRUI69mya"`

### 3.2 `test_parse_log_extracts_qobuz_album_id`

Fixture: direct-link batch:
```
[08:48:08] [info] fetching direct link metadata...
[08:48:08] [debug] url: https://open.qobuz.com/album/ldgvxrkvvvfpb
[08:48:17] [debug] direct link: trying qobuz for: Someone Like You  - Fred Everything
[08:48:48] [success] direct link qobuz: Someone Like You  - Fred Everything
[08:48:48] [success] downloaded: Someone Like You  - Fred Everything
```

Assert:
- `tracks[0].qobuz_album_id == "ldgvxrkvvvfpb"`
- `tracks[0].spotify_id is None`

### 3.3 `test_parse_log_multi_batch_ids_do_not_bleed`

Fixture: two batches in one log (Spotify then Qobuz). Assert that Spotify tracks have `spotify_id` set and `qobuz_album_id=None`, and Qobuz tracks have `qobuz_album_id` set and `spotify_id=None`.

---

## Execution

1. Read existing code before editing; use `str_replace` / `edit_block` only.
2. Run targeted tests:
   ```
   cd /Users/georgeskhawam/Projects/tagslut && export PATH="$HOME/.local/bin:$PATH" && poetry run pytest tests/intake/test_spotiflac_parser.py -v
   ```
3. Commit:
   ```
   feat(intake): extract service IDs from spotiflac log batches and route MP3s
   ```

## What NOT to do

- Do not modify `identity_service.py`.
- Do not run the full test suite.
- Do not write to `/Volumes/MUSIC` or any DB directly.
- Do not delete staging files.
- Do not fabricate track-level apple IDs or tidal track IDs — the log does not contain them.
