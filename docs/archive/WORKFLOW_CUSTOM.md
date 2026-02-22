# Custom Workflow (Full Commands + Variables)

This is your end-to-end operating runbook for intake, metadata, health checks, promotion, and playlist export.

## 0) Variables

Set these once per shell session.

```bash
# Core paths
export REPO_ROOT="/path/to/your/tagslut"
export TAGSLUT_DB="/path/to/your/tagslut_db/EPOCH_PLACEHOLDER/music.db"
export LIBRARY_ROOT="/Volumes/MUSIC/LIBRARY"
export STAGING_ROOT="$HOME/Music/mdl"

# Output/log roots
export OUT_DIR="$REPO_ROOT/output"
export ARTIFACTS_DIR="$REPO_ROOT/artifacts"

# Optional provider/auth config
export TAGSLUT_ARTIFACTS="$ARTIFACTS_DIR"
export TAGSLUT_ZONES="$REPO_ROOT/config/zones.yaml"

# Policy choices
export PROVIDERS="beatport,tidal"
export NO_QOBUZ="1"
```

## 1) Environment Check

```bash
cd "$REPO_ROOT"
poetry --version
poetry run python --version
```

## 2) Pre-Download DB Check (Skip What You Already Have)

### 2.1 Single URL

```bash
python tools/review/pre_download_check.py \
  --input <(printf '%s\n' "https://tidal.com/album/447061568/u") \
  --db "$TAGSLUT_DB" \
  --out-dir "$OUT_DIR/precheck"
```

### 2.2 Links file

```bash
python tools/review/pre_download_check.py \
  --input ~/links.txt \
  --db "$TAGSLUT_DB" \
  --out-dir "$OUT_DIR/precheck"
```

### 2.3 Automatic keep-only download

```bash
tools/get-auto --links-file ~/links.txt
```

## 3) Downloaders (Source-Aware)

### 3.1 Unified router

```bash
tools/get "https://www.beatport.com/release/.../..."
tools/get "https://tidal.com/browse/album/..."
tools/get "https://www.deezer.com/en/track/..."
```

### 3.2 Direct wrappers

```bash
# Beatport
tools/get-sync "https://www.beatport.com/release/.../..."

# Tidal
tools/tiddl "https://tidal.com/browse/album/..."

# Deezer (FLAC by default, auto-register source=deezer)
tools/deemix "https://www.deezer.com/en/track/..."
```

## 4) Register New Audio Into DB

```bash
poetry run tagslut index register \
  "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" \
  --source staging \
  --execute
```

If source-specific folder:

```bash
poetry run tagslut index register "$STAGING_ROOT/deezer" --db "$TAGSLUT_DB" --source deezer --execute
poetry run tagslut index register "$STAGING_ROOT/tiddl" --db "$TAGSLUT_DB" --source tidal --execute
poetry run tagslut index register "$STAGING_ROOT/beatport" --db "$TAGSLUT_DB" --source beatport --execute
```

## 5) Enrich Metadata (Beatport + Tidal)

```bash
poetry run tagslut index enrich \
  --db "$TAGSLUT_DB" \
  --providers "$PROVIDERS" \
  --path "$STAGING_ROOT/%" \
  --retry-no-match \
  --execute
```

Notes:
- Keep Qobuz out by not including it in `--providers`.
- Use `--force` only when you intentionally want full re-enrichment.

## 6) Duration Health + Verification

### 6.1 Measure and classify

```bash
poetry run tagslut index duration-check \
  "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" \
  --execute \
  --dj-only
```

### 6.2 Verify status buckets

```bash
poetry run tagslut verify duration \
  --db "$TAGSLUT_DB" \
  --dj-only \
  --status ok,warn,fail,unknown
```

## 7) Promote to Library (Move Workflow)

### 7.1 Dry run

```bash
poetry run tagslut execute promote-tags \
  "$STAGING_ROOT" \
  --dest "$LIBRARY_ROOT"
```

### 7.2 Execute

```bash
poetry run tagslut execute promote-tags \
  "$STAGING_ROOT" \
  --dest "$LIBRARY_ROOT" \
  --execute
```

## 8) Roon M3U Export

```bash
poetry run tagslut report m3u "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --source library \
  --m3u-dir "$LIBRARY_ROOT" \
  --merge
```

Duration status buckets:

```bash
poetry run tagslut verify duration --db "$TAGSLUT_DB" --status warn,fail,unknown
poetry run tagslut report duration --db "$TAGSLUT_DB"
```

## 9) Rekordbox MP3 320 (from playlist)

```bash
export SRC_M3U="$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES.m3u"
export MP3_OUT="$HOME/Music/Rekordbox_MP3_320"

python scripts/convert_m3u_to_mp3_320.py \
  --input-m3u "$SRC_M3U" \
  --output-root "$MP3_OUT" \
  --dedupe \
  --embed-cover
```

## 10) Dropbox Intake Cleanup (Optional)

```bash
export DROPBOX_SYNC_ROOT="/Volumes/bad/dbx/Dropbox"

# Scan/verify fully downloaded FLACs
python scripts/scan_dropbox_audio_health.py --root "$DROPBOX_SYNC_ROOT"

# Promote valid files
poetry run tagslut execute promote-tags \
  --db "$TAGSLUT_DB" \
  --source "$DROPBOX_SYNC_ROOT/Music Hi-Res" \
  --dest "$LIBRARY_ROOT" \
  --execute
```

