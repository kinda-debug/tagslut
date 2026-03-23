# Replacing `--dj`: Four Explicit Stages Instead of One Leaky Flag

**Date:** 2026-03-23

---

## Introduction

For a long time the DJ workflow in this project was managed by a flag: `--dj`. Pass it to
`tools/get` or `tools/get-intake`, and the system would "do DJ stuff." It was never clear
exactly what that meant. It depended on whether tracks were newly promoted or already in
the precheck cache. It depended on whether ffmpeg succeeded quietly. It depended on whether
you remembered to run Lexicon backfill before exporting to Rekordbox—or whether you knew that
step existed at all.

This post describes what was broken about that model, what replaced it, why the new
structure is operationally more honest, and what risks remain.

---

## What Was Broken

### The `--dj` flag had two divergent code paths

The core problem with `tools/get-intake --dj` was that it behaved differently depending
on whether the track was being newly promoted or had already been seen and suppressed by
the precheck stage.

- **Newly promoted tracks**: ffmpeg was called, MP3s were built, a DJ pool entry was created.
- **Precheck hit (already in library)**: the promote branch was skipped, so the DJ branch
  was also skipped. Only an M3U was generated. No MP3s were created. No error was emitted.

This was a silent failure. The command returned zero. The operator had no signal that the DJ
library hadn't been updated. They would discover it later—typically by noticing Rekordbox had
nothing new to import.

A concrete example of the breakage:

```bash
# First run: tracks are new → MP3 build runs → DJ pool updated
tools/get-intake --dj "https://www.beatport.com/release/12345"

# Same URL the next week: tracks are precheck hits → No MP3 build → DJ pool not updated
tools/get-intake --dj "https://www.beatport.com/release/12345"
# Output looks normal. DJ pool silently unchanged.
```

### ffmpeg failures were invisible

When MP3 generation did run, transcoding failures weren't surfaced. The code called ffmpeg,
checked the exit code, and proceeded. But a zero exit code from ffmpeg does not mean the
output MP3 is valid. Codec warnings, truncated writes due to disk pressure, and malformed
output could all produce a zero exit with a broken file.

There was no file size check. No parsing with mutagen. No duration check. The MP3 was
registered in the database as `status='verified'` and placed in the DJ pool—even if it was
corrupted or empty.

The operator would only find out when Rekordbox silently failed to import the track.

### Enrichment was optional when it shouldn't have been

The Lexicon DJ backfill step—the step that imports energy, danceability, popularity, and key
data from a Lexicon export—was documented as optional and was not part of the canonical DJ
workflow at all.

`dj xml emit` would proceed and generate valid Rekordbox XML even if none of those fields
had been populated. The XML was structurally correct but missing the metadata fields that
make a DJ library useful. Rekordbox would import the tracks, and the operator would notice
only in the player that key and energy values were absent.

### Three entry points for the same operation

There were three distinct places where DJ pool behavior was implemented:

1. `tools/get-intake --dj` — shell wrapper with the branching logic described above
2. `tagslut/dj/export.py` — a CLI module
3. `scripts/dj/build_pool_v3.py` — a lower-level script left from an earlier version

Each had different validation behavior, different error handling, different output formats.
A bug fixed in the CLI module would not fix the same bug in the wrapper. An operator who
learned the wrapper syntax and then switched to the CLI would get different results.

---

## The New Model

The DJ workflow is now a linear four-stage pipeline. Each stage writes explicit DB state
and is safe to re-run. The stages must be run in order.

### Stage 1 — Intake Masters

```bash
poetry run tagslut intake <provider-url>
```

This stage is responsible only for canonical identity. It ingests FLAC masters, creates
`track_identity` rows, links them to `asset_file` rows with `role='master'`, and records
enrichment from the provider (Beatport or TIDAL). Nothing DJ-specific happens here.

### Stage 2 — Register the MP3 Library

