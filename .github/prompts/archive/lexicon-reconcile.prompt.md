**NOTE BEFORE STARTING (updated 2026-03-30):**
FRESH DB current state differs from the row counts documented below (those were from the legacy DB).
Actual FRESH DB counts: ~585 track_identity, ~26,497 asset_file, ~652 mp3_asset, ~237 dj_admission.
All 7 tables (mp3_asset, dj_admission, dj_track_id_map, dj_playlist, dj_playlist_track,
dj_export_state, reconcile_log) already exist — Task 1 will verify and skip DDL creation.
Migration version is currently 14; migration 0015 (dj_validation_state_audit) exists in
schema.py but may not yet be applied to the FRESH DB — run migration runner before Task 2.
COMMIT ALL CHANGES BEFORE EXITING.

---

You are an expert Python and data-modeling engineer working in the tagslut repository.

Goal:
Reconcile the Lexicon DJ library with TAGSLUT_DB, centralize MP3 state,
import Lexicon metadata, and produce a clean canonical DJ pipeline ready
for the 4-stage workflow.

This is based on a completed, multi-session audit. All facts below are
verified from live databases and filesystem. Do not re-investigate the
schema — use what is documented here.

═══════════════════════════════════════════════════════
RATE LIMIT SAFETY — READ THIS FIRST
═══════════════════════════════════════════════════════

This is a long multi-task session. Assume you may be interrupted at any
point by a rate limit, crash, or context reset. Build for resumability:

  1. After completing each Task (1–8), write a checkpoint file:
       data/checkpoints/reconcile_YYYYMMDD_HH.json
     Format:
       {
         "session_run_id": "<uuid4>",
         "completed_tasks": [1, 2, ...],
         "task_summaries": {
           "1": {"status": "done", "notes": "..."},
           ...
         },
         "last_updated": "<ISO timestamp>"
       }

  2. At the START of this session, check if a checkpoint file exists:
       data/checkpoints/reconcile_*.json  (take the most recent)
     If found, print which tasks are already done and skip them.
     Ask before re-running a task marked "done" in the checkpoint.

  3. Every command (mp3 scan, reconcile, lexicon import, etc.) must write
     its own run log to:
       data/logs/reconcile_<task>_<run_id>.jsonl
     One JSON object per line. Include at minimum:
       {"ts": "<ISO>", "run_id": "...", "action": "...", "path": "...",
        "result": "...", "details": {...}}

  4. All DB writes go to reconcile_log table (created in Task 1) AND to
     the JSONL log. Dual-write. This means if the DB write fails, the
     JSONL is the recovery source.

  5. Use a single session_run_id (uuid4, generated once at session start)
     across all tasks. Stamp it on every reconcile_log row and every
     JSONL entry so the entire session is traceable end-to-end.

  6. Each task that modifies the DB must emit a progress summary to stdout
     at completion:
       [TASK N COMPLETE] X inserted, Y updated, Z skipped, W errors
     This is what you'll see if you check back after a rate limit.

═══════════════════════════════════════════════════════
VERIFIED PATHS
═══════════════════════════════════════════════════════

  TAGSLUT_DB:     /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db
  LEXICON_DB:     /Volumes/MUSIC/lexicondj.db
  DJUSB:          /Volumes/DJUSB/   (Rekordbox USB, mounted — ignore for now)

  MP3 scan roots:
    DJ_LIBRARY:       /Volumes/MUSIC/DJ_LIBRARY/             6,843 MP3s — canonical
    MANUAL_POOL:      /Volumes/MUSIC/DJ_POOL_MANUAL_MP3/       950 MP3s — manual imports
    ABSOLUTE_DJ_MP3:  /Volumes/MUSIC/_work/absolute_dj_mp3/  2,341 MP3s — dark zone, unregistered

  Excluded from scan (do not touch):
    /Volumes/MUSIC/_work/gig_runs/              ephemeral gig pool copy, not masters
    /Volumes/MUSIC/_work/cleanup_20260308_220000/
    /Volumes/MUSIC/_work/fix/
    /Volumes/MUSIC/_work/to_process/
    /Volumes/MUSIC/_work/quarantine/
    /Volumes/MUSIC/_work/bpdl_jimi_jules_20260220/

  FLAC zones:
    PRIMARY_FLAC:    /Volumes/MUSIC/MUSIC_LIBRARY_V2/    in TAGSLUT_DB (27,902 files)
    MASTER_LIBRARY:  /Volumes/MUSIC/MASTER_LIBRARY/      24,917 FLACs, NOT in TAGSLUT_DB

