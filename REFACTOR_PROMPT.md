Below is the revised prompt, with the COMMUNE staging + Yate workflow integrated cleanly and unambiguously, without altering your existing guarantees.

⸻

Repository Refactoring Prompt for AI Agent

Context

You are refactoring a Python-based FLAC music library deduplication and ingestion system.

Repository:
/Users/georgeskhawam/Projects/dedupe_repo_reclone

Primary purpose:
Scan, hash, deduplicate, ingest, and manage FLAC audio files across multiple libraries while preserving integrity, metadata quality, and deterministic behavior.

The codebase has grown organically and now suffers from duplicated logic, unclear boundaries, tool sprawl, and inconsistent error handling.

You have full authority to reorganize, rename, rewrite, and delete code as long as behavior is preserved and validated.

Target Python version: 3.11

⸻

Execution Rules (Read First)
	•	Preserve behavior: Same input must produce the same decisions
	•	No silent failures: All errors must be explicit and logged
	•	No duplication: Each function must exist in exactly one canonical place
	•	Backward compatible: Existing databases must continue to work (additive migrations only)
	•	Test-backed changes only
	•	Terminal-first workflow (no GUI dependencies)

⸻

What Works Today (Must Be Preserved)
	•	FLAC integrity checks via flac -t
	•	Parallel hashing and metadata extraction
	•	SQLite-backed duplicate detection
	•	AcoustID fingerprinting
	•	dupeGuru CSV import/export
	•	Terminal review workflows (fzf + mpv)
	•	Deterministic KEEP / DROP / REVIEW decision engine

⸻

New Required Feature: Staged Ingestion + Yate Integration

Objective

Introduce a controlled ingestion pipeline for new downloads, decoupled from the main library, with explicit tracking and database integration.

Staging Workflow
	•	All newly downloaded or externally sourced audio files are first placed in:

/Volumes/COMMUNE/10_STAGING

	•	Files in 10_STAGING are:
	•	Not considered part of the canonical library
	•	Fully tracked in the same SQLite database as the main library
	•	Marked with a clear library_state or equivalent flag (e.g. staging, accepted, rejected)

Yate Integration
	•	Yate is the only allowed tool to:
	•	Rename files
	•	Rewrite tags
	•	Restructure paths for staged files
	•	Yate operations must be observable and reconcilable:
	•	Pre- and post-Yate paths must be tracked
	•	Database records must be updated after Yate runs
	•	Provide a small integration layer in:

dedupe/external/picard.py

Responsibilities:
	•	Detect tagger-moved/retagged files
	•	Reconcile old paths → new paths
	•	Update the unified database accordingly
	•	Prevent orphaned or duplicated DB entries

Promotion to Canonical Library
	•	Only files that:
	•	Are flac_ok = true
	•	Have valid, normalized metadata
	•	Are not duplicates of existing KEEP files
may be promoted from:

/Volumes/COMMUNE/10_STAGING
→ /Volumes/COMMUNE/20_ACCEPTED

	•	Promotion must be an explicit, logged operation
	•	Promotion must update the database atomically

⸻

Refactoring Objectives

1. Clear Module Boundaries

dedupe/
├── core/            # Pure business logic (no I/O)
│   ├── hashing.py
│   ├── metadata.py
│   ├── integrity.py
│   ├── matching.py
│   └── decisions.py
│
├── storage/         # Persistence layer
│   ├── schema.py        # Additive migrations only
│   ├── queries.py       # Reusable SQL
│   └── models.py        # Typed data models
│
├── external/        # Third-party integrations
│   ├── acoustid.py
│   ├── dupeguru.py
│   └── picard.py       # REQUIRED: staging reconciliation
│
└── utils/
    ├── paths.py
    ├── parallel.py
    ├── logging.py
    └── config.py

Rules:
	•	core/ must be pure and fully testable
	•	All I/O, filesystem mutation, and subprocess calls live outside core/
	•	No circular imports

⸻

2. Function Deduplication Strategy
	•	Inventory all functions
	•	Identify semantic duplicates
	•	Select one canonical implementation
	•	Move it to the correct module
	•	Replace all call sites
	•	Add tests proving behavioral equivalence

⸻

3. Tool Consolidation (Click-based CLIs)

tools/
├── integrity/
│   └── scan.py
├── review/
│   ├── export.py
│   ├── listen.py
│   └── compare.py
├── decide/
│   ├── recommend.py
│   ├── review.py
│   └── apply.py
├── import/
│   ├── dupeguru.py
│   └── acoustid.py
└── ingest/
    ├── stage.py        # register new files into 10_STAGING
    ├── reconcile.py   # reconcile tagger changes
    └── promote.py     # move staging → accepted

All CLIs must:
	•	Share consistent flags and logging
	•	Fail loudly on error
	•	Be deterministic

⸻

4. Data Model Clarity

@dataclass
class AudioFile:
    path: Path
    checksum: str
    duration: float
    bit_depth: int
    sample_rate: int
    bitrate: int
    metadata: dict
    flac_ok: bool
    library_state: Literal["staging", "accepted", "rejected"]
    acoustid: str | None = None

(Other models unchanged.)

⸻

5. Quality Standards
	•	Full type hints (mypy --strict)
	•	Google-style docstrings
	•	Structured logging
	•	Explicit exceptions only
	•	pytest coverage ≥ 70% for core logic
	•	Deterministic outputs
	•	No dead code

⸻

6. Configuration Management

Single source of truth: config.toml

[library]
name = "COMMUNE"
root = "/Volumes/COMMUNE"

[library.zones]
staging = "10_STAGING"
accepted = "20_ACCEPTED"
rejected = "90_REJECTED"

(Database config unchanged.)

Loaded via:

from dedupe.utils.config import get_config


⸻

Validation Criteria (Non-Negotiable)
	•	Zero duplicate functions
	•	No circular imports
	•	mypy --strict passes
	•	pytest ≥ 70% coverage
	•	Staging → Yate → Promote workflow works end-to-end
	•	No orphaned DB rows after Yate moves
	•	No performance regression
	•	Documentation matches reality

⸻

Expected Outcome

A deterministic, testable, and auditable system with:
	•	Clear separation between staging and canonical library
	•	First-class Yate integration
	•	Unified database tracking all file states
	•	Zero duplication
	•	Preserved behavior
	•	Documented migration path

You may freely rename, reorganize, rewrite, and delete code as long as all constraints above are met.
