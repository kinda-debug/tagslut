# CLAUDE.md

Claude-specific guardrails (canonical rules still in `AGENT.md`).

## Core principles
- Follow `AGENT.md` first; this file adds Claude-only notes.
- Prefer minimal, reversible patches; update docs before code when behavior/docs diverge.
- Safety: no destructive git (no force pushes or history rewrites).

## Current workflow (post-April 2026)
- Active wrappers: `ts-get <url> [--dj]`, `ts-enrich [--provider ...]`, `ts-auth [tidal|beatport|qobuz|all]`.
- DJ pool is M3U-based (`dj_pool.m3u`); 4-stage DJ pipeline and XML emit are legacy (see `docs/archive/`).
- Treat `docs/README.md` as the current active-doc index. Read only the active docs relevant to the task, and treat everything under `docs/archive/` as historical reference only.

## How to audit/edit
1) Read: `AGENT.md`, this file, `docs/README.md`, `.github/prompts/`, and only the active docs/workflows/configs relevant to the task.
2) Plan before editing; keep scope tight; no drive-by refactors.
3) After edits, check for consistency between `AGENT.md`, `CLAUDE.md`, and any automation touched.

## Git hygiene
- Allowed: `git status`, `git diff`, `git add` of touched files, `git commit` with clear message.
- Forbidden: force push, history rewrite, deleting branches/tags.

## Sync rule
Update `.claude/CLAUDE.md` identically whenever this file changes.
