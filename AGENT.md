# AI Agent Operations Guide

This document provides a concise, prescriptive playbook for an automated AI agent
maintaining the `dedupe` repository and large audio libraries spanning:

* Main library: `/Volumes/dotad/MUSIC`
* Quarantine: `/Volumes/dotad/Quarantine`
* Garbage (confirmed duplicate sink): `/Volumes/dotad/Garbage`

The agent must preserve data integrity, minimise downtime, and avoid rework.

---
## What changed recently (Nov 2025)

- Fast scanner hardened: verbose-by-default output, resumable via SQLite, WAL + busy timeout, periodic commits, CSV snapshots, and a heartbeat status file.
- Watchdog auto-relaunch: `--watchdog` will relaunch the scanner if the heartbeat stalls or is missing.
- New safe mover: `scripts/dedupe_move_duplicates.py` plans and (optionally) executes moves of byte-identical duplicates into Garbage with collision-safe destinations.
- New bootstrap helper: `./setup.sh` to create a venv, verify external tools, and run common tasks (`scan-music`, `scan-quar`, `plan-moves`, `commit-moves`).
- Docs refreshed: README / USAGE updated; this guide augmented with daily loop and safeguards.

If you run into unexpected early exits during long scans, prefer launching via `./setup.sh scan-music` and monitor the heartbeat freshness.

---
## 1. Core Responsibilities

1. Continuous duplicate discovery (fast byte-identical + optional content-level).
2. Health auditing (playback integrity, truncation, stitched segments, duration mismatches).
3. Quarantine triage (classify anomalies, escalate suspicious files for manual review).
4. Safe dedupe actions (dry-run reports, deterministic keeper selection, reversible moves).
5. Automatic recovery from scanner interruptions (watchdog + heartbeat).
6. Clutter reduction (archival of obsolete logs, consolidation of superseded scripts).
7. Documentation freshness (update README / USAGE / architecture notes when flows evolve).

---
## 2. Canonical Tools & Entry Points

| Task | Command / Module | Notes |
|------|------------------|-------|
| Fast duplicate scan | `scripts/find_dupes_fast.py` | MD5 file bytes, resume, heartbeat, watchdog, CSV snapshots |
| Duplicate move planning | `scripts/dedupe_move_duplicates.py` | Dry-run by default, keeper heuristic, writes CSV report |
| Bootstrap helper | `./setup.sh` | Creates venv, verifies tools, and exposes quick-run tasks |
| Health scan (legacy deep) | `scripts/flac_scan.py` | Generates playlists & SQLite index; heavier than fast scan |
| Unified CLI | `python3 -m dedupe.cli` | Sub-commands: `health`, `sync`, `quarantine` |
| Quarantine deep inspect | `dedupe.cli quarantine inspect` | ffprobe + fingerprints + PCM hash |
| Duration mismatch detection | `dedupe.cli quarantine duration` | Reported vs decoded length |
| Sync healthiest staged copies | `dedupe.cli sync` | Moves healthiest version into library |

Always prefer unified CLI for new workflows; legacy scripts only if you need historical artifacts (e.g. old SQLite schemas).

---
## 3. Heartbeat / Watchdog Protocol

The fast scanner writes a heartbeat (default: `/tmp/find_dupes_fast.heartbeat`) with:

```
files_scanned=<int>
total_files=<int>
elapsed_sec=<int>
rate_per_sec=<float>
timestamp=<unix_epoch>
```

Watchdog relaunch conditions:
* Heartbeat file missing.
* Heartbeat age > `--watchdog-timeout` (default 120s) while scan not marked complete.

Agent loop template:
```bash
nohup python3 scripts/find_dupes_fast.py /Volumes/dotad/MUSIC \
  --output /tmp/file_dupes_music.csv \
  --heartbeat /tmp/find_dupes_fast.music.hb \
  --watchdog --watchdog-timeout 180 > /tmp/scan_music.log 2>&1 &
```

If a relaunch occurs, the scanner resumes thanks to cached rows in `~/.cache/file_dupes.db`.

---
## 3.1 Using setup.sh helpers (recommended)

