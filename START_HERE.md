# tagslut — Start Here

## Quick start

```bash
cd /Users/georgeskhawam/Projects/tagslut
source START_HERE.sh
```

This loads:
- `TAGSLUT_DB` (v3 SQLite DB)
- `MASTER_LIBRARY` (FLAC library root)
- `MP3_LIBRARY` (full-tag MP3 library root)
- `DJ_LIBRARY` (minimal-tag DJ MP3 library root)
- `STAGING_ROOT` (provider staging root)

## One-pass URL intake → fully-tagged FLAC → MP3/DJ derivatives

```bash
# URL → promote → single enrich/writeback pass over the FLAC cohort → MP3_LIBRARY (full tags)
tools/get --mp3 "<tidal-or-beatport-url>"

# URL → promote → single enrich/writeback pass over the FLAC cohort → MP3_LIBRARY (full tags) + DJ_LIBRARY (minimal DJ tags)
tools/get --dj "<tidal-or-beatport-url>"
```

Provider policy for that single enrich/writeback pass:
- Tidal URL:
  - `--mp3`: providers=`tidal`
  - `--dj`: providers=`beatport,tidal` (Beatport authoritative for DJ tags when available)
- Beatport URL:
  - `--mp3`/`--dj`: providers=`beatport,tidal`

## Provenance attribution (operator/run/tool)

Set these in the same shell session before running `tools/get --mp3/--dj`:

```bash
export TAGSLUT_OPERATOR="${TAGSLUT_OPERATOR:-$USER}"
export TAGSLUT_RUN_ID="intake_$(date +%Y%m%d_%H%M%S)"
export TAGSLUT_TOOL="cli"
```

