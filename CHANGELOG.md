# Changelog

## Unreleased

- Archived historical scripts and prototypes under `dedupe/ARCHIVE/` while
  promoting the modern `dedupe` package as the sole supported codebase.
- Rebuilt the `dedupe` package around reusable modules for scanning,
  metadata extraction, fingerprinting, matching, and manifest generation.
- Added a new CLI (`dedupe scan-library`, `parse-rstudio`, `match`,
  `generate-manifest`) that orchestrates the full recovery workflow.
- Documented the revised commands and developer workflow in `README.md` and
  `USAGE.md`.
- Refreshed architecture and operations documentation to reference the new
  pipeline while marking legacy quarantine workflows as archived.
>>>>>>> apply/patch-20251113
