# Global recovery workflow summary

- **Database schema** – The workflow provisions three SQLite tables:
  - `global_files` captures every scanned audio file with path metadata,
    technical attributes, checksum, and optional fingerprint.
  - `global_fragments` stores R-Studio Recognized exports with source paths and
    suggested names.
  - `global_resolved_tracks` records the resolver's latest keeper decision plus
    score, reason, and confidence.
- **Scanning** – `python3 scripts/global_recovery.py scan --root <path> --db <db>`
  ingests any number of source roots into a shared database. Use `--resume` to
  skip unchanged files and `--include-fp` when Chromaprint fingerprints are
  desired.
- **Recognized parsing** – `python3 scripts/global_recovery.py parse-recognized
  <Recognized.txt> --db <db>` loads R-Studio exports into the fragments table.
- **Resolver** – `python3 scripts/global_recovery.py resolve --db <db> --out-prefix
  <prefix>` scores every group, emits keepers/improvements/manual/archives CSVs,
  and upserts decisions into `global_resolved_tracks`.
