# Agent Instructions (canonical)

This is a CLI-first Python repo. Use these rules for all agents.

## Execution
- Primary wrappers: `ts-get <url> [--dj]`, `ts-enrich [--provider ...]`, `ts-auth [tidal|beatport|qobuz|all]`.
- Legacy 4-stage DJ pipeline is archived; `tools/get --dj` and Rekordbox XML emit are legacy reference only.
- Do not rely on files under `docs/archive/` for current behavior. Start with `docs/README.md`, then read only the active docs relevant to your task.

## DJ pool (current model)
- DJ pool is M3U-based: `ts-get --dj` writes per-batch M3U + global `$MP3_LIBRARY/dj_pool.m3u`.
- No `DJ_LIBRARY` writes and no XML emit in the active workflow.

## Debugging workflow
1) Reproduce via CLI wrappers (ts-get/ts-enrich/ts-auth).
2) Inspect the smallest relevant module.
3) Apply the smallest reversible patch.

## Testing
- Prefer targeted pytest (`poetry run pytest tests/<module> -v`).
- Do not run the full suite unless necessary.

## Constraints
- Do not scan the entire repo; stay scoped.
- Do not modify artifacts, databases, or external volumes; use migrations for DB changes.
- Do not write to `$MASTER_LIBRARY`, `$DJ_LIBRARY`, or mounted volumes.
- Return minimal patches only.
