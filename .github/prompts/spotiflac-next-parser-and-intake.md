# spotiflac-next-parser-and-intake

## Do not recreate or overwrite any existing files without reading them first.
## Do not run the full test suite. Use targeted pytest only.

---

## Context

`tagslut/intake/spotiflac_parser.py` currently handles the "old" SpotiFLAC log format:
timestamped lines like `[HH:MM:SS] [level] message`. This is used by `tagslut intake
spotiflac <log_file>`.

SpotiFLACnext produces a **different log format** (a "Download Report"). The parser must
be extended to handle both formats. No changes to `intake.py` or any CLI command are
required — only the parser and its tests.

---

## SpotiFLACnext log format (actual observed structure)

```
Download Report - 4/13/2026, 4:59:33 PM
--------------------------------------------------

[SUCCESS] What's Next - Ramon Tapia
1. Der Spatz Auf Dem Dach - Peter Juergens; Oliver Klein (Berlin Underground Selection (Finest Electronic Music))
   Error: [Qobuz A] track not found for ISRC: DEAA20900927 | [Qobuz B] track not found for ISRC: DEAA20900927 | [Deezer A] deezer api returned status: 502
   ID: 4CMBoQOCX7KNjJqCB800Rm
   URL: https://open.spotify.com/track/4CMBoQOCX7KNjJqCB800Rm

[SUCCESS] Shanghai Spinner - Oliver Huntemann
[SUCCESS] Burn Myself - Coyu; Edu Imbernon
2. Show of Hands - Bushwacka! (Berlin Underground Selection (Finest Electronic Music))
   Error: [Apple Music] Song not available in ALAC | [Qobuz A] track not found for ISRC: GBLPN0900005 | ...
   ID: 70MluEOJd2DaXur42Kk2rC
   URL: https://open.spotify.com/track/70MluEOJd2DaXur42Kk2rC
```

**Rules:**
- `[SUCCESS] Track Name - Artist; Artist` → succeeded track. Title is the full string after
  `[SUCCESS] `. No ISRC available from success lines.
- `N. Track Name - Artist; Artist (Playlist Name)` → failed track header. Strip the
  trailing `(Playlist Name)` suffix from the display title. N is sequential failure index
  (not track position).
- `   Error: [Provider A] message | [Provider B] message ...` → failure error string for
  the preceding failed entry. ISRCs appear as `ISRC: XXXXXX` inside provider error tokens.
  Extract the first ISRC found (all providers report the same ISRC for the same track).
- `   ID: <spotify_id>` → spotify_id field for the failed track (store on SpotiflacTrack
  as `spotify_id: str | None`).
- `   URL: https://open.spotify.com/track/...` → ignored (redundant with ID).
- Provider identification for failed tracks: scan the Error line for the first
  `[Provider X]` token that does NOT say "track not found" or "not available" — that
  would indicate a provider that was attempted but failed for a different reason. If all
  providers failed with "not found"/"not available", set `provider = "unknown"`.
- Blank lines and the header/separator lines are ignored.

**M3U8 naming in SpotiFLACnext:** The M3U8 files are named `<playlist>_converted.m3u8`
(MP3 paths) and `<playlist>.m3u8` (original FLAC/m4a paths). The parser should prefer
the non-`_converted` M3U8 (original audio) for path resolution. M3U8 paths in
SpotiFLACnext are relative, structured as:
`Artist/({year}] Album/track_number. Track - Artists.ext`

---

## Required changes to `tagslut/intake/spotiflac_parser.py`

### 1. Add `spotify_id: str | None` field to `SpotiflacTrack`

Add the field with default `None`. No other dataclass changes.

### 2. Add format auto-detection

Add a private function:

```python
def _detect_format(log_path: Path) -> Literal["legacy", "next"]:
```

- Read the first non-empty line of the file.
- If it starts with `Download Report` → return `"next"`.
- Otherwise → return `"legacy"` (existing timestamped format).

### 3. Add `parse_log_next(log_path: Path) -> list[SpotiflacTrack]`

Implement the SpotiFLACnext log parser per the format rules above.

ISRC extraction from error lines: reuse the existing `_QOBUZ_ISRC_RE` pattern — it
matches `ISRC: XXXXXX` in any context.

