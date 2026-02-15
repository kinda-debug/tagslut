# Handover: OneTagger Workflow (2026-02-09)

## Outcome

OneTagger is now wired as an active operational workflow with simple wrappers:

1. `tools/tag-build`
2. `tools/tag-run --m3u <path>`
3. `tools/tag`

All wrappers call:
- `tools/review/onetagger_workflow.py`

## Defaults

- DB: `TAGSLUT_DB` env var, fallback to `/Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-08/music.db`
- Library root: `/Volumes/MUSIC/LIBRARY`
- OneTagger binary: `/Users/georgeskhawam/Downloads/onetagger-cli`
- OneTagger config output: `/Users/georgeskhawam/.config/onetagger/config.tagslut-missing-isrc.json`
- Work links root: `/Volumes/MUSIC/_work`
- Artifacts output: `artifacts/compare/`
- Tag write scope: `ISRC` only
- Retry behavior: multi-pass on unresolved files (`--max-passes`, default `4`)
- Providers default: `spotify,deezer,musicbrainz`
- DB refresh: writes `canonical_isrc` back to `files` by default

## Pilot Evidence

Pilot input:
- 120 files from missing-ISRC pool (`needs_tagging_missing_isrc_pilot_120_20260209_122332.m3u`)

Pilot run outputs:
- Log: `artifacts/compare/onetagger_pilot_20260209_122603.log`
- Summary: `artifacts/compare/onetagger_pilot_summary_20260209_123137.json`
- File status: `artifacts/compare/onetagger_pilot_file_status_20260209_123137.csv`

Pilot result:
- Success M3U count: 116
- Failed M3U count: 4
- ISRC present after run: 103 / 120 (85.83%)
- Still missing ISRC: 17

Provider observations from pilot log:
- Beatport returned `State: Error` for all 120 attempts in this run.
- MusicBrainz worked but rate-limited heavily.
- Deezer and Spotify produced most successful matches.

## Why Symlink Batches

Direct `.m3u` input to OneTagger in this environment resolves as zero files.
Symlink-batch mode is therefore the stable execution path:
- source files are untouched in place
- OneTagger sees a normal folder scan
- outputs remain auditable

## Command Examples

Build only:
```bash
tools/tag-build
```

Run only:
```bash
tools/tag-run --m3u /Volumes/MUSIC/LIBRARY/needs_tagging_missing_isrc_YYYYMMDD_HHMMSS.m3u
```

Build + run:
```bash
tools/tag
```

DB sync only (no provider calls):
```bash
tools/tag --db-refresh-only
```

Pilot/full-size controls:
```bash
tools/tag --limit 120
tools/tag --threads 12
tools/tag --max-passes 6
```
