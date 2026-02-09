# 3-Command Workflow

This is the default Beatport workflow.

1. `tools/get <beatport-url>`
- Download missing tracks and build the playlist.

2. `tools/get-sync <beatport-url>`
- Same as above, explicitly named sync mode.

3. `tools/get-report <beatport-url>`
- Report-only check. No download.

Notes:
- Preferred CLI brand is `tagslut`.
- `dedupe` still works as a compatibility alias.
- For advanced commands, see `docs/SCRIPT_SURFACE.md`.