═══════════════════════════════════════════════════════
VERIFIED TAGSLUT_DB STATE  (music_v3.db)
═══════════════════════════════════════════════════════

Schema version: v3.9 (last migration: add chromaprint columns, 2026-03-12)

Tables confirmed to exist:
  files             27,902 rows  (all FLACs from MUSIC_LIBRARY_V2)
  track_identity    32,196 rows
  asset_file        51,146 rows  (7,638 with chromaprint_fingerprint)
  asset_link        rows linking asset_file ↔ track_identity
  preferred_asset   29,721 rows
  asset_analysis    bpm/key/energy analysis results
  provenance_event  18,452 rows
  dj_track_profile  304 rows     ← PRECIOUS, see rules below
  identity_status
  library_track_sources / library_tracks
  gigs / gig_sets / gig_set_tracks
  scan_sessions / scan_runs / scan_queue / scan_issues
  file_quarantine / file_path_history / file_metadata_archive
  move_plan / move_execution
  tag_hoard_*
  schema_migrations

PREVIOUS SESSION created migration 0009 which added these 6 tables.
Verify they exist before writing any DDL:
  mp3_asset, dj_admission, dj_track_id_map,
  dj_playlist, dj_playlist_track, dj_export_state

reconcile_log does NOT exist yet — must be created in Task 1.

Key columns on files (confirmed):
  path (PK), library, zone, mtime, size, checksum, sha256,
  canonical_title, canonical_artist, canonical_album, canonical_isrc,
  canonical_bpm, canonical_key, canonical_genre, canonical_label,
  canonical_mix_name, canonical_duration, canonical_year,
  spotify_id, beatport_id, tidal_id, qobuz_id, itunes_id, deezer_id,
  musicbrainz_id, traxsource_id,
  is_dj_material (INTEGER DEFAULT 0),
  dj_pool_path   2,272 rows ALL in _UNRESOLVED/missing_core_tags/ — broken, ignore,
  rekordbox_id   0 rows populated,
  dj_flag        0 rows set,
  dj_set_role, dj_subrole,
  bpm, key_camelot, energy, genre, isrc,
  quality_rank, mgmt_status, fingerprint

Key columns on track_identity (confirmed):
  id, identity_key, isrc,
  beatport_id, tidal_id, qobuz_id, spotify_id, apple_music_id,
  deezer_id, traxsource_id, itunes_id, musicbrainz_id,
  artist_norm, title_norm, album_norm,
  canonical_title, canonical_artist, canonical_album,
  canonical_genre, canonical_subgenre, canonical_label,
  canonical_catalog_number, canonical_mix_name,
  canonical_duration, canonical_year, canonical_release_date,
  canonical_bpm, canonical_key,
  enriched_at, created_at, updated_at, merged_into_id

dj_track_profile schema (confirmed):
  identity_id   INTEGER PRIMARY KEY REFERENCES track_identity(id)
  rating        INTEGER NULL CHECK(rating BETWEEN 0 AND 5)
  energy        INTEGER NULL CHECK(energy BETWEEN 0 AND 10)
  set_role      TEXT NULL CHECK(set_role IN
                  ('warmup','builder','peak','tool','closer','ambient','break','unknown'))
  dj_tags_json  TEXT NOT NULL DEFAULT ''
  notes         TEXT NULL
  last_played_at TEXT NULL
  updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP

Current content:
  303 rows with dj_tags_json like '["dance:07","happy:06","pop:07"]'
  1 row with set_role = 'peak'
  All 304: set_role NULL except the 1 peak row
  → NEVER overwrite any row where dj_tags_json IS NOT NULL

v_dj_ready_candidates (32,151 rows) — column map (positional, confirmed):
  1=identity_id, 2=identity_key, 3=canonical_artist, 4=canonical_title,
  5=canonical_bpm, 6=key_text, 7=canonical_genre, 8=canonical_duration,
  9=asset_id, 10=asset_path (FLAC), 11=identity_status, 12-17=nulls

Other confirmed views:
  v_dj_pool_candidates_active_v3       (29,305 rows)
  v_dj_pool_candidates_active_orphan_v3
  v_dj_pool_candidates_v3
  v_asset_analysis_latest_dj
  v_dj_export_metadata_v1