Prefer the helpers for consistent launches and environment activation:

```bash
./setup.sh env            # one-time venv + deps + tool checks
./setup.sh scan-music     # fast scan on MUSIC with watchdog + heartbeat
./setup.sh scan-quar      # fast scan on Quarantine with watchdog + heartbeat
./setup.sh plan-moves     # generate artifacts/reports/planned_moves.csv
./setup.sh commit-moves   # execute moves (writes executed_moves.csv)
```

Heartbeat files default to `/tmp/find_dupes_fast.<target>.hb` and logs to `/tmp/scan_<TARGET>.log`.

---
## 4. Keeper Selection Logic

For duplicate groups (same MD5):
1. Shortest path (fewest components) preferred.
2. Lexicographically earliest path as tie-breaker.
3. Future extension: incorporate bitrate, size, health metadata (if available from health DB).

Agent MUST avoid deleting files directly; instead move losers to Garbage (or stage a CSV for review).

---
## 5. Dedupe Action Workflow (Dry-Run -> Commit)

1. Run fast scan to build / update hashes.
2. Generate move plan:
   ```bash
   python3 scripts/dedupe_move_duplicates.py --db ~/.cache/file_dupes.db \
     --report artifacts/reports/planned_moves.csv
   ```
3. Verify `planned_moves.csv` (manual or scripted heuristics: check for path collisions, confirm all sources exist).
4. Commit move:
   ```bash
   python3 scripts/dedupe_move_duplicates.py --db ~/.cache/file_dupes.db \
     --commit --report artifacts/reports/executed_moves.csv
   ```
5. Post-move verification: run health audit focusing on moved paths to ensure no keeper was accidentally displaced.

Rollback strategy: all moved files reside under Garbage mirroring relative paths. Reverse by moving back if required.

---
## 6. Health Audit Sequence

Lightweight (duration + decode):
```bash
python3 -m dedupe.cli quarantine duration /Volumes/dotad/Quarantine --output artifacts/reports/quarantine_duration.csv
```

Deep inspection (fingerprints + PCM SHA1):
```bash
python3 -m dedupe.cli quarantine inspect /Volumes/dotad/Quarantine --output artifacts/reports/quarantine_inspect.csv --workers 6
```

Library full audit after major dedupe:
```bash
python3 -m dedupe.cli sync --library-root /Volumes/dotad/MUSIC --verify-library --dry-run
```

Escalate anomalies (ratio mismatches, multiple fingerprints, truncated flags) into a `PLAYLIST_REVIEW.m3u` for manual QA.

---
## 7. Clutter Management Rules

Purge or archive when:
* Log files older than 14 days: move to `archive/logs/YYYYMMDD/`.
* Intermediate CSV snapshots superseded by final reports: retain only the latest per root path.
* Temporary `.wav` extraction artifacts (window fingerprints) must be deleted immediately after use (already implemented).
* Orphaned heartbeat files with age > 1 day AND no active scan process: delete.

Do NOT delete:
* Any file under `artifacts/reports/` generated in the last 30 days.
* Original source audio pending manual quality verification.

---
## 8. Script Consolidation Policy

Prefer the following authoritative set:
* `scripts/find_dupes_fast.py` – fast MD5/resumable + watchdog.
* `scripts/dedupe_move_duplicates.py` – move planner/executor.
* Unified CLI (`dedupe/cli.py`) for health/quarantine/sync.

Candidates for deprecation (replace with CLI equivalents):
* `simple_quarantine_scan.py` → `quarantine inventory`
* `detect_playback_length_issues.py` → `quarantine duration`
* `analyze_quarantine_subdir.py` → `quarantine inspect`

Agent deprecation procedure:
1. Confirm CLI parity (fields & semantics) vs legacy output.
2. Move legacy script to `archive/deprecated/` with a stub comment referencing replacement.
3. Update README & USAGE to remove references.
4. Run tests + sample CLI invocation to prove substitution.

---
## 9. Documentation Update Checklist

