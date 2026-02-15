# legacy/tools

Archived scripts retained for reference and backward compatibility.

This directory is not the primary development surface.

## What belongs here

- Historical workflows that were replaced by `tagslut/` commands or `tools/review/` scripts.
- Compatibility code paths still called by wrapper commands (`tagslut scan`, `tagslut recommend`, `tagslut apply`, parts of `tagslut promote/quarantine`).

## Preferred modern paths

- Inventory + duplicate checks + M3U: `tagslut mgmt ...`
- Metadata enrichment/auth: `tagslut metadata ...`
- Corruption scan/repair: `tagslut recover ...`
- Operational planning and move execution: `tools/review/*.py`

## Migration rule

When editing legacy behavior, prefer implementing the fix in `tagslut/` or `tools/review/` and keep legacy scripts stable unless compatibility requires touching them.
