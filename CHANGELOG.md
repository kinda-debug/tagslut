# Changelog

## Unreleased

- Freeze detector: prefer targeted process-group kills and use `pkill`/`killall`
  directly (TERM then KILL escalation) when `ffmpeg` hangs. Avoid opening a new
  Terminal window on macOS; fall back to `killall` when `pkill` is unavailable.
  (See `scripts/lib/common.py`)
