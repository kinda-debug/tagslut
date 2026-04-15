# Codex Prompt: Fill blank top-level help text — get, tag, fix

**Repo**: `kinda-debug/tagslut` | **Branch**: `dev`
**Save to**: `.github/prompts/sc-03-fill-help-text.md`

---

## Context

Three top-level commands have no `help=` string on their `@cli.command`
decorator, which means `tagslut --help` shows them with no description.
This is a usability gap — all visible commands should be self-describing.

The three commands (all visible in the top-level CLI):
- `get` — primary intake entry point for URLs and local paths
- `tag` — curate/apply/sync tags against the library
- `fix` — resume a blocked cohort or repair a specific file/identity

---

## Grounding pass (stop and report if any fail)

1. Read `tagslut/cli/commands/get.py` — find `register_get_command`, confirm
   the `@cli.command("get")` decorator has no `help=` argument.
2. Read `tagslut/cli/commands/tag.py` — find the command/group registration,
   confirm no `help=`.
3. Read `tagslut/cli/commands/fix.py` — find the command registration, confirm
   no `help=`.
4. Run `poetry run tagslut --help` — verify `get`, `tag`, `fix` appear with
   no description text next to them (or a blank one).
5. Read `docs/SCRIPT_SURFACE.md` lines around `tools/get` and `tagslut auth`
   to understand the intended description language style.
6. Read `.git/logs/HEAD` last 10 lines — confirm branch is `dev`.

If any grounding step fails, stop and report.

---

## Task

Add a `help=` string to the `@cli.command` (or `@cli.group`) decorator for
each of the three commands. Use targeted `str_replace` — do not rewrite the
file.

### `get` command

Locate the decorator in `tagslut/cli/commands/get.py`:

```python
    @cli.command("get")
```

Replace with:

```python
    @cli.command(
        "get",
        help=(
            "Download and ingest a provider URL or local path. "
            "Runs precheck → download → tag → promote → M3U. "
            "Add --dj to build MP3 output with DJ playlists, "
            "--fix to resume a blocked cohort."
        ),
    )
```

### `tag` command / group

Read the actual decorator signature in `tagslut/cli/commands/tag.py` first.
If it is `@cli.command("tag")`, use:

```python
help="Curate, fetch, apply, and sync metadata tags for library files."
```

If it is a `@cli.group("tag")` or registered via `register_tag_group`, add
the help string to whichever decorator controls the top-level `tag` entry.

### `fix` command

Read the actual decorator in `tagslut/cli/commands/fix.py` first.
Add:

```python
help="Resume a blocked cohort or repair a specific file or identity."
```

---

## Verification

After each edit:
1. Re-read the modified function signature to confirm the help string is
   present and syntactically valid.
2. After all three edits, run:
   ```
   poetry run tagslut --help
   ```
   and confirm all three commands now show non-empty description text.

---

## Constraints

- Do not recreate any existing file.
- Do not modify any logic, only the `help=` argument on decorators.
- Do not change option help strings — only the top-level command help.
- Targeted pytest only after the help text change:
  ```
  poetry run pytest tests/cli/ -v -k "not scan"
  ```

---

## Commit

```
fix(cli): add help text for get, tag, fix top-level commands
```
