# Copilot Instructions

tagslut is a CLI-first Python project for building and managing DJ-ready music libraries.
It uses a dual-provider metadata architecture (Beatport + TIDAL) with a SQLite/Supabase
backend and a v3 identity model as the canonical source of truth.

## Canonical entrypoint

The only supported CLI entrypoint is:

    poetry run tagslut

Do not suggest alternative invocations or new entrypoints.

## Architecture

- Identity model: `track_identity → asset_link → asset_file`
- Providers: Beatport (primary), TIDAL (cross-source verification), Deezer, Traxsource, MusicBrainz
- Storage: SQLite (local dev), Supabase/PostgREST (production)
- All complex atomic writes go inside Postgres RPC functions — PostgREST has no
  client-side multi-step transaction support
- DJ pipeline: `FLAC → tagslut mp3 → tagslut dj → Rekordbox XML export`
- Intake pipeline: `tools/get` → `tools/get-intake` (precheck → download → scan →
  identify → audit → plan → apply → m3u → DJ → enrich/art)

## Working rules

- Start from a failing command or test — never from assumptions.
- Inspect the minimal code surface before proposing changes.
- Prefer small, reversible patches. No repo-wide refactors.
- Do not touch database files, migrations, schema, or external volume paths.
- Do not modify `artifacts/`, `output/`, or any operational log files.
- Targeted pytest only — do not run the full suite unless explicitly asked:

      poetry run pytest tests/<specific_module> -v

## Code style

- Python: follow existing patterns in `tagslut/`. No new dependencies without discussion.
- Bash: `set -euo pipefail`. Use the helper functions already defined in `tools/get-intake`
  (`clr`, `kv`, `step`, `run_cmd`, `err`) rather than inventing new ones.
- Commits: conventional format — `fix(scope): description`, `feat(scope): description`,
  `chore(scope): description`. Scope is the primary file or module changed.

## Key boundaries

- `tagslut.exec.get_intake_console` — the Rich wrapper. Do not modify it.
- `tagslut_db/` — database files. Do not modify.
- `artifacts/` — operational output. Do not modify.
- `docs/archive/` — superseded material. Do not read or update.

## Tool division of labor

This repo uses multiple AI tools. Stay in your lane:

- **Copilot** (you): inline completions, quick edits, chat about open files,
  Next Edit Suggestions. Best for: single-file edits, completing patterns,
  explaining unfamiliar code sections.
- **Claude Code CLI**: autonomous multi-step tasks, prompt-driven workflows,
  cross-file refactors. Prompts live in `.github/prompts/`. Do not replicate
  those workflows.
- **`@claude` GitHub bot**: issue and PR comment responses, automated code review
  on PRs. Do not duplicate this review work.

When a request involves more than 2 files or requires running commands to verify
behavior, suggest using Claude Code instead of attempting it inline.

## Active work

Current open task: fix `--resume` mode in `tools/get-intake`.
See `.github/prompts/resume-refresh-fix.prompt.md` for the full specification.
The three root causes are confirmed — do not re-investigate architecture,
only assist with implementing the specified patch.