If you are building MP3s from FLAC masters:

```bash
poetry run tagslut mp3 build \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-root "$DJ_LIBRARY" \
  --execute
```

If you already have MP3s on disk and want to link them to canonical identities without
re-transcoding:

```bash
poetry run tagslut mp3 reconcile \
  --db "$TAGSLUT_DB" \
  --mp3-root "$DJ_LIBRARY" \
  --execute
```

`mp3 reconcile` is the path for retroactive admission. If you have a DJ MP3 pool that
predates the v3 database, you run this once to register every file against a canonical
identity. It matches by ISRC (high confidence), then Spotify ID, then normalized
title+artist. Matches are logged in `reconcile_log` with confidence level.

Post-transcode validation is in place for `mp3 build`: after ffmpeg exits, the output
file is checked for existence, minimum size, mutagen readability, and duration greater
than one second. A `TranscodeError` is raised before the file is registered if any check
fails. The database does not see a bad output.

### Stage 3 — Admit and Validate the DJ Library

Bulk-admit all `mp3_asset` rows with `status='verified'`:

```bash
poetry run tagslut dj backfill --db "$TAGSLUT_DB"
```

Or admit a specific track:

```bash
poetry run tagslut dj admit \
  --db "$TAGSLUT_DB" \
  --identity-id <id> \
  --mp3-asset-id <id>
```

Then validate:

```bash
poetry run tagslut dj validate --db "$TAGSLUT_DB"
```

`dj validate` checks that admitted tracks have their MP3 files on disk, basic metadata
present, and no fatal inconsistencies in the admission table. On success it writes a
`dj_validation_state` row keyed to the current DJ DB `state_hash`.

That state hash is the gate for Stage 4.

### Stage 4 — Emit Rekordbox XML

```bash
poetry run tagslut dj xml emit \
  --db "$TAGSLUT_DB" \
  --out rekordbox.xml
```

`dj xml emit` queries `dj_validation_state` for a passing record whose state hash
matches the current DJ DB state before it does anything else. If the library has
changed since the last `dj validate` run—new admissions, deleted entries, playlist
changes—the state hash will not match and emit will refuse to proceed. You re-run
`dj validate` and then emit again.

For incremental re-exports that preserve Rekordbox cue points:

```bash
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --out rekordbox_v2.xml
```

