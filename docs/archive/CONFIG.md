# Configuration Guide

This document defines how `tagslut` reads configuration from environment variables and optional config files.

## Scope

Configuration sources used by this project:

- `.env` in repo root (loaded by tooling that supports dotenv)
- Shell environment (`export KEY=value`)
- Optional zone config at `~/.config/tagslut/zones.yaml`
- CLI flags (highest priority for individual commands)

## Precedence

General precedence (highest to lowest):

1. CLI argument (`--db`, `--m3u-dir`, etc.)
2. Exported shell variable
3. `.env` value
4. `zones.yaml` auto-populated roots (for volume variables)
5. Command defaults

## Required Variables

`TAGSLUT_DB` is the only hard requirement for most inventory and reporting operations.

```bash
TAGSLUT_DB=/absolute/path/to/music.db
```

## Recommended Variables

Use these for stable, repeatable runs:

```bash
# Core paths
TAGSLUT_DB=/absolute/path/to/music.db
VOLUME_STAGING=/absolute/path/to/staging
VOLUME_ARCHIVE=/absolute/path/to/archive
VOLUME_SUSPECT=/absolute/path/to/suspect
VOLUME_QUARANTINE=/absolute/path/to/quarantine
TAGSLUT_ARTIFACTS=/absolute/path/to/artifacts
TAGSLUT_REPORTS=/absolute/path/to/artifacts/reports

# Scan behavior
SCAN_WORKERS=8
SCAN_PROGRESS_INTERVAL=100
SCAN_CHECK_INTEGRITY=true
SCAN_CHECK_HASH=true
SCAN_INCREMENTAL=true

# Decision tuning
AUTO_APPROVE_THRESHOLD=0.95
QUARANTINE_RETENTION_DAYS=30
PREFER_HIGH_BITRATE=true
PREFER_HIGH_SAMPLE_RATE=true
PREFER_VALID_INTEGRITY=true
```

## .env Bootstrap

Create `.env` from example:

```bash
cd /Users/georgeskhawam/Projects/tagslut
cp .env.example .env
```

Then edit values in `/Users/georgeskhawam/Projects/tagslut/.env`.

## zones.yaml Integration

`zones.yaml` is optional. When present, it can supply staging/archive/suspect/quarantine roots.

Example file:

`/Users/georgeskhawam/Projects/tagslut/config/zones.yaml.example`

Default user location expected by tooling:

`~/.config/tagslut/zones.yaml`

Minimal schema:

```yaml
zones:
  staging:
    - /path/to/staging
  archive:
    - /path/to/archive
  suspect:
    - /path/to/suspect
  quarantine:
    - /path/to/quarantine
```

## Validation Commands

Verify effective setup before heavy operations:

```bash
cd /Users/georgeskhawam/Projects/tagslut

# Confirm env values are visible
printenv TAGSLUT_DB
printenv VOLUME_STAGING

# Confirm DB path exists
ls -l "$TAGSLUT_DB"

# Confirm CLI is wired
poetry run tagslut --help

# Optional: show zone classification for one path
poetry run tagslut show-zone "$VOLUME_STAGING"
```

## Common Pitfalls

- `TAGSLUT_DB` points to an old epoch DB.
  Use the active DB explicitly via `--db` when needed.

- Relative paths in `.env`.
  Use absolute paths only.

- Missing mount points under `/Volumes`.
  Validate with `ls -ld /Volumes/...` before runs.

- Conflicting shell exports vs `.env`.
  `printenv` shows the winning values at runtime.

## Canonical References

- Environment template: `/Users/georgeskhawam/Projects/tagslut/.env.example`
- Operations guide: `/Users/georgeskhawam/Projects/tagslut/docs/README_OPERATIONS.md`
- Zones details: `/Users/georgeskhawam/Projects/tagslut/docs/ZONES.md`
