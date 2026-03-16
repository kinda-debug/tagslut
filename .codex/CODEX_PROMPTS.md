# CODEX_PROMPTS.md

Reusable prompts for Codex tasks.

Bug fix template:
- reproduce with CLI or failing test
- identify smallest fix
- return minimal patch

Refactor template:
- preserve runtime behavior
- modify smallest surface possible
- include verification command
# TASK_PROMPTS.md

Standard task shapes.

Bug fix:
- failing command
- minimal patch
- verification command

DB migration:
- inspect storage/v3
- check migration runner
- confirm schema compatibility

CLI change:
- update command module
- update help text
- update relevant tests

# CODEX_PROMPTS.md

Reusable task prompts for Codex when working in this repository.

Principles
- Start from the failing command, traceback, or test.
- Inspect the smallest relevant module.
- Apply the smallest possible patch.
- Verify with a targeted command or pytest run.

Task types

Bug fix
- reproduce using CLI or failing test
- identify smallest responsible code surface
- return minimal patch
- provide verification command

CLI change
- inspect command module
- update argument parsing or behavior
- update help text if needed
- update relevant tests

Database / migration task
- inspect `tagslut/storage/` and `tagslut/storage/v3/`
- check migration runner
- confirm schema compatibility
- verify with migration tests

DJ pipeline task
- inspect `tagslut/dj/` or `tagslut/exec/`
- modify only the stage involved
- verify with DJ-related tests

Refactor
- preserve runtime behavior
- modify the smallest possible surface
- avoid unrelated cleanup
- include verification command