`dj xml patch` verifies a manifest hash of the prior export before proceeding,
preserves the `dj_track_id_map` assignments (so Rekordbox TrackIDs don't rotate),
and merges new or removed admissions into the updated XML.

---

## Why This Is Better Operationally

### Each stage has observable output

When `mp3 build` finishes, you can query `mp3_asset` and see exactly which files were
registered, at what confidence, with what status. When `dj backfill` finishes, `dj_admission`
has the authoritative set of admitted tracks. There is no implicit state carried by the
wrapper's execution path.

### Bad transcodes are caught before they enter the pool

The post-transcode validation means a broken ffmpeg run produces a logged error, not a
silent broken file in the DJ pool. The file is never registered if it fails validation.

### The XML emit gate catches state drift

The state-hash check between `dj validate` and `dj xml emit` means you cannot accidentally
export stale state. If you admit five new tracks and then try to emit without validating
again, the emit fails with an explicit message. This replaces the previous situation where
emit had no preconditions and could export whatever was in the database, valid or not.

### Stable TrackIDs mean Rekordbox metadata survives re-exports

TrackIDs are persisted in `dj_track_id_map`. A track admitted last month and re-emitted
today gets the same TrackID. Rekordbox cue points, beat grids, and comments are keyed
to TrackIDs. When IDs are stable across exports, that work survives.

### Retroactive admission is an explicit operation

`mp3 reconcile` lets you register an existing directory of MP3s against canonical
identities without rebuilding anything. Before this, if you had an existing DJ pool that
predated the database, the only option was to rely on the wrapper or touch each file
manually. Now it is a single command that produces an audit log.

---

## Remaining Risks

**The legacy wrappers still exist.** `tools/get --dj` and `tools/get-intake --dj` are
deprecated, emit warnings, and are not the supported workflow. They are not removed. An
operator who does not read the deprecation notice will use them and get non-deterministic
results. There is no removal deadline set.

**Lexicon backfill is still optional.** The step that populates energy, danceability, BPM
refinements, and key data from a Lexicon DJ export is not part of the canonical 4-stage
pipeline. You can run `dj xml emit` without it. The XML will be valid and Rekordbox will
import it, but energy and danceability fields will be empty. There is no warning at emit
time unless you know to look. This is a documentation gap as well as a workflow gap.

**Title+artist matching in `mp3 reconcile` produces false positives.** When an MP3 has no
ISRC in its ID3 tags, reconcile falls back to normalized title+artist comparison. A remix
and its original can share the same title and artist string under that normalization, which
means the remix registers against the wrong canonical identity. There is no confidence
scoring that would surface this to the operator. There is no manual override path in the
current CLI. Suspect rows end up in `reconcile_log` but nothing surfaces them for review.

**`dj validate` does not check enrichment completeness.** The validate step checks that
MP3 files exist and have basic metadata, but it does not check whether the canonical
identity has been enriched with DJ-relevant fields. An admitted track whose `canonical_payload_json`
is missing energy or key will pass validation and enter the XML export.

**No readiness state machine exists yet.** The data model recommendation calls for
`mp3_asset.readiness` and `dj_admission.readiness` columns to make state explicit (playable,
suspect, orphaned, stale). These columns do not exist in the schema. The admission table
has `status` but it does not distinguish "I am not sure this is the right track" from "this
file is unreadable." This is planned work, not completed work.

**No Rekordbox round-trip.** Changes made inside Rekordbox—playlist edits, cue point
placements, track annotations—do not flow back into the database. The system is one-way:
DB to Rekordbox XML. If you reorganize playlists in Rekordbox, those changes are invisible
to tagslut. `dj xml emit` will overwrite your Rekordbox playlist structure the next time you
run it (unless you use `patch` and the admitted-set hasn't changed). A `dj xml import`
command is described in the architecture docs as future work. It does not exist yet.

**`--skip-validation` exists.** It prints a warning to stderr and then proceeds. It is
documented as an emergency hatch. In practice, emergency hatches get used whenever the
normal path is inconvenient. The flag is not going away, but operators should treat it the
same way they treat `--force`: something to use once, document why, and clean up afterward—
not a routine part of the workflow.

---

## A Concrete Workflow Example

You downloaded a new Beatport release last week via `tools/get`. The FLAC masters landed
in `$MASTER_LIBRARY`. You want them in your DJ pool and in Rekordbox.

```bash
# 1. Confirm identity and enrichment exist for the new tracks
poetry run tagslut intake "https://www.beatport.com/release/12345"

# 2. Build MP3 derivatives from the FLAC masters
poetry run tagslut mp3 build \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-root "$DJ_LIBRARY" \
  --execute

# 3. Admit the new MP3s into the DJ layer
poetry run tagslut dj backfill --db "$TAGSLUT_DB"

# 4. Validate the DJ library state
poetry run tagslut dj validate --db "$TAGSLUT_DB"

# 5. Emit updated XML — only works if step 4 passed and state hasn't changed since
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --out rekordbox_v2.xml
```

Five explicit commands. Each one either succeeds with auditable DB state or fails with a
clear error. If `mp3 build` reports a `TranscodeError`, you know which file and why. If
`dj xml emit` refuses to proceed, you know the state hash changed and you know what to do.
Nothing happens implicitly.

Before this pipeline existed, the same workflow was one command with a flag, two divergent
code paths, no post-transcode validation, and silence on most failure modes.

The improvement is real. The remaining gaps are also real.
