This repository is a CLI-first Python project.

Execution
Run commands via:
poetry run tagslut
The `dedupe` alias has been removed.

DJ pipeline (canonical)

Build curated DJ libraries with this 4-stage workflow:

1. Intake masters: `poetry run tagslut intake <provider-url>`
2. Build or reconcile MP3s: `poetry run tagslut mp3 build ...` or `poetry run tagslut mp3 reconcile ...`
3. Admit and validate DJ state: `poetry run tagslut dj backfill ...`, then `poetry run tagslut dj validate ...`
4. Emit or patch Rekordbox XML: `poetry run tagslut dj xml emit ...` or `poetry run tagslut dj xml patch ...`

`tools/get --dj` and `tools/get-intake --dj` are legacy wrapper paths and are not the supported curated-library workflow.
See `docs/DJ_PIPELINE.md`.

Debugging workflow

1. Reproduce using the CLI.
2. Inspect the smallest relevant module.
3. Apply the smallest possible patch.

Testing
Prefer targeted pytest runs.

Do not run the full test suite unless necessary.

Constraints
Do not scan the entire repository.
Do not modify artifacts, databases, or external volumes.
Do not modify DB files directly - use migrations only.
Do not write to $MASTER_LIBRARY, $DJ_LIBRARY, or any mounted volume.
Return minimal patches only.