The `display_title` for succeeded tracks is the full string after `[SUCCESS] `.
For failed tracks it is everything before ` (Playlist Name)` on the numbered header line.
Strip the ` (Playlist Name)` suffix by removing the last ` (...)` group from the title.
Be conservative: only strip if the parenthesised suffix starts with an uppercase letter
(playlist names are always title-case).

Provider for succeeded tracks: set to `"unknown"` — SpotiFLACnext success lines do not
name the provider.

### 4. Update `parse_log(log_path: Path)` (the existing function)

No changes to its body. Rename it internally if needed, but keep the public name `parse_log`.

### 5. Update `build_manifest` to dispatch by format

```python
def build_manifest(
    log_path: Path,
    m3u8_path: Path | None = None,
    failed_path: Path | None = None,
) -> list[SpotiflacTrack]:
```

- After resolving `log_path`, call `_detect_format(log_path)`.
- If `"next"`: call `parse_log_next(log_path)` to get tracks. Skip `parse_failed_report`
  (failures are already embedded in the next-format log). For M3U8 discovery: if
  `m3u8_path` is None, search `log_path.parent` for `*.m3u8` files that do NOT end in
  `_converted.m3u8`. If exactly one is found, use it. If multiple, use the one whose
  stem matches `log_path.stem` most closely; if none match, use the first alphabetically.
- If `"legacy"`: existing behaviour unchanged.

Path resolution logic (stem_map / norm_stem_map) is shared and applies to both formats
after the tracks list is built.

### 6. Update `classify_failure_reason`

No changes required — existing logic handles SpotiFLACnext error strings correctly
(they contain "track not found").

---

## Tests

File: `tests/intake/test_spotiflac_parser.py`

Read the existing test file first. Add new test cases — do not remove or modify existing
ones.

Add a fixture `NEXT_FORMAT_LOG` (inline string, not a file) representing a minimal
SpotiFLACnext log:

```
Download Report - 4/13/2026, 4:59:33 PM
--------------------------------------------------

[SUCCESS] What's Next - Ramon Tapia
[SUCCESS] Shanghai Spinner - Oliver Huntemann
1. Der Spatz Auf Dem Dach - Peter Juergens; Oliver Klein (Berlin Underground Selection)
   Error: [Qobuz A] track not found for ISRC: DEAA20900927 | [Deezer A] deezer api returned status: 502
   ID: 4CMBoQOCX7KNjJqCB800Rm
   URL: https://open.spotify.com/track/4CMBoQOCX7KNjJqCB800Rm

2. Show of Hands - Bushwacka! (Berlin Underground Selection)
   Error: [Apple Music] Song not available in ALAC | [Qobuz A] track not found for ISRC: GBLPN0900005
   ID: 70MluEOJd2DaXur42Kk2rC
   URL: https://open.spotify.com/track/70MluEOJd2DaXur42Kk2rC

[SUCCESS] Burn Myself - Coyu; Edu Imbernon
```

Add these test cases:

- `test_detect_format_next`: assert `_detect_format` returns `"next"` for next-format log.
- `test_detect_format_legacy`: assert `_detect_format` returns `"legacy"` for a
  timestamped log line like `[00:54:07] [debug] trying qobuz for: Track - Artist`.
- `test_parse_log_next_success_count`: parse the fixture; assert 3 succeeded, 2 failed.
- `test_parse_log_next_isrc_extracted`: assert failed track 1 has `isrc == "DEAA20900927"`.
- `test_parse_log_next_spotify_id`: assert failed track 1 has
  `spotify_id == "4CMBoQOCX7KNjJqCB800Rm"`.
- `test_parse_log_next_display_title_strips_playlist`: assert failed track 1 has
  `display_title == "Der Spatz Auf Dem Dach - Peter Juergens; Oliver Klein"` (no suffix).
- `test_parse_log_next_succeeded_provider_unknown`: assert a succeeded track has
  `provider == "unknown"`.

Use `tmp_path` (pytest fixture) to write the fixture to a temp file for `_detect_format`
and `build_manifest` tests.

---

## Commit

```
feat(intake): extend spotiflac_parser to handle SpotiFLACnext download report format
```

Single commit. Targeted pytest only:
```
poetry run pytest tests/intake/test_spotiflac_parser.py -v
```
