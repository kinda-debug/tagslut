# Naming Workflow (Canonical Layout)

Goal: enforce a consistent, tag-driven naming scheme without deleting anything. This workflow is copy-first so you can validate before any destructive moves.

## Canonical template (current behavior)
Matches `tools/review/promote_by_tags.py`:
- Top folder: `label` if compilation, else `albumartist` (fallback `artist`).
- Album folder: `(YYYY) Album` + optional suffix: `[Bootleg]`, `[Live]`, `[Compilation]`, `[Soundtrack]`, `[EP]`, `[Single]`.
- Filename: `NN. <Artist - >Title` with "featuring/ft." normalized to `feat.`.

## Step 1: Normalize tags (Picard script)
Apply the tag normalization you shared so year, albumartist, releasetype, and label are consistent.

```
$if(%compilation%,
  $if2(%label%,Various Artists),
  $if2(%albumartist%,%artist%)
)/
($left(%date%,4)) %album%$if($inmulti(%releasetype%,bootleg), [Bootleg],
$if($inmulti(%releasetype%,live), [Live],
$if($inmulti(%releasetype%,compilation), [Compilation],
$if($inmulti(%releasetype%,soundtrack), [Soundtrack],
$if($eq(%_primaryreleasetype%,EP), [EP],
$if($eq(%_primaryreleasetype%,Single), [Single], )
)))))/

$num(%tracknumber%,2). 
$if(%compilation%,%artist% - ,)
$replace($replace($replace(%title%, featuring , feat. ), ft. , feat. ), feat. feat., feat.)

$noop(LIBRARY - CANONICAL ENFORCEMENT)

/* =========================
   CORE IDENTITY
   ========================= */

$set(artist,%artist%)
$set(album,%album%)
$set(albumartist,%albumartist%)
$set(title,%title%)

/* =========================
   STRUCTURE
   ========================= */

$set(tracknumber,%tracknumber%)
$set(totaltracks,%totaltracks%)
$set(discnumber,%discnumber%)
$set(totaldiscs,%totaldiscs%)

$unset(track)
$unset(tracktotal)
$unset(disc)
$unset(disctotal)

/* =========================
   DATES (YEAR-ONLY)
   ========================= */

$if($ne(%date%,),$set(date,$left(%date%,4)))
$if($ne(%originaldate%,),$set(originaldate,$left(%originaldate%,4)))

$unset(year)
$unset(trackyear)
$unset(datefull)
$unset(originalyear)
$unset(originalreleaseyear)

/* =========================
   MUSICAL SEMANTICS
   ========================= */

$set(genre,%genre%)
$set(style,%style%)

/* =========================
   RELEASE IDENTITY
   ========================= */

$set(label,%label%)
$set(catalognumber,%catalognumber%)
$set(barcode,%barcode%)
$set(isrc,%isrc%)

/* =========================
   LANGUAGE & LYRICS (KEEP)
   ========================= */

$set(language,%language%)
$set(lyrics,%lyrics%)

/* =========================
   SERVICE IDENTIFIERS (KEEP IF PRESENT)
   ========================= */

/* MusicBrainz */
$set(musicbrainz_releasegroupid,%musicbrainz_releasegroupid%)
$set(musicbrainz_albumid,%musicbrainz_albumid%)
$set(musicbrainz_trackid,%musicbrainz_trackid%)

/* Apple / iTunes */
$set(itunesalbumid,%itunesalbumid%)
$set(itunestrackid,%itunestrackid%)
$set(itunesadvisory,%itunesadvisory%)

/* Qobuz */
$set(qobuz_album_id,%qobuz_album_id%)
$set(qobuz_track_id,%qobuz_track_id%)

/* Tidal */
$set(tidal_album_id,%tidal_album_id%)
$set(tidal_track_id,%tidal_track_id%)

/* =========================
   REMOVE PERFORMANCE / SESSION CREDITS
   ========================= */

$unset(performer)
$unset(performer:*)
$unset(musician)
$unset(musician:*)
$unset(instrument)
$unset(instrument:*)

$unset(mixer)
$unset(engineer)
$unset(producer)
$unset(arranger)
$unset(conductor)

/* =========================
   REMOVE SORT & UI HELPERS
   ========================= */

$unset(artists)
$unset(artistsort)
$unset(albumartistsort)
$unset(composersort)

/* =========================
   REMOVE RELEASE BUREAUCRACY
   ========================= */

$unset(media)
$unset(releasetype)
$unset(releasestatus)
$unset(releasecountry)
$unset(script)
$unset(organization)
$unset(copyright)
$unset(description)
$unset(asin)

/* =========================
   REMOVE ACOUSTID & ANALYSIS
   ========================= */

$unset(musicbrainz_artistid)
$unset(musicbrainz_releaseartistid)
$unset(musicbrainz_recordingid)
$unset(musicbrainz_workid)
$unset(acoustid_id)
$unset(acoustid_fingerprint)
$unset(bpm)
$unset(key)

/* =========================
   REMOVE TOOL FINGERPRINTS
   ========================= */

$unset(encoder)
$unset(encoded_by)
$unset(encoder_settings)
$unset(tagging_application)
$unset(tagging_date)

/* =========================
   REMOVE REPLAYGAIN
   ========================= */

$unset(replaygain_album_gain)
$unset(replaygain_album_peak)
$unset(replaygain_track_gain)
$unset(replaygain_track_peak)

/* =========================
   REMOVE PICARD INTERNALS
   ========================= */

$unset(_*)
```

## Step 2: Build canonical layout (copy-only)
Dry-run first:
```
KEEP_DIR="/Volumes/COMMUNE/M/_staging__2026-01-14/2026-01-10_keep"
python3 /Users/georgeskhawam/Projects/dedupe/tools/review/promote_by_tags.py \
  --source-root "$KEEP_DIR" \
  --dest-root /Volumes/COMMUNE/M/Library \
  --dest-root-secondary /Volumes/xtralegroom \
  --spill-min-free-gb 60 \
  --mode copy \
  --no-resume \
  --skip-existing-root /Volumes/COMMUNE/M/Library \
  --progress-only \
  --progress-every-seconds 1 \
  --log-file /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/promote_by_tags_commune.log
```

If the dry-run shows work remaining, rerun with `--execute`.

## Step 3: Validate
- Review `promote_by_tags_commune.log` for errors and filename truncations.
- Spot-check a few albums for correct folder/track naming.

## Step 4: Optional move/cleanup
Only after a test period:
- Keep the archived staging and quarantine for rollback.
- If you want to swap, move the old Library aside and replace with the canonical copy.

## Guardrails
- The script skips AppleDouble `._*` files.
- Long filenames are truncated safely (max 240 chars).
- `--skip-existing-root` prevents re-copying files already placed.
- Use `--dest-root-secondary` and `--spill-min-free-gb` to avoid ENOSPC during large runs.
