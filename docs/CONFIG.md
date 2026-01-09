# Configuration (Minimal)

`config.toml` is loaded from the repo root or `~/.config/dedupe/config.toml`.

## Recommended Minimal Config

```toml
[library]
name = "COMMUNE"
root = "/Volumes/COMMUNE/M"

[library.zones]
staging = "01_candidates"
accepted = "Library"

[db]
path = "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db"

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
db_write_batch_size = 500
db_flush_interval = 60 # seconds
min_disk_space_mb = 50
allow_unzoned_paths = true
default_zone = "accepted"

[decisions]
zone_priority = ["accepted", "staging"]
metadata_tiebreaker = true
```

## Notes

- Zones are tags used by decision logic only.
- `allow_unzoned_paths` + `default_zone` keep scans from failing on non-COMMUNE paths.
