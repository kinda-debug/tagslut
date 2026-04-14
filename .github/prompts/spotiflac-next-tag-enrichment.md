# spotiflac-next-tag-enrichment

## Do not recreate or overwrite any existing files without reading them first.
## Do not run the full test suite. Use targeted pytest only.

---

## Context

`tagslut/intake/spotiflac_parser.py` parses SpotiFLACnext Download Report `.txt`
files and resolves file paths from `.m3u8` playlists. The current gap: after
`_resolve_file_paths` populates `track.file_path` for success tracks, `track.isrc`
remains `None` and `track.provider` remains `"unknown"` — even though both are
available in the downloaded file's embedded tags.

SpotiFLACnext embeds the following tags in every downloaded file:

**FLAC** (Vorbis Comments):
- `isrc` → ISRC string (lowercase key)
- `comment` → `https://open.spotify.com/track/<spotify_track_id>`

**M4A** (iTunes atoms):
- `----:com.apple.iTunes:ISRC` → list of MP4FreeForm bytes, decode utf-8
- `©cmt` → plain string list containing Spotify track URL

M4A files are always Apple Music (the only provider that delivers M4A).
FLAC provider cannot be determined from tags — leave as `"unknown"`.
MP3 files are auto-converted derivatives — skip them.

---

## Required changes to `tagslut/intake/spotiflac_parser.py`

Read the file before editing. Use targeted edits only.

### 1. Add `_SPOTIFY_TRACK_URL_RE` regex near existing URL regexes

```python
_SPOTIFY_TRACK_URL_RE = re.compile(r"open\.spotify\.com/track/(?P<id>[A-Za-z0-9]+)")
```

### 2. Add `_read_tags_from_file(path: Path) -> dict[str, str | None]`

Returns dict with keys `isrc`, `spotify_id`, `provider`. Rules:
- Import `mutagen.flac.FLAC` and `mutagen.mp4.MP4` inside the function body.
- `.flac`: open with `FLAC(path)`. Tags are lists; `tags.get("isrc", [None])[0]`.
  Comment key is `"comment"` (lowercase). Provider = `None`.
- `.m4a`: open with `MP4(path)`. `----:com.apple.iTunes:ISRC` is a list of
  `MP4FreeForm` — `.decode("utf-8")` on first element. `©cmt` is string list.
  Provider = `"apple"`.
- Extract `spotify_id` from comment using `_SPOTIFY_TRACK_URL_RE`.
- Uppercase ISRC before returning.
- Catch all exceptions; return `{"isrc": None, "spotify_id": None, "provider": None}`.

### 3. Add `_enrich_from_tags(tracks: list[SpotiflacTrack]) -> None`

For each track where `failed=False` and `file_path is not None`:
- Call `_read_tags_from_file(track.file_path)`.
- Set `track.isrc` only if result isrc is not None and `track.isrc is None`.
- Set `track.spotify_id` only if result spotify_id is not None and `track.spotify_id is None`.
- Set `track.provider` only if result provider is not None and `track.provider == "unknown"`.

### 4. Call in `build_manifest`

In the `if log_format == "next":` branch only, after `_resolve_file_paths(...)`:

```python
_enrich_from_tags(tracks)
```

---

## Required changes to `tests/intake/test_spotiflac_parser.py`

Read the file before editing. Do not modify existing tests.

Add imports if not present:
```python
import shutil
from tagslut.intake.spotiflac_parser import _enrich_from_tags
```

**IMPORTANT**: `FLAC()` with no path raises on tag assignment. Always copy the
existing fixture `tests/data/healthy.flac` to `tmp_path` and write tags to the copy.
For M4A, `MP4()` with no path works fine — save directly to `tmp_path`.

### Test 1: `test_enrich_from_tags_flac`

```python
flac_path = tmp_path / "test.flac"
shutil.copy(Path(__file__).parent.parent / "data" / "healthy.flac", flac_path)
from mutagen.flac import FLAC
audio = FLAC(flac_path)
audio["isrc"] = ["GBRTB2500016"]
audio["comment"] = ["https://open.spotify.com/track/41kUqScV9h8smErQor3Ul6"]
audio.save()
```

Build a SpotiflacTrack with `isrc=None`, `spotify_id=None`, `provider="unknown"`,
`failed=False`, `file_path=flac_path`. Call `_enrich_from_tags([track])`. Assert:
- `track.isrc == "GBRTB2500016"`
- `track.spotify_id == "41kUqScV9h8smErQor3Ul6"`
- `track.provider == "unknown"`

### Test 2: `test_enrich_from_tags_m4a`

```python
from mutagen.mp4 import MP4, MP4FreeForm
m4a_path = tmp_path / "test.m4a"
audio = MP4()
audio["----:com.apple.iTunes:ISRC"] = [MP4FreeForm(b"QM24S2300943")]
audio["©cmt"] = ["https://open.spotify.com/track/45hT5XsnLSJpzNY6tzfqtO"]
audio.save(m4a_path)
```

Assert `track.isrc == "QM24S2300943"`, `track.spotify_id == "45hT5XsnLSJpzNY6tzfqtO"`,
`track.provider == "apple"`.

### Test 3: `test_enrich_does_not_overwrite_existing`

Copy `healthy.flac` to `tmp_path`, embed `isrc=["FROMFILE"]`. Build track with
`isrc="EXISTING"`. Call `_enrich_from_tags`. Assert `track.isrc == "EXISTING"`.

---

## Acceptance

```
poetry run pytest tests/intake/test_spotiflac_parser.py -v
```

All existing and new tests must pass.

---

## Commit

```
feat(intake): enrich SpotiFLACnext success tracks with ISRC and provider from file tags
```
