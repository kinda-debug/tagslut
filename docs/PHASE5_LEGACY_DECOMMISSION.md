<!-- Status: Active document. Reviewed 2026-03-09. Historical or superseded material belongs in docs/archive/. -->

ARCHIVED DOCUMENT
This document describes pre-v3 architecture and is retained for historical reference.

Moved to:
- docs/archive/PHASE5_LEGACY_DECOMMISSION.md

## Recovery Package Decommissioned — 2026-03-07

`tagslut/recovery/` has been fully retired. The stub package (which raised ImportError) has been
deleted. All recovery implementation is archived at `legacy/tagslut_recovery/`.

The recovery phase is complete per REPORT.md. No active code imports `tagslut.recovery`.