═══════════════════════════════════════════════════════
VERIFIED LEXICON DB STATE  (lexicondj.db)
═══════════════════════════════════════════════════════

Track table: 31,211 rows, 45 columns.

Zone breakdown (all confirmed):
  DJ_LIBRARY          active=6,842  archived=1,000  CANONICAL — import these
  DJ_POOL_MANUAL_MP3  active=950    archived=0      MANUAL IMPORTS — import these
  _work/gig_runs      active=2,800  archived=0      ONE GIG POOL (2026-03-13) — SKIP
  _work/cleanup*      active=~50    archived=0      _UNRESOLVED artifacts — SKIP
  DJ_LIBRARY_MERGED   active=0      archived=3,543  ZERO files on disk — IGNORE
  DJ_LIBRARY_MP3      active=0      archived=433    ZERO files on disk — IGNORE
  LIBRARY/            active=0      archived=14,912 DIRECTORY DOES NOT EXIST — IGNORE
  MASTER_LIBRARY      active=324    archived=0      FLAC zone — skip for this task
  DJUSB               active=0      archived=71     USB exports — IGNORE
  _work/absolute_dj_mp3 → ZERO rows in Lexicon (entirely dark — handle via scan only)

Fingerprint: only 990/31,211 tracks have one (MD5 format, low coverage).
Primary match key is path + normalized tags, NOT fingerprint.

Key Track columns:
  id, title, artist, location (file path), locationUnique,
  fingerprint (MD5), bpm (REAL), key (TEXT e.g. "Fm","Am","Dbm"),
  rating (0–5), energy, danceability, happiness, popularity,
  playCount, lastPlayed, color,
  genre, label, remixer, mix, composer, producer, lyricist, grouping,
  extra1, extra2, streamingService, streamingId,
  bitrate, sampleRate, duration (ms), sizeBytes,
  dateAdded, dateModified, archived (0/1), incoming (0/1)

Supporting tables:
  Playlist (type: 1=folder, 2=playlist, 3=smartlist) + LinkTrackPlaylist
  Tag + TagCategory (Genre/39, Mood/15, Timing/9) + LinkTagTrack
  Cuepoint       → EMPTY
  HistorySession / HistoryTrack → EMPTY
  Waveform       → keep in Lexicon, do NOT import
  AlbumartPreview → keep in Lexicon, do NOT import

Playlists to import:
  "tagged_lexicon"         3,595 tracks  playlist_type='curated'
  "lexicon_manual_pool"      950 tracks  playlist_type='curated'
  "happy"                     67 tracks  playlist_type='mood'
  "HAPPY_FROM_CSV_plus2"      59 tracks  playlist_type='mood'
  prefix "dj-This Is Kölsch-"  43 tracks playlist_type='artist_set'
  prefix "Duplicate Tracks "   51 tracks playlist_type='admin', flag is_duplicate=true
  "fucked"                     44 tracks playlist_type='admin', status='needs_review'

Playlists to SKIP (name matches any of):
  starts with: Unnamed, lexicon_missing_, velocity_dj_,
               lexicon_enrichable_, lexicon_export_,
               lexicon_newlyadded_, lexicon-since-,
               lexicon-tagged-batch_, Text Matched, roon-tidal-
  exact:       no bpm, diff, ok, e, done, yes, new, newnew, nos, g,
               cvr, cvryes, antig, k, new23, ROOT, Dump, Lexicon,
               playlist, missing_genre_lexicon_consolidated_20260226_134220,
               Lexicon_tagged_tracks
  always skip: folder nodes (type=1), empty playlists (track_count=0)

═══════════════════════════════════════════════════════
CONTEXT FILES — read before starting
═══════════════════════════════════════════════════════

  AGENT.md
  CLAUDE.md
  docs/DJ_WORKFLOW.md
  docs/OPERATIONS.md
  docs/SCRIPT_SURFACE.md
  docs/DB_V3_SCHEMA.md
  tagslut/storage/schema.py
  tagslut/storage/migrations/
  tagslut/dj/admission.py
  tagslut/exec/mp3_build.py
  tests/e2e/test_dj_pipeline.py   (13 tests from previous session — do not break)