## 11) Daily Operator Sequence

```bash
# 1) precheck links
# 2) download keep-only
# 3) register
# 4) enrich beatport+tidal
# 5) duration-check
# 6) promote
# 7) export m3u buckets
```

## 12) Quick Troubleshooting

```bash
# Check auth
poetry run tagslut auth status

# Show command groups
poetry run tagslut --help

# Check DB file exists
ls -lh "$TAGSLUT_DB"

# Check latest precheck output
ls -lt "$OUT_DIR/precheck" | head
```

## 13) What This Workflow Enforces

- No Qobuz in active enrichment.
- Beatport + Tidal priority for metadata references.
- Duration-based DJ safety gates (`ok/warn/fail/unknown`).
- Roon playlists exported directly to library root.
- Source-aware registration for provenance and recovery.

## 14) Unknown Reduction (Head-On, No Qobuz)

Use this when `duration_status=unknown` is too high.

```bash
# 1) Local bootstrap of refs (no provider tokens)
python scripts/bootstrap_duration_refs_local.py \
  --db "$TAGSLUT_DB" \
  --execute

# 2) Recompute durations for library
poetry run tagslut index duration-check \
  "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --execute \
  --dj-only

# 3) Optional provider pass (Beatport + Tidal only)
poetry run tagslut index enrich \
  --db "$TAGSLUT_DB" \
  --providers beatport,tidal \
  --path "$LIBRARY_ROOT/%" \
  --recovery \
  --retry-no-match \
  --execute

# 4) Verify status counts
poetry run tagslut verify duration \
  --db "$TAGSLUT_DB" \
  --dj-only \
  --status ok,warn,fail,unknown
```

## 15) False Fail Reassessment (Extended/Remix Mismatch)

Use this for "audio is fine but marked fail" cases.

```bash
python scripts/reassess_duration_variant_mismatch.py \
  --db "$TAGSLUT_DB" \
  --execute
```

Then refresh playlists:

```bash
poetry run tagslut report m3u "$LIBRARY_ROOT" \
  --db "$TAGSLUT_DB" \
  --source library \
  --m3u-dir "$LIBRARY_ROOT" \
  --merge
```

## 16) Playlist Audit Against DB (XLSX)

```bash
# Example playlist audit script
python scripts/audit_playlist_xlsx.py \
  --xlsx "$HOME/Desktop/DJ_NEW.xlsx" \
  --db "$TAGSLUT_DB" \
  --library-root "$LIBRARY_ROOT"
```

Expected outputs:
- status report CSV/XLSX
- `*_ok.m3u`, `*_warn.m3u`, `*_fail.m3u`, `*_unknown.m3u`

## 17) Rekordbox Conversion (Whole Playlist, Deduped, 320 CBR)

```bash
export SRC_M3U="$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES.m3u"
export OUT_MP3="$HOME/Music/Rekordbox_MP3_320"

python scripts/convert_m3u_to_mp3_320.py \
  --input-m3u "$SRC_M3U" \
  --output-root "$OUT_MP3" \
  --dedupe \
  --bitrate 320 \
  --cbr
```

Cover embed pass (if source contains art):

```bash
python scripts/embed_artwork_from_sources.py \
  --source-m3u "$SRC_M3U" \
  --target-m3u "$LIBRARY_ROOT/BEATPORT_TIDAL_MATCHES_FULL_MP3_320.m3u"
```

## 18) Relink After Picard Renames (Lightweight New DB Flow)

```bash
export RELINK_DB="/path/to/your/tagslut_db/EPOCH_2026-02-10_RELINK/music.db"

python scripts/bootstrap_relink_db.py \
  --from-db "/path/to/your/tagslut_db/EPOCH_2026-02-08/music.db" \
  --to-db "$RELINK_DB"

poetry run tagslut index register \
  "$LIBRARY_ROOT" \
  --db "$RELINK_DB" \
  --source relink \
  --execute
```

## 19) Dropbox Promotion + Cloud Deletion Safety

```bash
export DBX_LOCAL="/Volumes/bad/dbx/Dropbox"
export DBX_TOKEN_FILE="$HOME/dbtoken.txt"

# 1) Verify local files are fully downloaded / decodable
python scripts/scan_dropbox_audio_health.py --root "$DBX_LOCAL"

# 2) Promote valid FLACs
poetry run tagslut execute promote-tags \
  "$DBX_LOCAL/Music Hi-Res" \
  --dest "$LIBRARY_ROOT" \
  --execute

# 3) Delete in cloud only with valid write-scope token
# Required Dropbox scopes: files.content.write + files.metadata.read
python scripts/delete_dropbox_cloud_paths.py \
  --token-file "$DBX_TOKEN_FILE" \
  --paths-file "$REPO_ROOT/dropbox_processed_cloud_paths.txt"
```

If cloud delete returns `missing_scope` or `expired_access_token`, regenerate token and retry.

## 20) Daily “No-Pollution” Policy

- Always precheck links against DB before download.
- Never promote without duration-check.
- Keep providers restricted to `beatport,tidal` unless explicitly needed.
- Treat `warn/fail` as review queues, not auto-delete signals.
- Rebuild Roon playlists from DB statuses after each major run.
