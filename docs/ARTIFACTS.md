# Artifacts and Evidence

Store evidence outputs outside the repo when possible.

## Recommended Locations

```
/Volumes/COMMUNE/M/00_manifests
/Volumes/COMMUNE/M/01_candidates
/Volumes/COMMUNE/M/02_unmatched
/Volumes/COMMUNE/M/03_reports
```

## Archive Location

```
/Users/georgeskhawam/Projects/dedupe_archive/
```

Use dated folders (e.g. `_ARCHIVE_STATE_YYYYMMDD_HHMMSS`).

## Database Schema (Evidence-First)

The SQLite database (`library_files` table) stores the following key technical evidence:

- `checksum`: The primary bit-identity evidence.
- `checksum_type`: Explicit provenance of the checksum (`STREAMINFO_MD5` or `SHA256_FULL`).
- `integrity_state`: Classification as `valid`, `recoverable` (MD5 mismatch), or `corrupt`.
- `risk_delta`: (In decision plans) Technical differences between duplicates (bitrate, duration).
- `conflict_label`: Highlights `[ACOUSTIC_MATCH | BIT_DIFF]` scenarios.

## Rules

- Do not edit CSV outputs in place.
- Archive before starting a new analysis phase.
- Keep DBs and manifests together in the same archive.
