# tagslut

Use this first:
- `docs/WORKFLOW_3_COMMANDS.md`

Quick commands:
1. `tools/get <beatport-url>` - download missing + build playlist
2. `tools/get-sync <beatport-url>` - explicit sync mode
3. `tools/get-report <beatport-url>` - report-only (no download)

OneTagger enrichment:
1. `tools/tag-build` - create M3U for library files missing ISRC
2. `tools/tag-run --m3u <m3u-path>` - run `onetagger-cli` for that list
3. `tools/tag` - build + run in one step (ISRC-only, multi-pass retries)

CLI naming:
- `tagslut` is the preferred command name
- `dedupe` is a compatibility alias