═══════════════════════════════════════════════════════
OPERATING RULES
═══════════════════════════════════════════════════════

  1. AGENT.md is the primary rule source. CLAUDE.md governs Claude behavior.
  2. No destructive git operations.
  3. Every command that writes to DB or moves files: --dry-run default, --execute to commit.
  4. All DB writes transactional. Partial runs safe to re-run (idempotent).
  5. NEVER overwrite dj_track_profile.dj_tags_json under any circumstances.
  6. NEVER touch the row where set_role = 'peak'.
  7. NEVER delete or move a file without --execute flag.
  8. Every decision → one row in reconcile_log AND one line in JSONL log.
  9. Use a single session_run_id (uuid4) across all tasks.
  10. ATTACH DATABASE to query Lexicon and TAGSLUT_DB in same connection where possible.
  11. If ambiguous, ask before guessing.

═══════════════════════════════════════════════════════
TASK 1 — Schema migration
═══════════════════════════════════════════════════════

FIRST: verify which tables from migration 0009 already exist:

  SELECT name FROM sqlite_master
  WHERE type='table'
    AND name IN ('mp3_asset','dj_admission','dj_track_id_map',
                 'dj_playlist','dj_playlist_track','dj_export_state',
                 'reconcile_log');

Then:
  - If all 7 exist → skip Task 1, write checkpoint, proceed to Task 2.
  - If reconcile_log is the only missing one → create migration 0010
    with reconcile_log only.
  - If others are missing → create migration 0010 with only the missing tables.
  - Do NOT re-run DDL for tables that already exist.

Migration file: tagslut/storage/migrations/0010_add_reconcile_log.sql
(or 0010_add_missing_dj_tables.sql if more than reconcile_log is missing)

reconcile_log DDL:
  CREATE TABLE IF NOT EXISTS reconcile_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT NOT NULL,
    event_time       TEXT DEFAULT CURRENT_TIMESTAMP,
    source           TEXT NOT NULL,
    action           TEXT NOT NULL,
    confidence       TEXT,
    mp3_path         TEXT,
    identity_id      INTEGER,
    lexicon_track_id INTEGER,
    details_json     TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_reconcile_log_run      ON reconcile_log(run_id);
  CREATE INDEX IF NOT EXISTS idx_reconcile_log_identity ON reconcile_log(identity_id);

If mp3_asset is missing, its DDL:
  CREATE TABLE IF NOT EXISTS mp3_asset (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_id      INTEGER REFERENCES track_identity(id),
    asset_id         INTEGER REFERENCES asset_file(id),
    path             TEXT NOT NULL UNIQUE,
    content_sha256   TEXT,
    size_bytes       INTEGER,
    bitrate          INTEGER,
    sample_rate      INTEGER,
    duration_s       REAL,
    profile          TEXT NOT NULL DEFAULT 'standard',
    status           TEXT NOT NULL DEFAULT 'unverified'
                       CHECK(status IN ('unverified','verified','missing','superseded')),
    source           TEXT NOT NULL DEFAULT 'unknown',
    zone             TEXT,
    transcoded_at    TEXT,
    reconciled_at    TEXT,
    lexicon_track_id INTEGER,
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at       TEXT DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS idx_mp3_asset_identity ON mp3_asset(identity_id);
  CREATE INDEX IF NOT EXISTS idx_mp3_asset_zone     ON mp3_asset(zone);
  CREATE INDEX IF NOT EXISTS idx_mp3_asset_lexicon  ON mp3_asset(lexicon_track_id);

If dj_admission is missing:
  CREATE TABLE IF NOT EXISTS dj_admission (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_id  INTEGER UNIQUE REFERENCES track_identity(id),
    mp3_asset_id INTEGER REFERENCES mp3_asset(id),
    status       TEXT NOT NULL DEFAULT 'pending'
                   CHECK(status IN ('pending','admitted','rejected','needs_review')),
    source       TEXT NOT NULL DEFAULT 'unknown',
    notes        TEXT,
    admitted_at  TEXT,
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS idx_dj_admission_identity ON dj_admission(identity_id);

If dj_track_id_map is missing:
  CREATE TABLE IF NOT EXISTS dj_track_id_map (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    dj_admission_id    INTEGER UNIQUE REFERENCES dj_admission(id),
    rekordbox_track_id INTEGER NOT NULL UNIQUE,
    assigned_at        TEXT DEFAULT CURRENT_TIMESTAMP
  );

If dj_playlist is missing:
  CREATE TABLE IF NOT EXISTS dj_playlist (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    parent_id           INTEGER REFERENCES dj_playlist(id),
    lexicon_playlist_id INTEGER,
    sort_key            TEXT,
    playlist_type       TEXT DEFAULT 'standard',
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, parent_id)
  );

If dj_playlist_track is missing:
  CREATE TABLE IF NOT EXISTS dj_playlist_track (
    playlist_id     INTEGER NOT NULL REFERENCES dj_playlist(id),
    dj_admission_id INTEGER NOT NULL REFERENCES dj_admission(id),
    ordinal         INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, dj_admission_id)
  );

