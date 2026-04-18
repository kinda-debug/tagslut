# Operator Quick Start

## Daily Startup

```bash
cd /Users/georgeskhawam/Projects/tagslut
source START_HERE.sh
```

If this machine does not have `env_exports.sh` yet:

```bash
cp env_exports.sh.template env_exports.sh
$EDITOR env_exports.sh
```

## Token refresh (run before any download or enrichment session)

```bash
ts-auth
```

If Qobuz session is expired (ts-auth will tell you):
```bash
poetry run tagslut auth login qobuz --email YOUR_EMAIL --force
```

If Beatport token is expired, launch beatportdl once to refresh:
```bash
cd ~/Projects/beatportdl && ./beatportdl-darwin-arm64
# Ctrl+C after the "Enter url" prompt appears
cd ~/Projects/tagslut && ts-auth beatport
```

## Download

```bash
ts-get <url>           # TIDAL, Qobuz, or Beatport URL
ts-get <url> --dj      # download + add to DJ pool M3U
poetry run tagslut get /path/to/dir --tag   # local staged intake -> enrich -> promote -> M3U
tools/ts-stage         # auto-process non-empty staging subdirectories with source auto-detection
```

Provider-specific prerequisites for `ts-get`:
- Beatport: no manual path is required in the default repo layout; override with
  `BEATPORTDL_CMD` or `BEATPORTDL_BIN` only when using a different binary.
- Qobuz: `STREAMRIP_CONFIG` must point to the active Streamrip config; `STREAMRIP_CMD`
  is optional and only needed to override the repo-local wrapper.

## SpotiFLAC-Next

```bash
tools/spotiflac-next
```

This launches the macOS app detached and writes logs under:

```text
artifacts/logs/spotiflacnext/
```

Use `tools/spotiflac-next --foreground` only when you want terminal log streaming.

## Staging intake

To process a single already-downloaded directory through staged intake:

```bash
poetry run tagslut get /Volumes/MUSIC/staging/SpotiFLACnext/My Batch --tag
poetry run tagslut get /Volumes/MUSIC/staging/bpdl/Some Release --tag
```

To process whatever is left under the staging root without picking the source
manually:

```bash
tools/ts-stage
```

`tools/ts-stage` walks the immediate subdirectories under `$STAGING_ROOT`,
skips empty ones, infers `bpdl` / `tidal` / `qobuz` / `spotiflacnext` /
`legacy`, then runs one-shot staged intake.

For `spotiflacnext` sources, stage now:
- reads the latest log from `artifacts/logs/spotiflacnext/` (or `SPOTIFLAC_NEXT_LOG_ROOT`)
- runs `tagslut intake spotiflac` before normal register/enrich/promote steps
- runs `index register-mp3` for the same root so MP3 outputs are indexed and routed
- prunes orphan `.m3u` files in playlist export roots after writing current stage playlists

To process a single staging root directly:

```bash
tools/ts-stage /Volumes/MUSIC/staging/SpotiFLACnext
tools/ts-stage /Volumes/MUSIC/staging/bpdl --dry-run
```

Staged intake now writes named M3U files automatically after promote:
- playlist/log name when a single batch log or playlist file exists
- album name when the promoted files share one album
- track title when it is a single-track batch
- one playlist per track when there is no safe merged batch name

## Enrich metadata

```bash
ts-enrich              # BPM, key, genre, label for all unenriched tracks
```

Enrichment fills linked `track_identity.canonical_*` fields when an active
identity link exists, while keeping `files.canonical_*` as the compatibility
fallback used by canonical FLAC writeback.
Default metadata providers are now `beatport,tidal,qobuz` unless disabled in
`~/.config/tagslut/providers.toml`.
Public ReccoBeats lookups remain available for audio-feature enrichment even if
its provider state reports `enabled_unconfigured`.

## DJ pool — Rekordbox

- Import `$MP3_LIBRARY/dj_pool.m3u` into Rekordbox
- Build crates there
- Synchronize to USB before gig

## Database stats

```bash
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*) FROM files;"
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*), SUM(CASE WHEN canonical_genre IS NOT NULL THEN 1 ELSE 0 END) FROM track_identity;"
```


## Related active docs

- `docs/README.md` — full active-doc index and audit-doc location.
- `docs/DJ_POOL.md` — current M3U-based DJ pool contract.
- `docs/DOWNLOAD_STRATEGY.md` — source-selection policy.
- `docs/TIDDL_CONFIG.md` — tiddl config contract for this workspace.
