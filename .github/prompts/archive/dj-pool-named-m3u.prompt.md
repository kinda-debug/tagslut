# dj-pool-named-m3u — Named M3U files from URL playlist/album title

## Do not recreate existing files. Do not modify files not listed in scope.

---

## Context

`write_dj_pool_m3u` always writes a batch M3U named `dj_pool.m3u` in the
album folder regardless of what was downloaded. When you download a playlist
called "Balearic Summer" or an album called "Leftism", the batch M3U should
be named `Balearic Summer.m3u` or `Leftism.m3u` — not `dj_pool.m3u`.

The global accumulating file at `MP3_LIBRARY/dj_pool.m3u` stays as-is.

The URL is available in `tools/get` at download time. The provider API
(Qobuz, TIDAL) knows the playlist/album title. That title needs to flow
through to the M3U writer.

---

## Scope

### 1. `tagslut/exec/dj_pool_m3u.py`

Change `write_dj_pool_m3u` signature to accept an optional `playlist_name`:

```python
def write_dj_pool_m3u(
    mp3_paths: list[Path],
    mp3_root: Path,
    playlist_name: str | None = None,
) -> tuple[Path, Path]:
```

When `playlist_name` is provided:
- Sanitize it: strip leading/trailing whitespace, replace `/\:*?"<>|` with `_`,
  collapse multiple spaces, truncate to 100 chars.
- Use it as the batch M3U filename: `{sanitized_name}.m3u`
- The global M3U is always `MP3_LIBRARY/dj_pool.m3u` regardless.

When `playlist_name` is None: existing behavior (`dj_pool.m3u` in batch dir).

### 2. `tagslut/cli/commands/intake.py`

The `intake url` command already accepts a URL. Add an optional
`--playlist-name TEXT` option that flows through to `write_dj_pool_m3u`.

```python
@intake.command("url")
...
@click.option("--playlist-name", default=None, help="Name for the batch DJ pool M3U file")
```

Pass `playlist_name` to `write_dj_pool_m3u`.

### 3. `tools/get` — extract name from URL before calling intake

For each provider routing block, attempt to resolve the playlist/album name
from the URL **before** calling the intake pipeline. Pass it via `--playlist-name`.

#### Qobuz block

After `"$STREAMRIP_CMD" --config-path "$STREAMRIP_CONFIG" url "$URL"` succeeds,
extract the name from the URL and Qobuz API:

```bash
PLAYLIST_NAME=""
if [[ "$URL" == *"/playlist/"* ]]; then
    PLAYLIST_ID="${URL##*/playlist/}"
    PLAYLIST_NAME="$(cd "$REPO_ROOT" && poetry run python3 -c "
from tagslut.metadata.auth import TokenManager
import requests, json
from pathlib import Path
tm = TokenManager(Path.home() / '.config/tagslut/tokens.json')
app_id, _ = tm.get_qobuz_app_credentials()
tok = tm.ensure_qobuz_token()
r = requests.get('https://www.qobuz.com/api.json/0.2/playlist/get',
    params={'playlist_id': '${PLAYLIST_ID}', 'app_id': app_id},
    headers={'X-App-Id': app_id, 'X-User-Auth-Token': tok}, timeout=8)
d = r.json()
print(d.get('name', '') or d.get('title', ''))
" 2>/dev/null)"
elif [[ "$URL" == *"/album/"* ]]; then
    ALBUM_ID="${URL##*/album/}"
    PLAYLIST_NAME="$(cd "$REPO_ROOT" && poetry run python3 -c "
from tagslut.metadata.auth import TokenManager
import requests
from pathlib import Path
tm = TokenManager(Path.home() / '.config/tagslut/tokens.json')
app_id, _ = tm.get_qobuz_app_credentials()
tok = tm.ensure_qobuz_token()
r = requests.get('https://www.qobuz.com/api.json/0.2/album/get',
    params={'album_id': '${ALBUM_ID}', 'app_id': app_id},
    headers={'X-App-Id': app_id, 'X-User-Auth-Token': tok}, timeout=8)
print(r.json().get('title', ''))
" 2>/dev/null)"
fi
```

Then when calling `tagslut intake url`, add:
```bash
if [[ -n "$PLAYLIST_NAME" ]]; then
    INTAKE_URL_CMD+=(--playlist-name "$PLAYLIST_NAME")
fi
```

#### TIDAL block

Same pattern. For TIDAL URLs, extract the ID from the path segment after
`/playlist/`, `/album/`, or `/mix/` and query TIDAL API:

```bash
PLAYLIST_NAME=""
if [[ "$URL" == *"/playlist/"* ]]; then
    TIDAL_ID="${URL##*/playlist/}"
    # Query TIDAL v2 playlist endpoint
    PLAYLIST_NAME="$(cd "$REPO_ROOT" && poetry run python3 -c "
from tagslut.metadata.auth import TokenManager
import requests, json
from pathlib import Path
tm = TokenManager(Path.home() / '.config/tagslut/tokens.json')
tok = tm.get_token('tidal')
access = tok.access_token if tok else ''
if not access:
    raise SystemExit
r = requests.get(f'https://openapi.tidal.com/v2/playlists/${TIDAL_ID}',
    headers={'Authorization': f'Bearer {access}', 'Accept': 'application/vnd.api+json'}, timeout=8)
d = r.json()
print((d.get('data') or {}).get('attributes', {}).get('name', ''))
" 2>/dev/null)"
elif [[ "$URL" == *"/album/"* ]]; then
    TIDAL_ID="${URL##*/album/}"
    PLAYLIST_NAME="$(cd "$REPO_ROOT" && poetry run python3 -c "
from tagslut.metadata.auth import TokenManager
import requests
from pathlib import Path
tm = TokenManager(Path.home() / '.config/tagslut/tokens.json')
tok = tm.get_token('tidal')
access = tok.access_token if tok else ''
if not access:
    raise SystemExit
r = requests.get(f'https://openapi.tidal.com/v2/albums/${TIDAL_ID}',
    headers={'Authorization': f'Bearer {access}', 'Accept': 'application/vnd.api+json'}, timeout=8)
print((r.json().get('data') or {}).get('attributes', {}).get('title', ''))
" 2>/dev/null)"
fi
```

If the API call fails or returns empty, `PLAYLIST_NAME` stays `""` and the
existing `dj_pool.m3u` fallback is used. Never block the download on name resolution.

---

## Result

```
ts-get https://play.qobuz.com/playlist/61550668 --dj
```
Produces:
```
/Volumes/MUSIC/MP3_LIBRARY/Various Artists/(2024) Balearic Summer/
    01 Track.mp3
    02 Track.mp3
    Balearic Summer.m3u        ← batch, named after playlist
/Volumes/MUSIC/MP3_LIBRARY/
    dj_pool.m3u                ← global accumulator, unchanged
```

Both M3U files contain `#EXTINF` entries with artist/title from ID3 tags.

---

## Tests

Update `tests/exec/test_dj_pool_m3u.py`:
- Test: `playlist_name="Balearic Summer"` → batch file is `Balearic Summer.m3u`
- Test: `playlist_name=None` → batch file is `dj_pool.m3u` (existing behavior)
- Test: `playlist_name` with illegal chars → sanitized correctly
- Test: `playlist_name` over 100 chars → truncated

Run: `poetry run pytest tests/exec/test_dj_pool_m3u.py -v`

---

## Commit

```
git add -A
git commit -m "feat(dj-pool): named M3U files from playlist/album title when --dj is used"
```