If dj_export_state is missing:
  CREATE TABLE IF NOT EXISTS dj_export_state (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT NOT NULL,
    output_path   TEXT NOT NULL,
    manifest_hash TEXT,
    scope_json    TEXT,
    emitted_at    TEXT DEFAULT CURRENT_TIMESTAMP
  );

Checkpoint: write data/checkpoints/reconcile_YYYYMMDD_HH.json with task 1 done.
Print: [TASK 1 COMPLETE] N tables verified existing, M tables created.

═══════════════════════════════════════════════════════
TASK 2 — MP3 scan
═══════════════════════════════════════════════════════

Command: tagslut mp3 scan
  --mp3-roots /Volumes/MUSIC/DJ_LIBRARY \
              /Volumes/MUSIC/DJ_POOL_MANUAL_MP3 \
              /Volumes/MUSIC/_work/absolute_dj_mp3
  --out data/mp3_scan_{YYYYMMDD}.csv
  [--include-gig-runs]   off by default

For each .mp3 collect:
  path, zone (which root), size_bytes, mtime, sha256,
  bitrate, sample_rate, duration_s,
  id3_title, id3_artist, id3_album, id3_year,
  id3_bpm, id3_key, id3_genre, id3_label, id3_remixer,
  id3_isrc, id3_comment

Output: stable CSV sorted by path.
Log each file to data/logs/reconcile_scan_<run_id>.jsonl.
Print progress every 500 files: [SCAN] N/M files processed...
Do NOT scan _work/gig_runs/ unless --include-gig-runs is passed.

Checkpoint: update checkpoint file with task 2 done, output CSV path.
Print: [TASK 2 COMPLETE] N files scanned across 3 zones. CSV: data/mp3_scan_YYYYMMDD.csv

═══════════════════════════════════════════════════════
TASK 3 — Reconcile MP3s against TAGSLUT_DB
═══════════════════════════════════════════════════════

Command: tagslut mp3 reconcile
  --db TAGSLUT_DB
  --scan-csv data/mp3_scan_{YYYYMMDD}.csv
  --out data/mp3_reconcile_{YYYYMMDD}.json
  [--dry-run | --execute]

Match each MP3 to a track_identity using priority:

  Tier 1 — Path pattern (confidence: HIGH)
    Extract artist + title from filename:
      Artist/(Year) Album/Artist – Album – NN Title.mp3
    Match vs track_identity.artist_norm + title_norm (exact normalized).
    Unique match only.

  Tier 2 — ISRC (confidence: HIGH)
    id3_isrc vs track_identity.isrc. Unique match only.

  Tier 3 — ID3 tag match (confidence: MEDIUM)
    Normalized id3_title + id3_artist vs title_norm + artist_norm.
    Unique match only.

  Tier 4 — Fuzzy (confidence: LOW)
    Token-sort ratio >= 0.92. Flag for review. Do NOT auto-admit.

  No match → stub:
    INSERT track_identity:
      source='mp3_reconcile', status='stub_pending_master',
      canonical_title=id3_title, canonical_artist=id3_artist
    INSERT mp3_asset linked to stub.
    Log action='orphan_stubbed'.

Conflicts:
  Multiple candidates → action='CONFLICT', do not link, flag for human.
  Duplicate MP3s for same identity → keep highest bitrate,
    mark lower as status='superseded'.

On match: INSERT mp3_asset:
  identity_id, path, zone, sha256, bitrate, sample_rate, duration_s,
  status='unverified', source='mp3_reconcile', reconciled_at=now,
  lexicon_track_id=NULL

Every decision → reconcile_log row + JSONL line.
Idempotent: skip paths already in mp3_asset.

