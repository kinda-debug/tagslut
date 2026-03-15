# AGENT.md

This file defines how **ChatGPT Codex** should behave in this repository. It is **ChatGPT‑specific** and intentionally short. For cross‑tool rules (ChatGPT, Copilot, Cursor, etc.), always defer to `AGENT.md`.

---

## Core principles

- **Single source of truth**: Treat `AGENT.md` as the canonical instructions for all coding agents. Mirror only ChatGPT‑specific details here.
- **Minimal, reversible changes**: Prefer small, focused patches over large rewrites. Always keep changes easy to review and revert.
- **Docs before code**: When behavior and docs disagree, update the docs first, then code, unless the behavior is clearly wrong.
- **Safety first**: Do not run destructive git operations, force pushes, or history‑rewriting commands.

---

## Default workflow for “audit and implement changes”

When asked to “audit the docs and implement the needed changes”, ChatGPT should:

1. **Discover context**
   - Read:
     - `AGENT.md`
     - `.codex/AGENT.md` (this file)
     - `README.md`
     - `docs/` active files only — **not** `docs/archive/` (historical/superseded material)
     - `.github/workflows/` (CI, ChatGPT Codex, code-review automation)
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
     - Conflicts between `.codex/AGENT.md`, `AGENT.md`, and automation.
     - Missing steps for safe application of changes.

3. **Plan before editing**
   - Draft a short plan in markdown (in the conversation), including:
     - Files to change.
     - The minimal edits required.
     - Any open questions or assumptions.

4. **Apply minimal patches**
   - Prefer editing:
     - `AGENT.md` (canonical rules).
     - `.codex/AGENT.md` (ChatGPT‑specific nuances).
     - Relevant docs in `docs/`.
     - GitHub workflows and config files **only when necessary** to match the documented behavior.
   - Keep edits small and well‑scoped:
     - No mass reformatting.
     - No drive‑by refactors unrelated to the request.

5. **Self‑check**
   - Re‑scan the edited files and verify:
     - There are no obvious contradictions between `AGENT.md`, `.codex/AGENT.md, and automation.
     - The instructions are clear for a new contributor and for automated agents.

---

## How ChatGPT should use repository files

When working in this repo, ChatGPT Code should:

- **Prefer these instruction files in this order**
  1. `AGENT.md` (global, vendor‑neutral rules)
  2. `AGENT.md` (this file, ChatGPT‑specific)
  3. Any tool‑specific configs (e.g. `.github/workflows/ChatGPT.yml`, `.github/prompts/`, `.cursor/rules`, `copilot-instructions.md`)

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

ChatGPT Code must follow these constraints when proposing or executing git commands:

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

ChatGPT should update `AGENT.md` only when:

- The project’s coding or review standards change.
- The way ChatGPT is integrated (CLI vs GitHub Action vs other) changes.
- New, recurring pitfalls for ChatGPT are discovered.

Keep changes focused on **principles and workflows**, not on one‑off tasks.
