# Rebrand Plan - tagslut (2026-02-09)

## Decision

Final product name: **tagslut**.

Compatibility aliases retained:
- `tagslut` (legacy/operator compatibility)
- `taglslut` (typo-tolerant alias)

## Upstream Repo Review

Reviewed source:
- `https://github.com/tagslut/tagslut`
- local inspection clone: `/tmp/tagslut_upstream`

What was reusable:
1. Documentation index pattern (`docs/README.md`).
2. Clear command-centric usage framing in README/docs.
3. Explicit policy/decision-log mindset (`docs/DECISIONS.md` style).

What was intentionally not imported:
1. Typer CLI stack and `src/tagslut` package layout (this repo is already Click-based and operationally mature).
2. Bot/integration modules (outside tagslut scope).
3. Any docs with unresolved conflict markers (found in upstream `docs/operations/scripts.md`).

## Implemented In This Repo

1. Package branding metadata changed to `tagslut` in `pyproject.toml`.
2. New CLI entrypoints:
   - `tagslut`
   - `taglslut`
   - existing `tagslut` preserved
3. New runtime package alias:
   - `tagslut/__init__.py`
   - `tagslut/__main__.py` (supports `python -m tagslut`)
4. Docs updated to establish `tagslut` as preferred invocation while keeping compatibility aliases documented.
5. Added `docs/README.md` as active docs index (adapted from upstream pattern).

## Command Migration Map

Use these replacements for operator docs and shell aliases:

| Old | New (preferred) |
| --- | --- |
| `tagslut intake ...` | `tagslut intake ...` |
| `tagslut index ...` | `tagslut index ...` |
| `tagslut decide ...` | `tagslut decide ...` |
| `tagslut execute ...` | `tagslut execute ...` |
| `tagslut verify ...` | `tagslut verify ...` |
| `tagslut report ...` | `tagslut report ...` |
| `tagslut auth ...` | `tagslut auth ...` |

## Rollout Policy

1. **Now**: `tagslut` is preferred in docs and helper targets.
2. **Transition window**: keep `tagslut` as a fully working alias.
3. **Future (optional)**: emit advisory warning when invoked as `tagslut`.
4. **Removal decision**: defer until all operator automation is migrated.

## Notes

- Internal package/module namespace remains `tagslut/` for now to avoid high-risk churn.
- Wrapper scripts and CLI behavior are unchanged functionally; this is a branding/migration pass.
