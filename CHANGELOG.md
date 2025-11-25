# Changelog

## Unreleased

- No changes yet.

## 0.9.0

- Removed remaining R-Studio artifacts and references from the packaged project.
- Normalised logging descriptions and CLI help text to match the released workflow.
- Ensured type-hint consistency across the CLI surface without altering behaviour.
- Improved readability in documentation while keeping commands unchanged.
- Hardened tests and fixtures around scanning, matching, and health scoring flows.
- Cleaned packaging metadata (pyproject, MANIFEST, requirements) for the release.

## 0.8.0

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
