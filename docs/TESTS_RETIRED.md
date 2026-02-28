# Retired Tests

## `tests/test_mgmt_workflow.py`

Retired during the audit cleanup because it exercises the hidden/retired `_mgmt` command group.

Rationale:
- `.claude/AGENTS.md` marks `mgmt` as a retired wrapper on the CLI surface.
- Canonical surfaces are: `intake`, `index`, `decide`, `execute`, `verify`, `report`, and `auth`.
