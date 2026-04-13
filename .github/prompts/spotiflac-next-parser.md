# spotiflac-next-parser

## Objective

Extend `tagslut/intake/spotiflac_parser.py` to support the **SpotiFLACnext
report format** (`.txt` files produced by SpotiFLACnext, distinct from the
original SpotiFLAC timestamped log format).

Do NOT recreate or rewrite any file wholesale. Use targeted edits only.
Do NOT modify any schema, migration, storage layer, or exec orchestrator.
Do NOT modify `tools/get` or `tools/get-intake`.

---

## Format reference

### Old SpotiFLAC format (already supported — do not break)

```
[HH:MM:SS] [debug] trying qobuz for: Track Title - Artist Name
[HH:MM:SS] [error] qobuz error: track not found for ISRC: XXXXXXXXXXXX
[HH:MM:SS] [debug] trying tidal for: Track Title - Artist Name
[HH:MM:SS] [success] tidal: Track Title - Artist Name
[HH:MM:SS] [success] downloaded: Track Title - Artist Name
[HH:MM:SS] [error] failed: Track Title - Artist Name
```

Companion files (auto-discovered by `build_manifest`):
- `<stem>.m3u8` — FLAC paths
- `<stem>_Failed.<ext>` — failure detail report

### SpotiFLACnext format (NEW)

```
Download Report - M/D/YYYY, H:MM:SS AM/PM
--------------------------------------------------

[SUCCESS] Track Title - Artist Name
N. Track Title - Artist Name (Playlist Name)
   Error: [Provider A] reason for ISRC: XXXXXXXXXXXX | [Provider B] reason | ...
   ID: <spotify_track_id>
   URL: https://open.spotify.com/track/<spotify_track_id>

[SUCCESS] Another Track - Another Artist
```

Parsing rules:
- First non-empty line starts with `Download Report` → SpotiFLACnext format.
- `[SUCCESS] ...` → successful track. `provider = "unknown"`. `spotify_id = None`.
- `N. Title (Playlist Name)` → start of a failed-track block.
  Strip trailing ` (Playlist Name)` parenthetical from `display_title`.
  The counter `N.` is not semantically meaningful.
- `   Error: ...` (indented line starting with `Error:`) → `failure_reason` is
  the full content after `Error: `. Extract first ISRC with `_QOBUZ_ISRC_RE`.
- `   ID: <id>` → `spotify_id`.
- `   URL: ...` → ignored.
- Emit the failed track when the next `[SUCCESS]` or `N.` line or EOF is reached.
- Failures are inline; no `_Failed` report file exists for this format.

Companion file: `<stem>_converted.m3u8` (note the `_converted` suffix).

---

## Changes required

### 1. `tagslut/intake/spotiflac_parser.py`

#### 1a. Add `spotify_id` field to `SpotiflacTrack`

Add `spotify_id: str | None = None` as a new optional field on the dataclass.
Existing field order must not change.

#### 1b. Add `_detect_format`

```python
def _detect_format(log_path: Path) -> Literal["spotiflac", "spotiflacnext"]:
    """Return 'spotiflacnext' if file starts with 'Download Report', else 'spotiflac'."""
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line:
            return "spotiflacnext" if line.startswith("Download Report") else "spotiflac"
    return "spotiflac"
```

#### 1c. Add `parse_log_next(log_path: Path) -> list[SpotiflacTrack]`

State machine:
- Skip header (`Download Report`) and separator (`---`).
- `[SUCCESS] ...` line → emit successful track immediately.
- `N. Title (Playlist Name)` line (matches `^\d+\.\s+`) → begin failed block;
  strip trailing ` (Playlist Name)` parenthetical.
- `Error: ...` → set `failure_reason`; run `_QOBUZ_ISRC_RE` to get first ISRC.
- `ID: <id>` → set `spotify_id`.
- `URL: ...` → skip.
- Next `[SUCCESS]` or `N.` line (or EOF) → flush pending failed track.

#### 1d. Extract `_resolve_file_paths` helper

Pull the stem→path matching block (exact map + norm_map loop) out of the
existing `build_manifest` into a module-level helper:

```python
def _resolve_file_paths(
    tracks: list[SpotiflacTrack],
    stem_map: dict[str, Path],
    norm_stem_map: dict[str, Path],
) -> None:
    """Mutate track.file_path in-place using exact then normalised stem matching."""
    ...
```

Both the old and new branches of `build_manifest` must call this helper.
Do not duplicate the logic.

#### 1e. Update `build_manifest` dispatch

```python
fmt = _detect_format(log_path)

if fmt == "spotiflacnext":
    if m3u8_path is None:
        candidate = log_path.with_name(log_path.stem + "_converted.m3u8")
        if candidate.exists():
            m3u8_path = candidate
        else:
            siblings = list(log_path.parent.glob("*_converted.m3u8"))
            if len(siblings) == 1:
                m3u8_path = siblings[0]
    tracks = parse_log_next(log_path)
    # failed_path not used for spotiflacnext
else:
    # existing auto-discovery of .m3u8 and _Failed files unchanged
    tracks = parse_log(log_path)
    # existing failed_map merge unchanged

stem_map = parse_m3u8(m3u8_path) if m3u8_path and m3u8_path.exists() else {}
norm_stem_map = {_norm_match_key(s): p for s, p in stem_map.items() if _norm_match_key(s)}
_resolve_file_paths(tracks, stem_map, norm_stem_map)
```

For the old branch, the `failed_map` merge onto tracks must still happen before
`_resolve_file_paths` is called (order preserved from current code).

---

### 2. `tests/intake/test_spotiflac_parser.py`

Add `test_spotiflacnext_manifest_parsing`. Do NOT modify the existing test.

Inline fixtures (same pattern as existing test). The test must cover:

- `[SUCCESS]` track → `failed=False`, `provider="unknown"`, `spotify_id=None`,
  `file_path` resolved via supplied `m3u8_path`.
- Failed track → `failed=True`, `isrc` extracted from Error line, `spotify_id`
  extracted from `ID:` line, `failure_reason` set, playlist-name parenthetical
  stripped from `display_title`.
- `classify_failure_reason` returns `"unavailable"` for `"track not found"`.

Supply `m3u8_path` explicitly (using `_converted.m3u8` naming convention in the
fixture filename) so M3U8 auto-discovery is also tested.

---

## Acceptance

```
poetry run pytest tests/intake/test_spotiflac_parser.py -v
```

Both tests must pass. No other tests may regress.

---

## Commit

```
feat(intake): add SpotiFLACnext report format parser
```

Single commit. Targeted edits only.
