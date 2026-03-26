# CLAUDE.md

This file defines how **Claude Code** should behave in this repository. It is **Claude‑specific** and intentionally short. For cross‑tool rules (Claude, Copilot, Cursor, etc.), always defer to `AGENT.md`.

---

## Core principles

- **Single source of truth**: Treat `AGENT.md` as the canonical instructions for all coding agents. Mirror only Claude‑specific details here.
- **Minimal, reversible changes**: Prefer small, focused patches over large rewrites. Always keep changes easy to review and revert.
- **Docs before code**: When behavior and docs disagree, update the docs first, then code, unless the behavior is clearly wrong.
- **Safety first**: Do not run destructive git operations, force pushes, or history‑rewriting commands.

## DJ pipeline

For curated DJ-library work, the primary operator workflow is the explicit 4-stage pipeline:

1. intake masters via `poetry run tagslut intake <provider-url>`
2. build or reconcile MP3 derivatives via `poetry run tagslut mp3 build ...` or `poetry run tagslut mp3 reconcile ...`
3. admit and validate DJ state via `poetry run tagslut dj admit ...` or `poetry run tagslut dj backfill ...`, then `poetry run tagslut dj validate ...`
4. emit or patch Rekordbox XML via `poetry run tagslut dj xml emit ...` or `poetry run tagslut dj xml patch ...`

`tools/get --dj` and `tools/get-intake --dj` are legacy compatibility paths and should not be treated as the recommended curated-library contract.
Use `docs/DJ_PIPELINE.md` as the concise operator reference and `docs/DJ_WORKFLOW.md` for the extended rationale.

---

## Default workflow for “audit and implement changes”

When asked to “audit the docs and implement the needed changes”, Claude should:

1. **Discover context**
   - Read:
     - `AGENT.md`
     - `CLAUDE.md` (this file)
     - `README.md`
     - `docs/` active files only — **not** `docs/archive/` (historical/superseded material)
     - `.github/workflows/` (CI, Claude Code, code-review automation)
     - `.github/prompts/` (any agent prompt customizations)
     - Any other tool‑specific instruction files (e.g. `.cursor/rules`, `copilot-instructions.md`).
   - Build a short internal inventory of:
     - Which agent instruction files exist.
     - How they are currently wired into the tooling (actions, configs, CLI).

2. **Compare “intended” vs “actual”**
   - Identify what the docs say agents should do.
   - Identify what the code and workflows actually do.
   - Look for:
     - Outdated rules.
     - Conflicts between `AGENT.md`, `CLAUDE.md`, and automation.
     - Missing steps for safe application of changes.

3. **Plan before editing**
   - Draft a short plan in markdown (in the conversation), including:
     - Files to change.
     - The minimal edits required.
     - Any open questions or assumptions.

4. **Apply minimal patches**
   - Prefer editing:
     - `AGENT.md` (canonical rules).
     - `CLAUDE.md` (Claude‑specific nuances).
     - Relevant docs in `docs/`.
     - GitHub workflows and config files **only when necessary** to match the documented behavior.
   - Keep edits small and well‑scoped:
     - No mass reformatting.
     - No drive‑by refactors unrelated to the request.

5. **Self‑check**
   - Re‑scan the edited files and verify:
     - There are no obvious contradictions between `AGENT.md`, `CLAUDE.md`, and automation.
     - The instructions are clear for a new contributor and for automated agents.

---

## How Claude should use repository files

When working in this repo, Claude Code should:

- **Prefer these instruction files in this order**
  1. `AGENT.md` (global, vendor‑neutral rules)
  2. `CLAUDE.md` (this file, Claude‑specific)
  3. Any tool‑specific configs (e.g. `.github/workflows/claude.yml`, `.github/prompts/`, `.cursor/rules`, `copilot-instructions.md`)

- **For code changes**
  - Follow the coding style and patterns described in `AGENT.md` and `docs/`.
  - Keep changes localized and include brief comments only when they clarify non‑obvious logic.
  - If you need to add new modules or files, make sure:
    - They fit the existing project structure.
    - You update any relevant documentation.

- **For documentation changes**
  - Keep language concise and actionable.
  - Avoid duplicating long explanations across multiple files; link or reference instead.
  - When updating process or workflow docs, ensure they match the actual GitHub Actions and scripts.

---

## Git and safety guidelines

Claude Code must follow these constraints when proposing or executing git commands:

- **Allowed**
  - `git status`
  - `git diff`
  - `git add` on specific files that were just edited.
  - `git commit` with a clear, conventional message (e.g. `chore: update agent docs`).
- **Forbidden**
  - `git push --force` or any force push.
  - `git rebase --interactive` or history rewriting operations.
  - Deleting branches or tags.

When unsure about a potentially destructive command, **do not run it**. Instead, explain the recommended manual steps for a human to execute.

---

## When to update this file

Claude should update `CLAUDE.md` only when:

- The project’s coding or review standards change.
- The way Claude is integrated (CLI vs GitHub Action vs other) changes.
- New, recurring pitfalls for Claude are discovered.

Keep changes focused on **principles and workflows**, not on one‑off tasks.

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

- **Copilot**: inline completions, quick edits, chat about open files,
  Next Edit Suggestions. Best for: single-file edits, completing patterns,
  explaining unfamiliar code sections.
- **Claude Code CLI** (you): autonomous multi-step tasks, prompt-driven workflows,
  cross-file refactors. Prompts live in `.github/prompts/`. Do not replicate
  those workflows.
- **`@claude` GitHub bot**: issue and PR comment responses, automated code review
  on PRs. Do not duplicate this review work.

When a request involves more than 2 files or requires running commands to verify
behavior, that is within your scope — proceed with cross-file refactors and
command execution directly.

## Active work

Current open task: fix `--resume` mode in `tools/get-intake`.
See `.github/prompts/resume-refresh-fix.prompt.md` for the full specification.
The three root causes are confirmed — do not re-investigate architecture,
only assist with implementing the specified patch.

---

## Keeping `.claude/CLAUDE.md` in sync

There are two copies of this file:

- `CLAUDE.md` (repo root — checked in, reviewed in PRs)
- `.claude/CLAUDE.md` (read by Claude Code CLI at startup)

When editing either copy, apply the identical patch to the other. They must stay in sync.
