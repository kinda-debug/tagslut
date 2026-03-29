# DJ Pipeline Cleanup: How We Replaced "Just Add --dj" With an Explicit Contract

**tagslut open streams, post 0010 — 2026-03-23**

---

## Intro

For a while, the DJ library workflow in tagslut had a kind of mythological quality: add `--dj` to
the download command and a Rekordbox-ready library would materialize. Sometimes it did. Often it
didn't. When it didn't, nobody got an error — just a missing MP3, an empty admission table, and a
Rekordbox import that silently skipped half your tracks.

This post is about why that broke, what the replacement looks like, and which parts are still being
hardened.

---

## What Was Broken

### The `--dj` flag had two runtime paths and you couldn't predict which one ran

`tools/get-intake --dj` worked differently depending on whether the tracks were newly promoted or
already in inventory. If the download was fresh, the MP3 build ran. If the tracks hit precheck
(already owned), the code fell into a fallback branch that generated an M3U playlist instead of
building MP3s. No error. No warning. Just a DJ library that did not grow.

This wasn't obscure — it was the primary entry point.

### FFmpeg failures were silent

The MP3 transcode stage didn't check ffmpeg exit codes, didn't validate the output file size,
didn't parse duration, and didn't verify ID3 tags. A failed transcode would register the (missing
or truncated) file as `status='verified'` in the database and move on. The first time the operator
discovered the failure was when Rekordbox failed to load the track at import time.

### Enrichment was optional when it shouldn't be

Intake gets you 60–80% of the metadata you need. The rest — energy, danceability, Camelot key —
came from an optional Lexicon backfill step that was not part of the canonical pipeline and left no
DB record when skipped. DJ XML could emit cleanly with those fields missing. Rekordbox would
import the track with blank energy and key fields and you'd only notice at the gig.

### Validation didn't block anything

`dj validate` ran checks against the admission table and produced a report. But it didn't update
the admission row state, and nothing downstream required it to have run. You could go from backfill
to XML emit without validation ever executing. The `--skip-validation` flag existed specifically
to bypass the gate that wasn't actually gating anything.

### There were three entry points with different guarantees

`tools/get --dj`, `tools/get-intake --dj`, and the canonical 4-stage CLI all existed
simultaneously. They produced different outputs, had different error behaviors, and none of them
clearly stated which was authoritative. Deprecation warnings were added but no removal timeline was
set.

---

## The New Model

The canonical workflow is now an explicit 4-stage pipeline. Each stage has a defined DB output.
Stages do not proceed if the prior stage's state is absent or invalid.

```
Stage 1: Intake masters
  poetry run tagslut intake
  Output: track_identity rows + asset_file (role='master')

Stage 2: Build or reconcile MP3 derivatives
  poetry run tagslut mp3 build ...    # FLAC → MP3 with output validation
  poetry run tagslut mp3 reconcile ... # register existing MP3s against identities
  Output: mp3_asset rows with readiness state

Stage 3: Admit and validate DJ library state
  poetry run tagslut dj backfill ...   # admit all verified MP3s
  poetry run tagslut dj validate ...   # check files, metadata, enrichment
  Output: dj_admission rows with readiness='ready'

Stage 4: Emit or patch Rekordbox XML
  poetry run tagslut dj xml emit ...   # deterministic export, stable TrackIDs
  poetry run tagslut dj xml patch ...  # incremental update, preserves cue points
  Output: Rekordbox XML + dj_export_state manifest
```

### Three distinct libraries, three distinct DB layers

The old mental model collapsed master FLAC files, MP3 copies, and the DJ curated subset into a
fuzzy notion of "the DJ library." The replacement makes three layers explicit:

**Master FLAC library** — canonical recordings. Files in `$MASTER_LIBRARY`. Read-only after intake.
Linked to `track_identity` via `asset_file (role='master')`.

**MP3 library** — derived playback copies. Files in `$DJ_LIBRARY`. Each MP3 registered in
`mp3_asset` with a readiness state (`unchecked` → `playable` → `orphaned`/`corrupted`). An MP3 that
failed transcode validation never becomes `playable`. Only `playable` MP3s can advance.

**DJ admission layer** — the curated subset. Each admitted track is a row in `dj_admission` linking
an identity to a specific MP3 asset. Readiness tracks validation state (`unvalidated` → `ready` →
`stale`). Only `ready` admissions can appear in a Rekordbox XML export.

### Why retroactive admission matters

Most DJ libraries weren't built from scratch with tagslut. They pre-exist. `mp3 reconcile` handles
this: it scans an existing MP3 directory, extracts ISRCs from ID3 tags, and links files to known
track identities. High-confidence matches (ISRC) land at `readiness='playable'`. Low-confidence
matches (title+artist fallback) land at `readiness='suspect'` and require operator review before
admission.