Checkpoint: update with task 3 done.
Print: [TASK 3 COMPLETE] N matched (T1/T2/T3/T4/stub breakdown), M skipped, W conflicts.

═══════════════════════════════════════════════════════
TASK 4 — Import Lexicon metadata
═══════════════════════════════════════════════════════

Command: tagslut lexicon import
  --db TAGSLUT_DB
  --lexicon /Volumes/MUSIC/lexicondj.db
  [--dry-run | --execute]
  [--prefer-lexicon]

Source: Lexicon Track WHERE archived=0 AND incoming=0
        AND (location LIKE '/Volumes/MUSIC/DJ_LIBRARY/%'
          OR location LIKE '/Volumes/MUSIC/DJ_POOL_MANUAL_MP3/%')

Match Lexicon Track → TAGSLUT_DB identity (in order):
  1. mp3_asset.path = Lexicon Track.location → get identity_id
  2. Normalized artist+title vs track_identity.artist_norm+title_norm
  3. Lexicon Track.streamingId vs track_identity provider ID columns

Field mapping (write only if target IS NULL, unless --prefer-lexicon):
  Track.bpm        → track_identity.canonical_bpm
  Track.key        → track_identity.canonical_key
  Track.energy     → dj_track_profile.energy (only if row exists AND energy IS NULL)
  Track.rating     → dj_track_profile.rating (only if row exists AND rating IS NULL)
  Track.lastPlayed → dj_track_profile.last_played_at (only if NULL)
  Track.color      → dj_track_profile.notes prefix "lexicon_color:<value>"
  Track.genre      → track_identity.canonical_genre (if NULL)
  Track.label      → track_identity.canonical_label (if NULL)
  Track.remixer    → track_identity.canonical_mix_name (if NULL)
  Track.id         → mp3_asset.lexicon_track_id (always set if matched)
  Track.extra1/2   → append to dj_track_profile.notes as
                     "lexicon_extra1:<v>" / "lexicon_extra2:<v>"

HARD RULES — non-negotiable:
  NEVER modify dj_track_profile.dj_tags_json
  NEVER touch the row where set_role = 'peak'
  NEVER overwrite non-null fields unless --prefer-lexicon
  NEVER create a new dj_track_profile row (only update existing ones)

Every field write → reconcile_log action='lexicon_field_import',
  details_json={field, old_value, new_value} + JSONL.

Checkpoint: update with task 4 done.
Print: [TASK 4 COMPLETE] N tracks matched, M fields written, W skipped (non-null), E errors.

═══════════════════════════════════════════════════════
TASK 5 — Import Lexicon playlists
═══════════════════════════════════════════════════════

Command: tagslut lexicon import-playlists
  --db TAGSLUT_DB
  --lexicon /Volumes/MUSIC/lexicondj.db
  [--dry-run | --execute]

Import only the playlists listed in the LEXICON DB STATE section above.
Skip rules are also listed there — enforce them strictly.

For each imported playlist:
  1. INSERT OR IGNORE INTO dj_playlist (name, lexicon_playlist_id, playlist_type)
  2. For each LinkTrackPlaylist (ordered by position):
     a. Find dj_admission row via identity resolved in Task 4.
        If none: INSERT dj_admission(status='pending', source='lexicon_playlist_import').
     b. INSERT OR IGNORE INTO dj_playlist_track
          (playlist_id, dj_admission_id, ordinal=position)
  3. "fucked" playlist: set dj_admission.status='needs_review' for all its tracks.

Log every playlist + track link to reconcile_log + JSONL.
Idempotent.

Checkpoint: update with task 5 done.
Print: [TASK 5 COMPLETE] N playlists imported, M tracks linked, W skipped.

═══════════════════════════════════════════════════════
TASK 6 — MASTER_LIBRARY FLAC ingest
═══════════════════════════════════════════════════════

Command: tagslut master scan
  --root /Volumes/MUSIC/MASTER_LIBRARY
  --db TAGSLUT_DB
  [--dry-run | --execute]

24,917 FLACs not yet in TAGSLUT_DB.

