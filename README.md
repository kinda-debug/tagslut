# tagslut

Tagslut is a recovery-first music library deduplication and metadata orchestration toolkit.
It focuses on safe ingest, deterministic decisioning, and audit-friendly execution for large FLAC libraries.

> ⚠️ **`dedupe` alias retiring June 2026** — If you use the `dedupe` command, migrate to `tagslut` now.
> Replace `dedupe [args]` with `tagslut [args]`. The alias emits a deprecation warning on every
> invocation and will be removed on **2026-06-01**.

## Install

```bash
poetry install
```

## Most Useful Commands

```bash
poetry run tagslut --help
poetry run tagslut intake --help
poetry run tagslut index --help
poetry run tagslut decide --help
poetry run tagslut execute --help
```

## Documentation

See `docs/README.md` for the full documentation index.

Key docs:

- `docs/WORKFLOWS.md`
- `docs/OPERATIONS.md`
- `docs/ARCHITECTURE.md`
- `docs/TROUBLESHOOTING.md`
- `docs/DJ_REVIEW_APP.md`
- `docs/DJ_WORKFLOW.md`
- `docs/PROJECT.md`
- `docs/PROGRESS_REPORT.md`

## Development

```bash
poetry install
poetry run pytest tests -x -q
```

## License

See `LICENSE`.
