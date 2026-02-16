# Custom Workflow (DJ Health)

This is a full, copy‑pasteable workflow with commands and variables. It assumes the `tagslut` CLI and tools in this repo.

## Variables

Set these once per shell session or in `.env`.

```bash
# Database (source of truth)
export TAGSLUT_DB="/path/to/your/tagslut_db/EPOCH_YYYY-MM-DD/music.db"

# Library root (for playlist output)
export TAGSLUT_LIBRARY="/Volumes/MUSIC/LIBRARY"

# Optional: zones config (if you use it)
export TAGSLUT_ZONES="~/.config/tagslut/zones.yaml"

# Optional: reports/artifacts root
export TAGSLUT_ARTIFACTS="/path/to/tagslut/artifacts"
```

## Inputs

Pick one:

```bash
# Folder of FLACs
export INPUT_PATH="/path/to/folder"

# Or a file list (one path per line)
export INPUT_LIST="/path/to/paths.txt"
```

## 1) Register & measure durations

```bash
# Register files in the inventory (no mutations by default)
poetry run tagslut index register --db "$TAGSLUT_DB" "$INPUT_PATH"

# Measure durations and compute duration status
poetry run tagslut index duration-check --db "$TAGSLUT_DB" "$INPUT_PATH"
```

## 2) Enrich metadata (Beatport + Tidal)

```bash
# Enrich metadata using provider cascade
# Use --providers to limit sources; example uses beatport + tidal
poetry run tagslut index enrich --db "$TAGSLUT_DB" --providers beatport,tidal "$INPUT_PATH"
```

## 3) Re‑audit duration anomalies

```bash
# Audit duration anomalies (ok/warn/fail/unknown)
poetry run tagslut index duration-audit --db "$TAGSLUT_DB" --status warn
poetry run tagslut index duration-audit --db "$TAGSLUT_DB" --status fail
poetry run tagslut index duration-audit --db "$TAGSLUT_DB" --status unknown
```

## 4) Export Roon playlists (OK/Warn/Fail)

```bash
# OK
poetry run tagslut report m3u --db "$TAGSLUT_DB" --source ok --m3u-dir "$TAGSLUT_LIBRARY" "$INPUT_PATH"

# WARN
poetry run tagslut report m3u --db "$TAGSLUT_DB" --source warn --m3u-dir "$TAGSLUT_LIBRARY" "$INPUT_PATH"

# FAIL
poetry run tagslut report m3u --db "$TAGSLUT_DB" --source fail --m3u-dir "$TAGSLUT_LIBRARY" "$INPUT_PATH"
```

## 5) Canonize tags (optional, uses library_canon.json)

```bash
# Dry‑run canonization
poetry run tagslut canonize "$INPUT_PATH" --canon-dry-run

# Execute canonization
poetry run tagslut canonize "$INPUT_PATH" --execute
```

## 6) Provider auth (only if needed)

```bash
# Show auth status
poetry run tagslut auth status

# Initialize token template
poetry run tagslut auth init

# Refresh tokens
poetry run tagslut auth refresh
```

## One‑shot helper commands

```bash
# Full intake flow (Beatport/Tidal/Deezer via tools/get-intake)
poetry run tagslut intake run --help

# Beatport prefilter only
poetry run tagslut intake prefilter --help
```

## Notes

- `tagslut` expects FLAC inputs for most health checks.
- Beatport token is not required for the tokenless paths; if you want authenticated paths, use `tagslut auth`.
- Adjust `--providers` for strict source control.
