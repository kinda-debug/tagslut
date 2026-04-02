# Contract Documents

These documents are **normative**. They describe the current runtime behavior of the system as anchored to commit `a060a2b`.

## Documents

- [`metadata_architecture.md`](metadata_architecture.md) — Canonical store, identity key derivation, `resolve_or_create_identity()` guarantees, convergence, confidence normalization, Supabase transaction model
- [`provider_matching.md`](provider_matching.md) — TIDAL and Beatport transport split, auth, ISRC capability, match precedence, rate limits
- [`metadata_row_contracts.md`](metadata_row_contracts.md) — CSV schemas, column definitions, field mapping table

## Governance

Changes to identity resolution, CSV schemas, match precedence, confidence representation, or write-path atomicity **require a contract doc update in the same PR**.

Design docs in `docs/design/` are non-normative. Planning artifacts in `docs/archive/` are historical.

`docs/WORKFLOWS.md` remains normative for operator workflows. For matching and confidence behavior, it defers to these contract docs.
