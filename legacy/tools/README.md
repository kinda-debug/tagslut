# legacy/tools

Archived scripts retained for reference and backward compatibility.

This directory is not the primary development surface.

## What belongs here

- Historical workflows that were replaced by `dedupe/` commands or `tools/review/` scripts.
- Compatibility code paths still called by wrapper commands (`dedupe scan`, `dedupe recommend`, `dedupe apply`, parts of `dedupe promote/quarantine`).

## Preferred modern paths

- Inventory + duplicate checks + M3U: `dedupe mgmt ...`
- Metadata enrichment/auth: `dedupe metadata ...`
- Corruption scan/repair: `dedupe recover ...`
- Operational planning and move execution: `tools/review/*.py`

## Migration rule

When editing legacy behavior, prefer implementing the fix in `dedupe/` or `tools/review/` and keep legacy scripts stable unless compatibility requires touching them.
