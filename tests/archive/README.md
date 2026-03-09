<!-- Status: Active document. Reviewed 2026-03-09. Historical or superseded material belongs in docs/archive/. -->

# Archived Test Suites

This directory contains retired test suites preserved for historical reference:

- `recovery/` mirrors the archived `legacy/tagslut_recovery/` package.
- `scan/` mirrors the archived `legacy/tagslut_scan/` package.

These tests are excluded from active CI via `tests/conftest.py` (`collect_ignore = ["archive"]`).
