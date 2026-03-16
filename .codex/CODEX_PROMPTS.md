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
