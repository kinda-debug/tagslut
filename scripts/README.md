Short notes about the `scripts/` folder

This repository contains a set of small helper scripts (both shell and Python)
that are useful as command-line utilities. To reduce clutter at the repository
root these helper scripts were moved into the `scripts/` directory.

Moved files (as of 2025-11-03):
- `stage_hash_dupes.sh`
- `apply_dedupe_plan.py`
- `check_dedupe_plan.py`
- `remove_repaired.py`
- `repair_unhealthy.py`
- `verify_post_move.py`

Notes:
- These files are intended to be executed directly (they include shebangs).
- If you have any shell aliases, cron jobs, or tooling that referenced the old
  top-level paths, either update them to point to `scripts/<name>` or create
  a small symlink at the repository root (e.g. `ln -s scripts/apply_dedupe_plan.py apply_dedupe_plan.py`).
- The scripts were moved without changing content. If you'd prefer I can add
  small wrapper entrypoints that import from package modules instead of moving
  files.

How to run:

```bash
# Make sure the scripts directory is on your PATH or invoke them directly:
python3 scripts/apply_dedupe_plan.py --dry-run
bash scripts/stage_hash_dupes.sh "$DB" "/Volumes/dotad/MUSIC" 25 true
```

If you'd like a different organization (e.g. keep top-level stubs, or convert
these into proper CLI entrypoints), tell me and I can implement that.

Root shims
---------

Small root-level shim wrappers were created so the old top-level command names
continue working (they forward to `scripts/<name>`). The shims are lightweight
bash wrappers that exec the real script and pass through all arguments.

Shims added:
- `apply_dedupe_plan.py`
- `check_dedupe_plan.py`
- `remove_repaired.py`
- `repair_unhealthy.py`
- `verify_post_move.py`
- `stage_hash_dupes.sh`

If you prefer symlinks instead of shims, I can switch them; shims are
portable across platforms and ensure `python3` is used for the Python tools.
