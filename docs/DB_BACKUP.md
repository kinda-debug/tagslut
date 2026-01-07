**Database backups**

Location
- Local, secure backup directory: `~/dedupe_db_backups/` (timestamped subfolders).
- Current backups were copied from the working backup at `~/dedupe_repo_reclone_db_backup/`.

Restore
- To restore a backup into the canonical DB location (outside the repo):

```bash
# pick a timestamped folder, e.g. 20251125_164857
cp -a ~/dedupe_db_backups/20251125_164857/. /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-08/
# ensure permissions
chmod -R 700 /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-08
```

Notes
- Database files are intentionally excluded from Git to avoid pushing large blobs and to keep sensitive data out of the repository history.
- Use the provided script `scripts/backup_dbs.sh` to create timestamped backups and rotate older backups (default keeps 7).

Artifacts placeholders

- The repository includes lightweight placeholders for working artifacts (not the DB content itself):
	- `artifacts/manifests/.gitkeep`
	- `artifacts/reports/.gitkeep`
	- These are intended to document and reserve repository structure; actual DB files remain excluded via `.gitignore`.

Script usage

```bash
# run with defaults (source: ~/dedupe_repo_reclone_db_backup, dest: ~/dedupe_db_backups)
./scripts/backup_dbs.sh

# specify custom destination and keep count
./scripts/backup_dbs.sh --src /path/to/working_backup --dest /path/to/backups --keep 14
```