This is the only safe way to retrofit a pre-existing MP3 folder into the curated library. The old
path — running `--dj` against a URL that was already in inventory — silently skipped this whole
process.

### Why Rekordbox XML is treated as a contract, not an afterthought

Rekordbox TrackIDs are the stable identifiers that cue points are keyed to. If you regenerate
TrackIDs on every export, every cue point you've placed in Rekordbox disappears.

The system now maintains a `dj_track_id_map` table that persists TrackID assignments across
emit/patch cycles. Once a track gets a TrackID, it keeps it. The `xml patch` command preserves all
prior TrackIDs, adds new ones for newly admitted tracks, and removes tracks that are no longer
admitted. Cue points survive.

The manifest hash system catches tampering: if the XML file was edited outside tagslut between
`emit` and `patch`, the hash won't match and the patch will refuse to run.

---

## Why This Is Better Operationally

### Concrete example: adding 10 new tracks to an existing DJ library

**Old path:**
```bash
tools/get --dj "https://beatport.com/release/12345"
# Hope the tracks are new (not precheck hits)
# Hope ffmpeg didn't fail silently
# Hope enrichment is complete
# Import into Rekordbox; discover 3 tracks have broken paths or missing key data
```

**New path:**
```bash
poetry run tagslut intake "https://beatport.com/release/12345"
poetry run tagslut mp3 build --db "$TAGSLUT_DB" --master-root "$MASTER_LIBRARY" \
  --dj-root "$DJ_LIBRARY" --execute
# ↑ validates ffmpeg output: file size, duration, ID3 tags checked before registering as 'playable'

poetry run tagslut dj backfill --db "$TAGSLUT_DB"
poetry run tagslut dj validate --db "$TAGSLUT_DB"
# ↑ if validation fails, it tells you which tracks and why; xml emit is gated on passing state

poetry run tagslut dj xml patch --db "$TAGSLUT_DB" --out rekordbox_v2.xml
# ↑ stable TrackIDs; cue points on existing tracks are preserved
```

If anything goes wrong, it goes wrong at the stage where it actually went wrong — not silently
three stages later when Rekordbox refuses to load the file.

### State is auditable

At any point you can query the DB to see the readiness state of every admitted track, which
enrichment stages have run, and when the last XML was emitted. You don't need to run the full
pipeline to check if the library is exportable.

---

## Remaining Risks

### FFmpeg validation is better but not complete

`mp3 build` now validates output file size and duration before marking a transcode as `playable`.
What it doesn't yet do: check ID3 tag completeness, detect codec errors in valid-sized files, or
verify that the encoded audio is not corrupt. These are documented as gaps in the test suite.

### Title+artist matching in reconcile still has false positive risk

When `mp3 reconcile` falls back to title+artist matching (because the MP3 has no ISRC in its ID3
tags), remixes and originals with the same credited artist and title can match incorrectly. The
reconcile log marks these as `suspect` and they require operator review. But there's no automated
disambiguation, and no test coverage for this path.

### Lexicon backfill is still optional and still untracked

The Lexicon enrichment step (which adds energy, danceability, and Camelot key from a Lexicon DJ
export) is not part of the canonical 4-stage pipeline. The `enrichment_state` table design exists
(documented in `DATA_MODEL_RECOMMENDATION.md`) but the implementation hasn't landed. Until it does,
`dj validate` does not check for missing energy/danceability fields. You can still emit an XML
without those fields if you skip backfill.

### XML import is not yet implemented

The `dj xml import` command — which would round-trip playlist edits from Rekordbox back to the DB —
is designed but not built. Right now the XML export is one-directional: tagslut → Rekordbox. If you
reorganize playlists in Rekordbox, those changes don't sync back. You have to maintain playlist
state manually in both places.

### Legacy wrappers are deprecated but not removed

`tools/get --dj` and `tools/get-intake --dj` print deprecation warnings and are not the recommended
path. They haven't been deleted yet. No removal date has been set. An operator who doesn't read the
deprecation warning will still use them and get the old, unreliable behavior.

---

## Summary

The core change is replacing vague "DJ mode" behavior with an explicit, stateful pipeline. Each
stage has a defined input contract, a defined DB output, and a readiness state that downstream
stages can check.

The plumbing is mostly in place. The gaps are in validation depth (enrichment completeness, full
ffmpeg output integrity), reconcile edge cases (false positive matching), and the two features that
don't exist yet: XML import and enrichment state tracking in the DB.

What's reliable now: the four-stage pipeline, MP3 build output validation, backfill idempotence,
stable TrackID assignment, and the manifest hash tamper detection on XML patch. Start there.
