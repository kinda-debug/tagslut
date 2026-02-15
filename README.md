# tagslut

Music library deduplication and metadata orchestration toolkit.

## Quick Start

```bash
cd ~/Projects/tagslut
source .venv/bin/activate
tagslut --help
```

## Documentation

| Document | Purpose |
|----------|---------|
| `docs/README_OPERATIONS.md` | **Single source of truth** - all commands |
| `docs/WORKFLOWS.md` | Step-by-step workflow guides |
| `docs/TROUBLESHOOTING.md` | Common issues and fixes |

## Common Commands

```bash
# Download from any source (Beatport/Tidal/Deezer)
tools/get <url>

# Pre-check + download only missing
tools/get-auto <url>

# Register downloads to DB
tagslut index register <path> --source [bpdl|tidal|deezer]

# Check for duplicates
tagslut index check --db <db>
```

## CLI

- `tagslut` - preferred command name
- `dedupe` - compatibility alias (retiring June 2026)
