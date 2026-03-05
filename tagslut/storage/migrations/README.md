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
