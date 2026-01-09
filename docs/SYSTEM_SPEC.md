# System Spec (Index)

This repository implements an evidence-first FLAC recovery and deduplication workflow. This file is an index of authoritative documents.

## Core References

- `docs/architecture.md` — system architecture overview.
- `docs/process_flow.md` — end-to-end process flow.
- `docs/RECOVERY_WORKFLOW.md` — recovery-first workflow.
- `docs/FAST_WORKFLOW.md` — fast scan/dedupe workflow.
- `docs/staging_review_playbook.md` — staging review playbook.
- `docs/configuration.md` — config reference.
- `docs/DB_BACKUP.md` — DB backup procedures.
- `docs/scripts_reference.md` — operator scripts reference.
- `docs/repo_inventory.md` — file-by-file inventory and alignment notes.

## Principles (Short Form)

- Evidence-first: never delete or mutate files without an explicit, reviewed plan.
- Deterministic: scans and decisions must be reproducible.
- Auditability: produce CSV/JSON outputs for review before changes.
- Provenance preservation: do not collapse prefixes or sources without evidence.
