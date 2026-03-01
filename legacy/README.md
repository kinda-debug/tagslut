# legacy/

This directory is the single authoritative home for **retired** scripts, shell
wrappers, and historical tooling that has been superseded by the V3 architecture
but is preserved for reference or emergency rollback.

## What belongs here

| Sub-path | Contents |
|---|---|
| `tools/review/` | Retired review-surface scripts (superseded by V3 review tools in `tools/review/`) |
| `scripts/` | Retired one-off migration or diagnostic scripts |
| *(other)* | Any historical shell wrappers or batch files no longer in active use |

## What does NOT belong here

- Active production scripts → `tools/`
- Active migration helpers → `scripts/`
- Python package code → `tagslut/`

## Relationship to `tagslut/legacy/`

**`tagslut/legacy/` does not exist and is not created.**  Keeping a `legacy/`
directory inside the installable Python package would make it importable as
`tagslut.legacy`, creating confusion about the package surface.  All retired
code is consolidated here, at the repository root, and is never imported by the
package.

See `docs/README.md` for the documentation index and full consolidation
decision.
