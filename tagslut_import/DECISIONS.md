# Decisions (Authoritative)

> Keep this file short. Each item has a one-line rule and a rationale.
> When you change a rule, update ``.policy.toml`` and add a new entry here.

## 2025-10-22 — Apple lyrics banned; iTunes public API allowed for metadata only
- **Rule:** Do **not** fetch lyrics from Apple Music. You **may** use
  ``itunes.apple.com/{search|lookup}`` for basic metadata.
- **Rationale:** Closed/fragile endpoints and licensing ambiguity. Public iTunes
  APIs are auditable and aligned with compliance requirements.

## 2025-10-22 — Quality ladder (lossless-only)
- **Rule:** Preferred order: 1) Qobuz 24/192, 2) Tidal Max 24/192, 3) Qobuz
  24/96, 4) Tidal Max 24/96, 5) Qobuz 16/44.1, 6) Tidal Lossless 16/44.1.
  **Abort if no FLAC.**
- **Rationale:** Deterministic, highest fidelity first. Avoid lossy outputs even
  when only metadata is requested.

## 2025-10-22 — Provenance must be written for all tag writes
- **Rule:** The cascade must emit a per-track provenance JSON sidecar via
  ``write_provenance_json``.
- **Rationale:** Ensures the enrichment pipeline remains auditable and compliant
  with policy guard checks.
