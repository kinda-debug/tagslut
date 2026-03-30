# DJ Pipeline Cleanup: Replacing “Just Add `--dj`” With an Explicit Contract

**tagslut open streams, post 0010 — 2026-03-30**

## Intro

For too long, the DJ workflow in tagslut was a vibe: run `tools/get-intake --dj`, and a Rekordbox-ready library would *sometimes* appear.

When it didn’t, it didn’t fail loudly. It failed like an operator nightmare: missing MP3s, a “successful” run with nothing new admitted, and a Rekordbox import that quietly skipped tracks.

This post is about replacing implied “DJ mode” side effects with explicit contracts: a master library, an MP3 library, a DJ admission layer, and a deterministic Rekordbox XML projection.

## What Was Broken

The failure modes weren’t exotic. They were the normal day-to-day path.

First: `--dj` was a flag attached to wrapper scripts, not a contract. The wrappers mixed concerns (intake, transcode, playlists, “DJ output”) and their behavior depended on internal branches you couldn’t see as an operator. A “precheck hit” (already in inventory) could change what the wrapper did without changing your command line.

Concretely: you could run the same command twice and get meaningfully different “DJ results” depending on whether the second run hit precheck.

```bash
tools/get-intake --dj "<provider-url>"
tools/get-intake --dj "<provider-url>"  # precheck hit changes the runtime path
```

Second: “MP3 exists” was treated as “MP3 is usable.” An ffmpeg run can return success and still produce a broken file (truncated writes, unreadable container, near-zero duration). If you register that as good, you’ve turned a transcode hiccup into a downstream Rekordbox failure you only discover at import time.

Third: “DJ library” was used to mean three different things:

- The canonical master recordings (FLACs).
- A pile of MP3s on disk (some built, some copied, some stale).
- The curated subset you actually intend to DJ with.

When those collapse into one mental model, you don’t know what you’re validating or exporting. You just know something “didn’t show up.”

## The New Model

The replacement is a 4-stage pipeline with explicit state at each stage. You can re-run stages safely, and downstream stages have preconditions.

1) Master FLAC library

Stage 1 is identity + masters. It’s not “DJ mode.” It’s the canonical intake layer.

```bash
poetry run tagslut intake <provider-url>
```

2) MP3 library

Stage 2 is “the MP3 library exists as a database-backed inventory,” whether you build it from masters or reconcile an existing MP3 folder.

Build MP3 derivatives:

```bash
poetry run tagslut mp3 build \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --mp3-root "$DJ_LIBRARY" \
  --execute
```

Reconcile pre-existing MP3s (retroactive admission starts here):

```bash
poetry run tagslut mp3 reconcile \
  --db "$TAGSLUT_DB" \
  --mp3-root "$DJ_LIBRARY" \
  --execute
```

This stage is intentionally explicit about uncertainty: matching is strongest when ISRC is present in tags; it has to fall back when it isn’t. Every decision is logged (via `reconcile_log`) so you can audit what got linked and why.

3) DJ admission layer

Stage 3 is the line between “we have MP3s” and “this is the curated DJ library.”

Bulk admit verified MP3 assets:

```bash
poetry run tagslut dj backfill --db "$TAGSLUT_DB" --execute
```

Then validate:

```bash
poetry run tagslut dj validate --db "$TAGSLUT_DB"
```

Admission is stored as `dj_admission` rows; it’s not a folder side effect. TrackIDs used for Rekordbox are persisted in `dj_track_id_map` so they don’t rotate between exports.

4) Rekordbox XML projection

Stage 4 is an interoperability contract: deterministic XML, stable TrackIDs, and explicit manifests.

Full emit:

```bash
poetry run tagslut dj xml emit \
  --db "$TAGSLUT_DB" \
  --out rekordbox.xml
```

Patch (requires a prior export and verifies the prior on-disk file hash):

```bash
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --out rekordbox_next.xml
```

`dj xml emit` enforces a validation gate: you must have a recorded passing `dj validate` for the current DJ state hash (unless you explicitly bypass with `--skip-validation`). Exports are recorded in `dj_export_state` with a SHA-256 manifest hash, and the emitter treats “same scope, different bytes” as a determinism violation.

## Why This Is Better Operationally

The big difference is that the system now tells you what it did.

If Stage 2 didn’t produce MP3 assets, you can see that in `mp3_asset`. If Stage 3 didn’t admit tracks, you can see it in `dj_admission`. If Stage 4 refuses to run, it says why: no passing validation record for the current state, or blocking issues like missing files, duplicate paths, or missing title/artist metadata.

Stage 2 also stops treating “ffmpeg returned 0” as success: MP3 build validates the output file before registering it.

Deterministic XML and stable TrackIDs are the operator painkiller. Rekordbox cue points are keyed to TrackID. If TrackIDs churn, your library *looks* like it updated, but your work (cues, comments, grids) evaporates. With `dj_track_id_map`, TrackIDs are assigned once and treated as immutable.

Retroactive admission stops being a weird corner case. Most real libraries predate the database. Stage 2 reconciliation makes that explicit: it registers what’s already on disk, logs the match quality, and only then do you decide what to admit.

End-to-end, the workflow is now boring—in the good way:

```bash
poetry run tagslut intake <provider-url>
poetry run tagslut mp3 reconcile --db "$TAGSLUT_DB" --mp3-root "$DJ_LIBRARY" --execute
poetry run tagslut dj backfill --db "$TAGSLUT_DB" --execute
poetry run tagslut dj validate --db "$TAGSLUT_DB"
poetry run tagslut dj xml emit --db "$TAGSLUT_DB" --out rekordbox.xml
```

Each command has a clear output state you can audit and a clear place it fits in the pipeline.

## Remaining Risks

The pipeline is explicit, but it’s not magically complete.

The legacy wrappers still exist. `tools/get --dj` and `tools/get-intake --dj` are deprecated, but they’re still a temptation, and they still carry historic behavior you shouldn’t treat as the curated-library contract.

The validation gate is intentionally narrow right now. `dj validate` checks consistency (files exist, admitted MP3 assets are `status='verified'`, no duplicate MP3 paths across admitted tracks, and required title/artist metadata is present). It does not enforce “DJ quality” metadata (energy, danceability, key coverage) as required. If you want those fields, you still need to treat enrichment/backfill as an operator step, not something the pipeline guarantees.

Reconciliation is only as trustworthy as the tags. ISRC matching is solid when present; title/artist fallback matching can produce false positives when your MP3 pool is messy. The logging exists because this remains a risk.

And Rekordbox is still mostly one-way. We can emit and patch XML deterministically and protect TrackIDs, but we are not importing playlist edits or cue points back into the database. The contract is “projection,” not “round-trip sync.”
