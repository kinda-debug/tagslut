# Operator Quickstart (Recovery-First, Evidence-Preserving)

This guide is tailored to your workflow: forensic recovery of FLAC libraries across multiple volumes, with evidence-first constraints and auditable outputs. It assumes:

- **Authoritative on-disk root**: `/Volumes/RECOVERY_TARGET/Root`
- **New canonical staging root**: `/Volumes/COMMUNE/M`
- **No destructive operations** unless explicitly approved
- **All results must be reproducible** (CSV/JSON artifacts)

---

## 0) Working Principles (Do Not Skip)

1. **No deletes, no overwrites.** Treat everything as evidence.
2. **Always produce a report before any action.**
3. **Keep provenance.** Don’t collapse roots without proof.
4. **Use read-only scans first; write only after review.**

---

## 1) Project Layout You Should Know

- **Core tools**: `tools/` (stable CLI entry points)
- **Core library**: `dedupe/` (internal logic)
- **Operator docs**: `docs/` (specs and workflows)
- **Manifests and reports**: `/Volumes/COMMUNE/M/00_manifests` and `/Volumes/COMMUNE/M/03_reports`

Key docs:
- `docs/RECOVERY_WORKFLOW.md`
- `docs/FAST_WORKFLOW.md`
- `docs/scripts_reference.md`
- `docs/repo_inventory.md`

---

## 2) New Canonical Library Target

Your new canonical library lives here:

```
/Volumes/COMMUNE/M/Library
```

We will only copy into this after review. All candidate files live in:

```
/Volumes/COMMUNE/M/01_candidates
```

---

## 3) Current Evidence Artifacts (Already Built)

These are authoritative outputs from earlier analysis:

- `/Volumes/COMMUNE/M/00_manifests/recovery_target_manifest.csv`
- `/Volumes/COMMUNE/M/01_candidates/recovery_candidates.csv`
- `orphans_reconciliation_master.csv`
- `orphans_unmatched_investigation_list.csv`

Use these before any new scan.

---

## 4) Daily Operator Workflow (Recommended)

### Step A — Confirm Inputs (Read-Only)

1. Check that the volumes are mounted read-only:
   - `/Volumes/RECOVERY_TARGET`
   - `/Volumes/COMMUNE`

2. Confirm expected roots exist:
   - `/Volumes/RECOVERY_TARGET/Root`
   - `/Volumes/COMMUNE/M`

### Step A.1 — Default Scanner Behavior (No Flags Needed)

Defaults for `tools/integrity/scan.py` are set in `config.toml` under `[integrity]`.
These defaults make the scan verbose, progress-heavy, resumable, and safe.

### Step B — Use the Candidate List

The file `/Volumes/COMMUNE/M/01_candidates/recovery_candidates.csv` is your current recovery candidate list.

Each row has:
- `relative_path`
- `source` (COMMUNE or QUARANTINE)
- `source_path`
- `checksum`
- `target_path` (under `/Volumes/COMMUNE/M/Library`)

### Step C — Stage Copy (Only When Approved)

The safe process for a single file:

1. Verify source checksum (SHA-256)
2. Copy to `/Volumes/COMMUNE/M/01_candidates/<relative_path>`
3. Re-hash the copied file
4. Record in a manifest (CSV)

**Nothing should go into `/Volumes/COMMUNE/M/Library` until you approve the staged set.**

---

## 5) Handling “Overlong” R-Studio Files

Symptoms:
- Track duration extends beyond expected end
- Possible stitched audio or appended content

Recommended evidence steps:

1. **Duration check** (streaminfo + decoded):
   - `metaflac --show-total-samples --show-sample-rate`
   - `ffprobe -show_entries format=duration`

2. **Tail activity check** (RMS per second or silence detection):
   - Use `ffmpeg` + `silencedetect` to detect real audio after a long silence.

3. **Report and isolate**:
   - Export a CSV with `path`, `decoded_duration`, `last_active_sec`, `tail_silence_sec`.

Do not trim or rewrite audio until the report is reviewed.

---

## 6) When to Stop and Ask for a Decision

Stop and request operator confirmation if:

- The candidate list includes multiple sources for the same checksum
- A file appears to have appended audio or large post‑silence activity
- A “match” relies only on filenames and not checksum
- You are about to copy, move, or rewrite files

---

## 7) Clean Reset Option (If Needed)

If the DB feels compromised or untrustworthy:

1. Archive current DB + artifacts (already done)
2. Create a new DB file (timestamped)
3. Scan only authoritative sources
4. Build dedupe plan from scratch

---

## 8) Who Does What

You should do:
- Decide which sources are authoritative
- Approve any copy/move action
- Review candidate lists before promotion

Codex should do:
- Build reports, manifests, and evidence summaries
- Identify conflicts and anomalies
- Prepare copy plans (dry-run)

---

## 9) Quick Commands (Read-Only)

These commands only read files; they do not modify anything.

### Check a single FLAC duration
```bash
metaflac --show-total-samples --show-sample-rate "/path/to/file.flac"
ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "/path/to/file.flac"
```

### Detect tail silence
```bash
ffmpeg -v info -i "/path/to/file.flac" -af silencedetect=noise=-50dB:d=2 -f null -
```

---

## 10) Where to Put New Evidence

- Reports: `/Volumes/COMMUNE/M/03_reports/`
- Manifests: `/Volumes/COMMUNE/M/00_manifests/`
- Candidate lists: `/Volumes/COMMUNE/M/01_candidates/`

---

## 11) Ask for Help

If you are unsure, don’t proceed.
Ask for a report or a small pilot run instead of a full action.
