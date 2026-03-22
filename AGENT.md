This repository is a CLI-first Python project.

Execution
Run commands via:
poetry run tagslut

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
Return minimal patches only.
