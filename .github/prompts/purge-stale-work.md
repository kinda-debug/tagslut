# purge-stale-work

## Goal
Delete confirmed-stale subdirectories from `/Volumes/MUSIC/_work`.

## Do not recreate existing files
This prompt does filesystem deletion only. No code changes.

## Targets — delete these exactly, nothing else

| Path | Reason |
|---|---|
| `/Volumes/MUSIC/_work/absolute_dj_mp3` | Pre-M3U DJ pool snapshot, superseded |
| `/Volumes/MUSIC/_work/bpdl_jimi_jules_20260220` | Old beatportdl batch, ingested |
| `/Volumes/MUSIC/_work/cleanup_20260308_220000` | March cleanup output, stale |
| `/Volumes/MUSIC/_work/discard` | Discard queue, already processed |
| `/Volumes/MUSIC/_work/gig_runs` | Historical gig exports, superseded |

## DO NOT touch

- `/Volumes/MUSIC/_work/fix` — contains live triage FLACs requiring manual review
- `/Volumes/MUSIC/_work/quarantine` — may contain recoverable files

## Steps

1. Verify each target path exists before attempting deletion.
2. For each target: print total file count and size, then delete the
   entire directory tree with `shutil.rmtree`.
3. Confirm each directory is gone after deletion.
4. Print final summary: dirs deleted, total space reclaimed.

## Constraints
- Abort entirely if `/Volumes/MUSIC` is not mounted
- Do not delete anything outside the five listed paths
- No DB changes required
- No tests needed
- Commit with: `chore(filesystem): purge stale _work subdirs`
