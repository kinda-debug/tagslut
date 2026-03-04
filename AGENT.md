AGENT.md — tagslut Repository Guide

Purpose

tagslut manages large FLAC music libraries and produces deterministic downstream artifacts such as DJ pools.

The system prioritizes:
	•	deterministic workflows
	•	auditable file movement
	•	identity-based track management
	•	reproducible DJ outputs

The FLAC master library is always the source of truth.

⸻

Default Branch Policy

Default branch:

dev

Rules:
	•	dev is protected.
	•	Never commit directly to dev.
	•	All work must be done via topic branches and pull requests.

Example workflow:

dev
 └─ feature branch
     └─ PR → dev


⸻

Core System Invariants
	1.	FLAC master library is canonical.
	2.	MP3 or DJ pools are derived outputs only.
	3.	File moves must be auditable.
	4.	Planning and execution must be separated.

decide → execute → verify

	5.	Runtime outputs must live in:

artifacts/
output/

	6.	Files must never be permanently deleted.
If removal is requested, move items to Trash.

⸻

Repository Structure

Main code:

tagslut/

Operational tools:

tools/review/

Utility scripts:

scripts/

Configuration:

config/

Documentation:

docs/
docs/archive/

Runtime outputs:

artifacts/
output/

Archived material must never override active documentation.

⸻

CLI Command Surface

Preferred commands:

tagslut intake
tagslut index
tagslut decide
tagslut execute
tagslut verify
tagslut report
tagslut auth

Specialized commands:

tagslut export
tagslut dj
tagslut gig
tagslut canonize
tagslut enrich-file
tagslut explain-keeper

Deprecated alias:

dedupe

Scheduled removal:

2026-06-01

Retired commands must not be reintroduced.

⸻

DJ Workflow (v3)

The DJ system is downstream from the FLAC library.

Pipeline:

FLAC library
      ↓
v3 identity index
      ↓
DJ candidate export
      ↓
DJ profile curation
      ↓
DJ ready export
      ↓
DJ pool builder
      ↓
DJ software (Rekordbox / Lexicon)

Rules:
	•	preferred assets must be used when available
	•	orphan identities excluded by default
	•	DJ operations must never modify the master library

⸻

DJ Pool Builder

Implementation:

scripts/dj/build_pool_v3.py

Execution model:

Default mode:

plan

Produces a manifest but does not copy files.

Execution mode:

--execute

Copies or transcodes assets into the pool.

Execution must always be explicit.

⸻

DJ Development Layers

DJ features are split into three layers.

Layer A — Documentation

docs/DJ_POOL.md
docs/DJ_WORKFLOW.md
docs/OPERATIONS.md

Layer B — DJ Curation Layer (B1)

tagslut/db/v3/dj_profile.py
scripts/dj/profile_v3.py
scripts/dj/export_ready_v3.py
tests/test_dj_profile_v3.py
tests/test_export_ready_v3.py

Layer C — DJ Pool Builder (B2)

scripts/dj/build_pool_v3.py
tests/test_build_pool_v3.py
Makefile DJ targets

Each layer should normally be delivered as separate PRs.

Documentation archive operations must never be mixed with code changes.

⸻

Git Hygiene Rules

Prefer explicit path staging.

git add <file>

Avoid staging the whole repository.

If interactive staging is required:

git add -p

Rules:
	•	stage only the intended hunks
	•	reject unrelated help-list changes
	•	reject archive doc churn

Always verify staged files:

git diff --cached --name-only


⸻

Worktree Recovery Procedure

If the working tree becomes contaminated:

git stash push -u -m "wip contaminated worktree"
git fetch origin
git reset --hard origin/dev
git clean -fd

Then restore only required files:

git restore --source=<stash> -- <paths>

Never restore an entire stash blindly.

⸻

Common Commands

Run tests:

poetry run python -m pytest -q

DJ pool plan:

V3_DB=<path> POOL_OUT=<path> make dj-pool-plan

DJ pool execute:

V3_DB=<path> POOL_OUT=<path> make dj-pool-run EXECUTE=1

Direct usage:

python scripts/dj/build_pool_v3.py --db <path> --out-dir <path>
python scripts/dj/build_pool_v3.py --db <path> --out-dir <path> --execute


⸻

Documentation Rules

When behavior changes, update:

docs/WORKFLOWS.md
docs/OPERATIONS.md
docs/SCRIPT_SURFACE.md
docs/SURFACE_POLICY.md
REPORT.md

Historical material must remain under:

docs/archive/

Bulk archive moves must be isolated in their own PR.

⸻

Operational Preferences

Long-running scripts should run in the foreground.

Do not run commands using:

&
nohup
detached sessions

Operators must be able to see command output.

Prefer verbose modes:

-v
-vv
--verbose


⸻

Post-Edit Validation

After changes run:

poetry run python -m pytest -q

Then repository audits:

poetry run python scripts/audit_repo_layout.py
poetry run python scripts/check_cli_docs_consistency.py

If CLI changed:

tagslut <command> --help


⸻
