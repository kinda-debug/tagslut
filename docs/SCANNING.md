# Scanning (Resumable + Verbose)

The primary scanner is:

```
python3 tools/integrity/scan.py
```

## Key Behavior

- **Incremental by default**: skips unchanged files (mtime+size match).
- **Resumable**: progress is committed in batches and automatically flushed every 60 seconds (adaptive commit).
- **Safe**: Pre-flight checks for disk space (50MB min) and write sanity tests ensure your filesystem is healthy before scanning.
- **Verbose**: progress is continuous when enabled in config.

## Defaults (config.toml)

```toml
[integrity]
verbose = true
progress = true
progress_interval = 1
incremental = true
recheck = false
force_all = false
check_integrity = false
check_hash = false
stale_days = 30
parallel_workers = 1
db_write_batch_size = 50
allow_unzoned_paths = true
default_zone = "accepted"
```

## Typical Commands

Scan a root:

```bash
python3 tools/integrity/scan.py /Volumes/RECOVERY_TARGET/Root
```

Scan a quarantine folder:

```bash
python3 tools/integrity/scan.py /Volumes/RECOVERY_TARGET/_QUARANTINE
```

## Notes

- Setting `db_write_batch_size = 1` maximizes safety (slower, but no loss of work).
- Set `default_zone = "quarantine"` when scanning quarantine roots without flags.
