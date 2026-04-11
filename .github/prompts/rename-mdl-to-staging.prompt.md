# DO NOT recreate existing files. DO NOT modify DB or audio files.

# Rename mdl → staging (codebase references only)

## Context

The download staging directory on the audio volume is being renamed from
`/Volumes/MUSIC/mdl` to `/Volumes/MUSIC/staging`. The volume-side rename
is handled manually by the operator BEFORE running this prompt.

This prompt handles only the codebase reference updates.

## Scope

Update every occurrence of the string `mdl` that refers to the staging
directory path in the following files:

### Live code (surgical edits required):
- `tagslut/cli/commands/mp3.py`
- `tagslut/exec/precheck_inventory_dj.py`
- `tests/exec/test_get_intake_console_render.py`
- `tests/exec/test_intake_orchestrator.py`
- `tools/review/promote_replace_merge.py`
- `env_exports.sh`
- `START_HERE.sh`
- `tools/absorb_rbx_bpdl.py`
- `tools/absorb_mp3_to_sort.py`

### Docs and prompts (bulk sed acceptable):
- All `.md` files under `docs/`, `.github/prompts/`, `artifacts/`
- `README.md`, `postman_README.md`, `PROJECT_DIRECTIVES.md`

## Replacement rules

Replace path references only — not the word "mdl" if it appears as part of
an unrelated identifier or variable name unrelated to the staging path.

Specifically replace:
- `/Volumes/MUSIC/mdl` → `/Volumes/MUSIC/staging`
- `/Volumes/RBX_USB 1/mdl` → `/Volumes/RBX_USB 1/staging`
- `$STAGING_ROOT/mdl` → `$STAGING_ROOT` (if mdl was appended redundantly)
- String literals `"mdl"` or `'mdl'` only where context confirms staging dir
- Environment variable values like `MDL_ROOT=...` or `STAGING_ROOT=.../mdl`

Do NOT replace:
- Variable names like `mdl_path`, `mdl_root` — rename those to `staging_path`,
  `staging_root` accordingly
- The word `mdl` inside playlist filenames referenced in tests (e.g.
  `MDL_NEW_TRACKS.m3u`) — that is a playlist name, not a path
- Any occurrence in `docs/archive/` — leave archive docs untouched

## Verification

After edits, run:
```bash
grep -r "/Volumes/MUSIC/mdl" tagslut/ tools/ tests/ env_exports.sh START_HERE.sh
```
Output must be empty (no remaining path references to old location).

## Commit

```
chore(staging): rename mdl → staging in all codebase path references
```

## Operator note

Before running Codex, manually execute on the volume:
```bash
mv /Volumes/MUSIC/mdl /Volumes/MUSIC/staging
mv "/Volumes/RBX_USB 1/mdl" "/Volumes/RBX_USB 1/staging"
```
Then run this prompt.