For each .flac:
  1. Check asset_file.path exists → skip if so (idempotent).
  2. INSERT asset_file(path, zone='MASTER_LIBRARY', library='master',
                       size_bytes, mtime, sha256, bitrate, sample_rate,
                       duration_s, first_seen_at=now)
  3. Match identity:
     - isrc from tags vs track_identity.isrc
     - Normalized title+artist vs title_norm+artist_norm
  4. If match: INSERT asset_link(asset_id, identity_id,
                                 confidence, link_source='master_scan')
  5. If no match: INSERT track_identity stub
                  (canonical_title, canonical_artist, status='stub_pending_enrichment')
                  then INSERT asset_link
  6. Log to reconcile_log + JSONL.

Print progress every 1,000 files: [MASTER SCAN] N/24917...
Do NOT run enrichment.

Checkpoint: update with task 6 done.
Print: [TASK 6 COMPLETE] N assets inserted, M matched to existing identity,
       W stubs created, X skipped (already existed).

═══════════════════════════════════════════════════════
TASK 7 — Missing masters report
═══════════════════════════════════════════════════════

Command: tagslut mp3 missing-masters
  --db TAGSLUT_DB
  --out data/missing_masters_{YYYYMMDD}.md

Section A — Orphaned MP3s
  (mp3_asset rows where identity is stub_pending_master OR identity_id IS NULL)
  Columns: priority, zone, title, artist, path, bitrate
  Priority:
    HIGH   — appears in dj_playlist_track
              OR Lexicon energy > 5 for matched lexicon_track_id
    MEDIUM — has canonical_bpm AND canonical_key
    LOW    — everything else

Section B — FLACs ready, no MP3
  (v_dj_ready_candidates with no matching mp3_asset.identity_id)
  Columns: identity_key, canonical_artist, canonical_title, asset_path
  Suggested action: tagslut mp3 build --identity-id <id>

Format: GitHub-flavoured markdown checkboxes, sorted by priority DESC.

Checkpoint: update with task 7 done.
Print: [TASK 7 COMPLETE] Section A: N orphaned MP3s (X HIGH, Y MEDIUM, Z LOW).
       Section B: M FLACs ready with no MP3. Report: data/missing_masters_YYYYMMDD.md

═══════════════════════════════════════════════════════
TASK 8 — Tests
═══════════════════════════════════════════════════════

Add tests (do NOT break the 13 existing tests in tests/e2e/test_dj_pipeline.py):

  tests/exec/test_mp3_reconcile.py
    - Tier 1/2/3/orphan/conflict reconcile paths with fixture data
    - Duplicate MP3 → superseded correctly
    - Dry-run → zero DB writes
    - reconcile_log has 1 row per decision
    - JSONL log written alongside reconcile_log

  tests/dj/test_lexicon_import.py
    - Null-field skip (default behavior)
    - --prefer-lexicon overwrites non-null
    - dj_tags_json NEVER modified under any condition
    - set_role='peak' row survives full import unchanged
    - extra1/2 appended to notes, not to dj_tags_json
    - Idempotent: double-run produces same result

  tests/dj/test_lexicon_playlists.py
    - Skip-list honored precisely
    - "fucked" tracks get status='needs_review'
    - "Duplicate Tracks" tracks get is_duplicate flag
    - Ordinal preserved from Lexicon position
    - Idempotent

  tests/storage/test_reconcile_migration.py
    - Migration idempotent (run twice, no error)
    - All 7 tables exist after migration
    - reconcile_log indexes exist

  tests/exec/test_master_scan.py
    - Idempotent on re-run
    - Stub created for unmatched FLAC
    - asset_link created for matched FLAC

═══════════════════════════════════════════════════════
FINAL STEPS
═══════════════════════════════════════════════════════

After all 8 tasks:
  1. Append full entry to CHANGELOG.md.
  2. Save this prompt verbatim to .github/prompts/lexicon-reconcile.prompt.md.
  3. Write final checkpoint with all tasks marked done and a session summary:
       data/checkpoints/reconcile_YYYYMMDD_HH_FINAL.json
  4. Print overall session summary:
       [SESSION COMPLETE]
       Tasks done: 1 2 3 4 5 6 7 8
       run_id: <uuid>
       MP3s scanned: N
       MP3s reconciled: N (T1/T2/T3/T4/stub/conflict breakdown)
       Lexicon tracks matched: N
       Fields written: N
       Playlists imported: N
       MASTER_LIBRARY assets registered: N
       JSONL log: data/logs/reconcile_<run_id>.jsonl
       Checkpoint: data/checkpoints/reconcile_YYYYMMDD_HH_FINAL.json

