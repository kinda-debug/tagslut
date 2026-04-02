# DJ Pipeline Markdown Triage

This triage records the active Markdown surfaces that describe DJ, MP3, or
Rekordbox behavior after the 4-stage pipeline hardening pass.

| File | Classification | Action | Reason |
| --- | --- | --- | --- |
| `README.md` | ESSENTIAL | Updated | Root operator surface must show intake -> mp3 -> dj -> xml as the primary workflow. |
| `AGENT.md` | ESSENTIAL | Updated | Repo-wide agent rules now state the canonical DJ workflow and legacy wrapper status. |
| `CLAUDE.md` | ESSENTIAL | Updated | Claude-specific instructions now mirror the canonical DJ workflow. |
| `.claude/CLAUDE.md` | ESSENTIAL | Updated | Must stay in sync with `CLAUDE.md`. |
| `docs/DJ_PIPELINE.md` | ESSENTIAL | Added | New concise canonical reference for the 4-stage workflow. |
| `docs/DJ_WORKFLOW.md` | ESSENTIAL | Updated | Retained as the extended operator guide; now points to `docs/DJ_PIPELINE.md`. |
| `docs/OPERATIONS.md` | ESSENTIAL | Updated | Day-to-day recipes must match the canonical stage ordering. |
| `docs/SCRIPT_SURFACE.md` | ESSENTIAL | Updated | Command map must classify `mp3` as Stage 2 and `dj` as Stages 3-4. |
| `docs/DJ_POOL.md` | ESSENTIAL | Updated | DJ-pool contract depends on the canonical upstream pipeline reference. |
| `docs/ARCHITECTURE.md` | ESSENTIAL | Updated | Architecture doc must describe the same stage boundaries as the operator docs. |
| `docs/README.md` | ESSENTIAL | Updated | Documentation index must point readers at the canonical pipeline doc first. |
| `docs/audit/DJ_WORKFLOW_AUDIT.md` | ESSENTIAL | Left as-is | Audit evidence remains current and still justifies hard deprecation of wrapper-driven DJ flow. |
| `docs/audit/DJ_WORKFLOW_TRACE.md` | ESSENTIAL | Left as-is | Runtime trace remains valid evidence for legacy branching behavior. |
| `docs/audit/DJ_WORKFLOW_GAP_TABLE.md` | ESSENTIAL | Left as-is | Gap table still matches the hardening target. |
| `docs/audit/MISSING_TESTS.md` | ESSENTIAL | Left as-is | Test-gap inventory still applies as supporting rationale. |
| `docs/audit/DATA_MODEL_RECOMMENDATION.md` | ESSENTIAL | Left as-is | Data-model target remains aligned with current hardening work. |
| `docs/audit/REKORDBOX_XML_INTEGRATION.md` | ESSENTIAL | Left as-is | XML invariants and interoperability guidance remain current. |
| `docs/archive/**` | STALE | Left archived | Historical or superseded material already lives under the archive boundary. |
| `archive/**` | ORPHAN | Left archived | Historical root-level notes and snapshots are not part of the maintained DJ operator surface. |
| Other active Markdown not mentioning DJ, MP3, or Rekordbox | UNRELATED | Left untouched | Outside the scope of DJ-pipeline hardening. |