After any functional change (schema, keeper heuristic, heartbeat format, CLI option):
1. Edit `README.md` – high-level capability & quick-start.
2. Edit `USAGE.md` – concrete command examples.
3. Edit `docs/architecture.md` – data flow diagrams and updated components.
4. Commit with conventional message: `docs: update heartbeat spec & keeper heuristic`.
5. If scripts removed: add a `CHANGELOG.md` entry under `Removed`.

---
## 10. Safety & Verification Gates

Before committing dedupe moves:
* Ensure `planned_moves.csv` row count == sum of (duplicate group sizes - 1).
* Confirm no source path equals any existing destination path (collision avoidance).
* Ensure heartbeat age < 2 × interval during active scan (freshness check).

Post-move:
* Re-run fast scan to validate no unintended keeper loss.
* Optional: spot-audit random moved files for silent corruption (`ffmpeg -v error -i FILE -f null -`).

---
## 11. Extensibility Hooks

Future agent upgrades can leverage:
* Additional metadata DB linking health scores to duplicate decisions.
* Rolling Bloom filter for quick seen-file detection during continuous ingestion.
* Structured JSON heartbeat for richer watchdog triggers (success state, last commit batch, etc.).

---
## 12. Minimal Daily Loop (Agent Cron Blueprint)

1. Verify/no-op upgrade environment (dependencies present).
2. Launch/ensure fast scan watchdog for MUSIC.
3. On completion or after daily threshold: generate/update duplicate move plan.
4. Run quarantine duration + inspect deltas; flag anomalies.
5. If move plan unchanged from previous day: skip commit; else produce dry-run diff.
6. Archive yesterday's logs; purge stale heartbeats.
7. Update AGENT.md if operational heuristics changed.

---
## 13. Glossary

* **Keeper** – The retained file within a duplicate group.
* **Loser** – A duplicate file scheduled for move to Garbage.
* **Heartbeat** – Small status file enabling external liveness monitoring.
* **Watchdog** – Loop that relaunches the scanner if the heartbeat stalls.
* **Quarantine** – Holding area for files requiring manual inspection or repair.
* **Garbage** – Destination for confirmed duplicates; reversible storage.

---
## 14. Change Log Tracking

All operational changes must append a line to `CHANGELOG.md` under the proper
section and reference the commit hash implementing the change.

---
## 15. Anti-Patterns (Avoid)

* Piping long-running scanner output directly to `head` (kills process via SIGPIPE).
* Deleting duplicates without producing a CSV audit.
* Running content-level hashing (PCM) on every file unconditionally (only for anomaly cohorts).
* Editing legacy scripts when CLI modules already expose equivalent behaviour.

---
## 16. Quick Commands Reference

```bash
# Fast scan with watchdog
python3 scripts/find_dupes_fast.py /Volumes/dotad/MUSIC --watchdog --heartbeat /tmp/find_dupes_fast.music.hb --output /tmp/file_dupes_music.csv

# Generate dedupe move plan
python3 scripts/dedupe_move_duplicates.py --db ~/.cache/file_dupes.db --report artifacts/reports/planned_moves.csv

# Commit moves
python3 scripts/dedupe_move_duplicates.py --db ~/.cache/file_dupes.db --commit --report artifacts/reports/executed_moves.csv

# Quarantine deep inspection
python3 -m dedupe.cli quarantine inspect /Volumes/dotad/Quarantine --output artifacts/reports/quarantine_inspect.csv --workers 6

# Duration mismatches
python3 -m dedupe.cli quarantine duration /Volumes/dotad/Quarantine --output artifacts/reports/quarantine_duration.csv

# Library sync dry-run
python3 -m dedupe.cli sync --library-root /Volumes/dotad/MUSIC --dry-run --verify-library
```

---
## 18. Codex/ChatGPT operator prompt

For running this repo via ChatGPT/Codex, use the prompt in `CODEX_PROMPT.md`. It encodes goals, guardrails, and the exact helper commands to use.

---
## 17. Final Notes

The agent should prefer incremental, low-risk operations with verifiable side
effects (CSV, heartbeat, logs). Human review points: move plans, anomaly spike
reports, and any change reducing redundancy safeguards.
