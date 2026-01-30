# Metadata Package

This package handles metadata enrichment and provider resolution for FLAC files.

Start here:
- `docs/METADATA_WORKFLOW.md` — full workflow, modes, DB fields, and CLI usage.

Key modules:
- `enricher.py` — orchestrates resolution and DB updates
- `models.py` — data structures + canonical precedence rules
- `auth.py` — token management
- `providers/` — provider implementations
