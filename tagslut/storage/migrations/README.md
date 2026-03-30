<!-- Status: Active document. Reviewed 2026-03-09. Historical or superseded material belongs in docs/archive/. -->

# Storage Migrations

Migrations run in filename order via `tagslut.storage.migration_runner`.

Rules:
- Use sequential `NNNN_description` filenames.
- SQL migrations should be idempotent and safe to re-run.
- Python migrations must define `up(conn)` and be side-effect safe.
- Avoid destructive schema changes; prefer additive columns/tables.

To apply pending migrations:

```bash
python -m tagslut.storage.migration_runner <db_path>
```

Verification note:
- Numbered migration modules such as `0015_v3_isrc_partial_unique.py` cannot be imported with `from ... import 0015_...` because Python identifiers cannot start with digits.
- Use `importlib.import_module("tagslut.storage.migrations.0015_v3_isrc_partial_unique")` for in-package verification snippets.
- If loading by path outside the installed package, use `importlib.util.spec_from_file_location(...)`.
