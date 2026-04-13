# qobuz-full-intake-pipeline

## Goal
After streamrip downloads a Qobuz URL, route it through the full
get-intake cohort pipeline (precheck → register → enrich → promote →
M3U) instead of the current stub that only calls `index register` and
optionally `intake url --mp3`.

## Do not recreate existing files
Edit `tools/get` only. No other files.

## Problem
The Qobuz branch in `tools/get` (the `elif [[ "$URL" == *"qobuz.com"* ]]`
block) does:
  1. streamrip download
  2. `tagslut index register $STREAMRIP_ROOT --source qobuz --execute`
  3. `tagslut intake url $URL --mp3/--dj` only if --mp3 or --dj passed
  4. `tools/enrich` in auto mode

It never calls `get-intake`, so there is no cohort, no precheck, no
promote to MASTER_LIBRARY, and no M3U output. TIDAL and Spotify both
call `build_intake_cmd` + `exec "${INTAKE_CMD[@]}"` — Qobuz should too.

## Fix

After the streamrip download succeeds, replace the existing
register/intake/enrich stub with a call to `build_intake_cmd` using
source `qobuz` and the `STREAMRIP_ROOT` as the target path (not the
URL, since streamrip has already downloaded — get-intake should process
the local directory).

Specifically:

1. Keep the streamrip download call unchanged.
2. After download succeeds, instead of the manual `index register` +
   `intake url` block, call:
   ```bash
   build_intake_cmd "qobuz" "$STREAMRIP_ROOT/Qobuz" "$@"
   exec "${INTAKE_CMD[@]}"
   ```
   Pass `--enrich` flag to build_intake_cmd if `MODE == enrich`.
   Pass playlist name via `--playlist-name "$PLAYLIST_NAME"` if
   PLAYLIST_NAME is non-empty (resolve it before the download using the
   existing Qobuz API snippet already in the file).

3. The `PLAYLIST_NAME` resolution block should move to BEFORE the
   streamrip download call so the name is available when building the
   intake command.

4. Remove the now-redundant manual `index register`, `intake url`,
   and `tools/enrich` calls at the bottom of the Qobuz block.

## Constraints
- Do not touch any other provider branch (TIDAL, Spotify, Beatport,
  Deezer)
- Do not change `build_intake_cmd` function
- Do not change streamrip invocation
- Preserve `--dj` and `--mp3` flag forwarding — they are already
  handled inside `build_intake_cmd` via `intake_args`
- Commit: `fix(get): route qobuz through full get-intake cohort pipeline`
