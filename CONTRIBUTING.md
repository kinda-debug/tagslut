# Contributing

Thank you for considering a contribution! To keep changes predictable, please:

## Workflow
- Discuss large changes in an issue before opening a pull request.
- Keep pull requests small and focused; reference any multi-step roadmap (for example, a "PR 1–15" plan) so reviewers understand the scope.
- Avoid altering scanning, matching, ingest, dedupe, fingerprinting, or recovery logic unless explicitly requested.

## Testing
- Install runtime dependencies (see `requirements.txt` or `pyproject.toml`).
- Run the full test suite with `pytest` before submitting a PR.
- Run `flake8` for linting when modifying Python files.

## CLI usage
- From the repository root, invoke the CLI with `python3 -m dedupe.cli --help` for available commands.
- Example scan: `python3 -m dedupe.cli scan-library --root /path/to/library --db /absolute/path/to/library.db --resume-safe --verbose`.

## Style conventions
- Follow PEP 8 and prefer explicit type hints for new functions and methods.
- Add concise docstrings to new modules, classes, and functions.
- Keep argument names stable and document new CLI options with `--help` text.
