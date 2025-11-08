# Changelog

## Unreleased

- Freeze detector: prefer targeted process-group kills and use `pkill`/`killall`
  directly (TERM then KILL escalation) when `ffmpeg` hangs. Avoid opening a new
  Terminal window on macOS; fall back to `killall` when `pkill` is unavailable.
  (See `scripts/lib/common.py`)
- Reorganised the project into a `dedupe` package with a unified CLI and shared
  modules for health checks, synchronisation, and quarantine analysis. Legacy
  scripts now delegate to the new package.
- Added architecture, process flow, and configuration documentation under
  `docs/` and refreshed the main README to describe the consolidated workflows.
