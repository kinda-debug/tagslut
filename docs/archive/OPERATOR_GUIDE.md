# Operator Guide (Tailored)

This guide is for your recovery-first workflow.

## Authoritative Roots

- **Source of truth (current)**: `/Volumes/RECOVERY_TARGET/Root`
- **Canonical target (new)**: `/Volumes/COMMUNE/M/Library`
- **Staging**: `/Volumes/COMMUNE/M/01_candidates`

## Workflow (Evidence-First)

### 1) Scan (Read-Only)
Scan sources into a DB. Scans are resumable and incremental by default.

```bash
python3 tools/integrity/scan.py /Volumes/RECOVERY_TARGET/Root
```

### 2) Decide (Read-Only)
Generate a plan without modifying files.

```bash
python3 tools/decide/recommend.py --db "$DEDUPE_DB" --output plan.json
```

### 3) Stage (Manual Approval)
Use candidate lists and copy into:

```
/Volumes/COMMUNE/M/01_candidates
```

Do not copy into `Library` until you approve the staged set.

### 4) Promote (Manual Approval)
After verification, move from `01_candidates` into:

```
/Volumes/COMMUNE/M/Library
```

### 5) Archive Evidence
Archive CSV/JSON outputs to a dated archive folder.

## Stop Conditions

Stop and ask for a decision if:
- A file appears stitched or has unexpected audio after an end point.
- A match is filename-only without checksum evidence.
- You are about to move or delete any file.

## Notes

- Zones are tags only. They do not move files.
- The scanner commits in batches, so work is not lost on interruption.
