# feat: Lexicon-aware merge-write for --dj tag output

## Do not recreate existing files. Do not modify schema.py without a migration.

## Background

Lexicon DJ (https://lexicondj.com) manages the operator's DJ pool at
/Volumes/MUSIC/DJ_POOL. It enriches MP3 tags with its own values and
maintains a SQLite DB at /Users/georgeskhawam/Music/main.db.

tagslut and Lexicon must not clobber each other's fields. The rule is:

  tagslut owns:   ISRC (TSRC), label (TPUB), canonical date (TDRC),
                  title (TIT2), artist (TPE1), album (TALB),
                  track number (TRCK), disc number (TPOS)

  Lexicon owns:   BPM corrections (TBPM, TXXX:bpm),
                  key (TKEY, TXXX:INITIALKEY, TXXX:initialkey),
                  energy/danceability/happiness (TXXX:ENERGY, COMM mood string),
                  synced lyrics (TXXX:USLT),
                  AcoustID fingerprint (TXXX:acoustid_fingerprint),
                  Serato autogain (TXXX:serato_autogain),
                  MusicBrainz IDs written by Lexicon

## Lexicon detection

A file has been touched by Lexicon if ANY of these are present:
  TXXX:LEXICON_RATING
  TXXX:serato_autogain
  TXXX:ENERGY
  COMM frame matching r"\d+ Energy, \d+ Dance, \d+ Happy, \d+ Pop"
  TXXX:acoustid_fingerprint

## Lexicon DB integration

The Lexicon DB schema (Track table) exposes:
  id, title, artist, bpm, key, energy, danceability, happiness,
  label, genre, fingerprint, importSource, location (absolute path)

Join key: Track.location == absolute file path.

tagslut should optionally read this DB before writing tags, to avoid
writing stale values over Lexicon corrections. The DB path is configured
via LEXICON_DB env var, defaulting to
/Users/georgeskhawam/Music/main.db if it exists and is readable.

## What to produce

1. `tagslut/dj/lexicon.py`

   LexiconDB class:
     __init__(db_path: Path | None)
       Opens DB read-only if path exists. No-ops silently if path is None
       or file is not readable (Lexicon may not be installed on all machines).
     is_lexicon_touched(file_path: Path) -> bool
       Read ID3 tags from file; return True if any detection marker is present.
     get_track(file_path: Path) -> dict | None
       Query Track table by location; return row as dict or None.

   LEXICON_OWNED_FRAMES: frozenset of ID3 frame names tagslut must not write
   when is_lexicon_touched returns True.

2. `tagslut/dj/tag_writer.py`

   write_dj_tags(file_path: Path, tags: dict, lexicon: LexiconDB) -> None
     - If lexicon.is_lexicon_touched(file_path): write only frames NOT in
       LEXICON_OWNED_FRAMES. Log which frames were skipped.
     - Otherwise: write all frames.
     - Always write TXXX:TAGSLUT_LAST_WRITE = ISO 8601 UTC timestamp.
     - Never raise on a single frame write failure — log and continue.

3. `tagslut/dj/drift.py`

   detect_drift(file_path: Path, lexicon: LexiconDB) -> list[str]
     - Read TXXX:TAGSLUT_LAST_WRITE from file.
     - Read current TBPM and TKEY from file.
     - Query lexicon DB for same path.
     - If DB bpm or key differs from file tags AND TAGSLUT_LAST_WRITE is
       present (meaning tagslut wrote those values): return list of field
       names that drifted. Empty list = no drift.
     Used by `tagslut admin status` to surface files where Lexicon has
     updated values since tagslut last wrote.

4. Wire LexiconDB into the --dj output path in the existing intake/dj flow.
   Pass LEXICON_DB from env. LexiconDB must be instantiated once per run,
   not per file.

5. `tests/dj/test_lexicon_detection.py`
   Tests for: detection markers present/absent, frame skip logic,
   TAGSLUT_LAST_WRITE written, drift detection.

6. `tests/dj/test_tag_writer_merge.py`
   Tests for: merge-write skips Lexicon-owned frames when marker present,
   writes all frames when no marker, no exception on frame failure.

Commit after each file. Run targeted tests after all files are complete:
  poetry run pytest tests/dj/ -v
