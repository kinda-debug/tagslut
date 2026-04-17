# CODEX_PROMPTS.md

Reusable task shapes for work in this repository.

Principles
- Start from a failing command, traceback, or test.
- Inspect the smallest relevant module.
- Apply the smallest possible patch.
- Verify with a targeted command or pytest run.

Task types

Bug fix
- reproduce with CLI or failing test
- identify smallest responsible code surface
- return minimal patch
- provide verification command

CLI change
- inspect command module
- update argument parsing or behavior
- update help text if required
- update relevant tests

Database / migration task
- inspect `tagslut/storage/` and `tagslut/storage/v3/`
- verify migration safety
- confirm schema compatibility
- run migration tests

DJ pipeline task
- inspect `tagslut/dj/` or `tagslut/exec/`
- modify only the stage involved
- verify with DJ tests

Lexicon metadata task
- inspect `tagslut/cli/commands/lexicon.py`, `tagslut/exec/lexicon_import.py`, or `tagslut/dj/reconcile/lexicon_backfill.py`
- preserve backup ZIP/main.db compatibility
- preserve `locationUnique` matching and `canonical_payload_json` source payloads
- verify with Lexicon importer/backfill tests

Refactor
- preserve runtime behavior
- modify the smallest possible surface
- avoid unrelated cleanup
- include verification command
