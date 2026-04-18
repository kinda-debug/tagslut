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
poetry run python -m tagslut auth login qobuz --email YOUR_EMAIL --force
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
```

Provider-specific prerequisites for `ts-get`:
- Beatport: `BEATPORTDL_CMD` must point to the local `beatportdl` binary.
- Qobuz: `STREAMRIP_CMD` and `STREAMRIP_CONFIG` must point to the local `streamrip` install and config.

## Enrich metadata

```bash
ts-enrich              # BPM, key, genre, label for all unenriched tracks
```

Enrichment fills linked `track_identity.canonical_*` fields when an active
identity link exists, while keeping `files.canonical_*` as the compatibility
fallback used by canonical FLAC writeback.
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
