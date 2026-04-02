<!-- Status: Partially active. Top-level workflow sections updated 2026-04-02.
     V3 migration, manual phase, and maintenance sections below are legacy reference
     kept for archaeology. Current daily workflow is in OPERATOR_QUICK_START.md. -->

# WORKFLOWS.md

Operator reference for tagslut. Start here.

**Surface policy**
Use canonical entry points: `ts-get`, `ts-enrich`, `ts-auth`. Legacy `tagslut intake/index/decide/execute/verify/report/auth` flows and `tools/review/*` scripts below are reference only.

> **Environment bootstrap** (update once, use everywhere):
> ```bash
> export REPO_ROOT="/path/to/tagslut"
> source .venv/bin/activate
> set -a
> source .env
> set +a
> export V3_DB="${V3_DB:-$TAGSLUT_DB}"
> export MASTER_LIBRARY="${MASTER_LIBRARY:-${LIBRARY_ROOT:-$VOLUME_LIBRARY}}"
> export STAGING_ROOT="${STAGING_ROOT:-$VOLUME_STAGING}"
> export ROOT_BP="${ROOT_BP:-$STAGING_ROOT/bpdl}"
> export ROOT_TD="${ROOT_TD:-$STAGING_ROOT/tidal}"
> export PLAYLIST_ROOT="${PLAYLIST_ROOT:-$MASTER_LIBRARY/playlists}"
> export DJ_LIBRARY="${DJ_LIBRARY:-${DJ_MP3_ROOT:-}}"
> export DJ_PLAYLIST_ROOT="${DJ_PLAYLIST_ROOT:-$DJ_LIBRARY}"
> export VOLUME_WORK="${VOLUME_WORK:-/Volumes/MUSIC/_work}"
> export FIX_ROOT="${FIX_ROOT:-$VOLUME_WORK/fix}"
> export QUARANTINE_ROOT="${QUARANTINE_ROOT:-${VOLUME_QUARANTINE:-$VOLUME_WORK/quarantine}}"
> export DISCARD_ROOT="${DISCARD_ROOT:-$VOLUME_WORK/discard}"
> ```

---

## Current Daily Workflow

```bash
# Download (TIDAL, Qobuz, or Beatport URL)
ts-get <url>
ts-get <url> --dj        # + DJ pool M3U

# Metadata enrichment
ts-enrich                # runs beatport → tidal → qobuz → reccobeats

# Token refresh
ts-auth                  # refresh all providers
ts-auth tidal            # one provider only
ts-auth beatport         # one provider only
ts-auth qobuz            # one provider only
```

See `docs/OPERATOR_QUICK_START.md` for full startup sequence.

---

## Command Surface (active wrappers)
- `ts-get <url> [--dj]` — download via tiddl/streamrip/beatportdl; `--dj` writes per-batch + global `dj_pool.m3u`.
- `ts-enrich [--provider ...]` — hoarding pass; uses `$TAGSLUT_DB`.
- `ts-auth [tidal|beatport|qobuz|all]` — refresh tokens; validates Qobuz session; syncs beatportdl creds.
- `tools/auth [tidal|beatport|qobuz|all]` — implementation behind ts-auth.
- `tools/enrich` — implementation behind ts-enrich.
- Legacy wrappers (`tools/get`, `poetry run tagslut intake ...`, etc.) are archived; see `docs/archive/` if needed.

---

## Legacy reference (pre-April 2026 pipeline)

The sections below describe the old `tagslut intake url` / `tools/get` pipeline
and 8-step manual workflow. They are kept for archaeology only.

## V3 Migration Operations

Use these commands when validating or repairing the v3 identity layer. Do not mix them into ordinary intake work.

### Baseline snapshot before migration work

```bash
cp "$V3_DB" "${V3_DB}.pre_phase1_$(date +%Y%m%d_%H%M%S).bak"
sqlite3 "$V3_DB" "PRAGMA foreign_keys = ON; PRAGMA foreign_key_check;"
sqlite3 "$V3_DB" "PRAGMA integrity_check;"
```

### Identity backfill

```bash
# Dry run
python scripts/backfill_v3_identity_links.py --db "$V3_DB"

# Execute
python scripts/backfill_v3_identity_links.py --db "$V3_DB" --execute

# Resume from a known file id
python scripts/backfill_v3_identity_links.py \
  --db "$V3_DB" \
  --execute \
  --resume-from-file-id <file_id>
```

Artifacts written by the backfill command:
- `artifacts/backfill_v3_summary_<stamp>.json`
- `artifacts/backfill_v3_checkpoint_<stamp>_<file_id>.json`
- `artifacts/backfill_v3_abort_<stamp>.json`

### Migration and parity verification

```bash
sqlite3 "$V3_DB" "PRAGMA foreign_keys = ON; PRAGMA foreign_key_check;"
sqlite3 "$V3_DB" "PRAGMA integrity_check;"
sqlite3 "$V3_DB" "PRAGMA optimize;"

python scripts/validate_v3_dual_write_parity.py --db "$V3_DB" --strict
python scripts/db/verify_v3_migration.py --db "$V3_DB"
```

### Merged identity inspection

```bash
python scripts/db/compute_identity_status_v3.py \
  --db "$V3_DB" \
  --out artifacts/identity_status.csv

sqlite3 "$V3_DB" "
SELECT id, identity_key, merged_into_id
FROM track_identity
WHERE merged_into_id IS NOT NULL
ORDER BY merged_into_id, id;
"
```

### Rollback to a pre-phase backup

```bash
cp "${V3_DB}.pre_phase1_<stamp>.bak" "$V3_DB"
sqlite3 "$V3_DB" "PRAGMA integrity_check;"
```

## Manual Phase Workflow (Advanced)

This is the explicit phase-by-phase loop. Use it when you intentionally want manual control rather than `tagslut intake <URL>` (alias: `tagslut intake url <URL>`) or `tools/get`.

```
1. precheck    → decide what to download
2. download    → fetch only what's missing
3. register    → add to DB
4. enrich      → pull metadata from providers
5. integrity   → verify FLAC files are valid
6. duration    → measure + classify DJ safety
7. promote     → move to master library
8. playlists   → rebuild M3U exports
```

### 1 · Precheck (skip what you already have)

```bash
# Single URL
python tools/review/pre_download_check.py \
  --input <(printf '%s\n' "https://tidal.com/album/447061568/u") \
  --db "$TAGSLUT_DB" \
  --out-dir output/precheck

# Links file
python tools/review/pre_download_check.py \
  --input ~/links.txt \
  --db "$TAGSLUT_DB" \
  --out-dir output/precheck

# One-command: precheck + auto-download keep-only
tools/get-auto --links-file ~/links.txt
```

Outputs: `output/precheck/precheck_decisions_*.csv`, `precheck_keep_track_urls_*.txt`

Use `--quiet` for script-level automation, or run through `tagslut intake <URL>` (alias: `tagslut intake url <URL>`) or `tools/get` for the normal concise operator flow.

### 2 · Download

```bash
# Primary wrapper (recommended)
tools/get "https://www.beatport.com/release/.../..."
tools/get "https://tidal.com/browse/album/..."
tools/get "https://www.deezer.com/en/track/..."

# Advanced/direct wrappers
tools/get-intake --no-download --batch-root "$STAGING_ROOT/bpdl" --execute
tools/tiddl    "https://tidal.com/browse/album/..."    # downloader-only Tidal
tools/deemix   "https://www.deezer.com/en/track/..."   # Deezer (FLAC, auto-registers)

# Quarantine retention cleanup
python tools/review/quarantine_gc.py \
  --root "$QUARANTINE_ROOT" \
  --days "$QUARANTINE_RETENTION_DAYS"
```

| Source   | Wrapper          | `--source` flag | Auto-register | Default path              |
|----------|------------------|-----------------|---------------|---------------------------|
| Beatport | `get`            | `bpdl`          | No            | config-defined / staging  |
| Tidal    | `get`, `tiddl`   | `tidal`         | No            | `~/Music/mdl/tidal`       |
| Deezer   | `get`, `deemix`  | `deezer`        | **Yes**       | `~/Music/mdl/deezer`      |
| Qobuz    | —                | —               | —             | Not in active workflows   |

### 3 · Register

```bash
# Whole staging root
poetry run tagslut index register "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" --source staging --execute

# Source-specific
poetry run tagslut index register "$ROOT_TD" --db "$TAGSLUT_DB" --source tidal --execute
poetry run tagslut index register "$ROOT_BP" --db "$TAGSLUT_DB" --source beatport --execute
poetry run tagslut index register "$STAGING_ROOT/deezer"  --db "$TAGSLUT_DB" --source deezer   --execute
```

### 4 · Enrich metadata

```bash
poetry run tagslut index enrich \
  --db "$TAGSLUT_DB" \
  --providers beatport,tidal \
  --path "$STAGING_ROOT/%" \
  --retry-no-match \
  --execute
```

- **Never** include Qobuz in `--providers`.
- Use `--force` only for intentional full re-enrichment.

### 5 · Integrity check

```bash
python tools/review/check_integrity_update_db.py "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" \
  --execute
```

Writes `flac_ok=1` on pass. Corrupt files are blocked from promotion.

### 6 · Duration check

```bash
# Measure + classify
poetry run tagslut index duration-check "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" --execute --dj-only

# Review status buckets
poetry run tagslut verify duration \
  --db "$TAGSLUT_DB" --dj-only --status ok,warn,fail,unknown
```

Status meanings: `ok` = safe for DJ use · `warn` = review · `fail` = do not promote · `unknown` = not yet checked

### 7 · Promote to master library

```bash
# Dry run first (always)
poetry run tagslut execute promote-tags "$STAGING_ROOT" \
  --dest "$MASTER_LIBRARY"

# Execute
poetry run tagslut execute promote-tags "$STAGING_ROOT" \
  --dest "$MASTER_LIBRARY" --execute
```

Gates: corrupt FLACs are blocked (`flac -t`). `duration_status` must be `ok` (override: `--allow-non-ok-duration`).

Alternatively, use the replace+merge script for smarter conflict handling:
```bash
python tools/review/promote_replace_merge.py "$STAGING_ROOT" \
  --dest "$MASTER_LIBRARY" --db "$TAGSLUT_DB" --execute
```

### 8 · Rebuild playlists

```bash
# Roon M3U export
poetry run tagslut report m3u "$MASTER_LIBRARY" \
  --db "$TAGSLUT_DB" --source library --m3u-dir "$PLAYLIST_ROOT" --path-mode relative --name-prefix roon- --merge

# Review warn/fail/unknown buckets
poetry run tagslut verify duration --db "$TAGSLUT_DB" --status warn,fail,unknown
poetry run tagslut report duration --db "$TAGSLUT_DB"
```

---

## One-Command Pipeline (Staged Root)

For a staged root that is already on disk, use the v3-safe `process-root` phase set:

```bash
python -m tagslut intake process-root \
  --db "$V3_DB" \
  --root "$STAGING_ROOT" \
  --library "$MASTER_LIBRARY" \
  --phases identify,enrich,art,promote,dj
```

Preview only the DJ stage:

```bash
python -m tagslut intake process-root \
  --db "$V3_DB" \
  --root "$STAGING_ROOT" \
  --phases dj \
  --dry-run
```

Current `--dry-run` scope is DJ-only. If you need scan/register/integrity behavior, run the dedicated commands from the manual workflow instead of relying on `process-root`.

### process-root phase contracts (v3-safe set)

The v3-safe phase set is:

- identify
- enrich
- art
- promote
- dj

Use this as a maintainership contract for `tagslut intake process-root` on a v3 DB.

#### identify

- Inputs: staged audio files under `--root`, v3 DB at `--db`.
- Outputs: identity-linked staged cohort (rows are associated to v3 identity where matchable).
- DB side effects: writes/updates identity linkage state used by downstream v3 views and phase decisions.
- Filesystem side effects: none on audio payload; source files remain in staged root.
- Handoff: produces the identity-backed working set consumed by enrich.

#### enrich

- Inputs: identify-phase cohort plus provider configuration (canonical provider set is Beatport and TIDAL).
- Outputs: refreshed canonical metadata used by export and DJ shaping (artist/title/genre/label/BPM/key/year when available).
- DB side effects: updates enrichment-backed identity metadata payloads and related provenance for enrichment operations.
- Filesystem side effects: no library moves; metadata fetch work may emit operational artifacts/logs only.
- Handoff: passes metadata-complete cohort to art.

#### art

- Inputs: enriched cohort from prior phases and artwork provider availability.
- Outputs: artwork enrichment state for tracks where art is resolved.
- DB side effects: updates artwork/provenance state associated with the v3 identity-backed cohort.
- Filesystem side effects: may write artwork-related operational artifacts; does not promote or relocate library audio.
- Handoff: passes identity+metadata+art-ready cohort to promote.

#### promote

- Inputs: staged cohort at `--root`, destination library root via `--library`, and prior phase eligibility state.
- Outputs: accepted library placement under `MASTER_LIBRARY` for promotable files.
- DB side effects: records promoted file state/paths used by downstream DJ/export workflows.
- Filesystem side effects: moves/copies promotable files from staged root into library layout (per current promote policy).
- Handoff: produces promoted master-library cohort consumed by dj.

#### dj

- Inputs: promoted cohort and v3 identity-backed DJ metadata context.
- Outputs: DJ-prep eligibility state and DJ-facing artifacts needed for downstream DJ pool/export workflows.
- DB side effects: writes DJ-phase provenance/state updates used by `dj` command-group workflows.
- Filesystem side effects: no direct Rekordbox export; writes DJ-phase artifacts in configured output locations.
- Handoff: terminal phase for `process-root`; downstream operator flow continues with canonical DJ commands (`tagslut dj ...`).

## Reviewed Plan Execution

For CSV-backed move plans, use the canonical executor:

```bash
python -m tagslut execute move-plan \
  --plan plans/example.csv \
  --db "$V3_DB" \
  --dry-run
```

When executed, common sidecars such as lyric files and sibling artwork move with the audio file.

---

## DJ Pool Export (FLAC → MP3 → Rekordbox)

### Transcode new tracks to DJSSD

```bash
python3 - <<'PY'
import os, subprocess
from pathlib import Path

SRC_ROOT = Path('$MASTER_LIBRARY')
DST_ROOT = Path('$DJ_LIBRARY')
M3U      = Path('$MASTER_LIBRARY/MDL_NEW_TRACKS.m3u')

lines = [l.strip() for l in M3U.read_text(encoding='utf-8', errors='replace').splitlines()]
seen, paths = set(), []
for l in lines:
    if not l or l.startswith('#'):
        continue
    p = Path(l)
    if p not in seen:
        seen.add(p); paths.append(p)

for src in paths:
    if not src.exists():
        continue
    try:
        rel = src.relative_to(SRC_ROOT)
    except Exception:
        continue
    out = (DST_ROOT / rel).with_suffix('.mp3')
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        continue
    tmp = out.with_suffix('.tmp.mp3')
    cmd = [
        'ffmpeg','-hide_banner','-loglevel','error','-stats','-y',
        '-i', str(src),
        '-map','0:a','-map','0:v?','-map_metadata','0',
        '-c:a','libmp3lame','-b:a','320k','-minrate','320k','-maxrate','320k','-bufsize','320k',
        '-id3v2_version','3','-write_id3v1','1',
        '-c:v','copy','-disposition:v','attached_pic',
        str(tmp)
    ]
    if subprocess.run(cmd).returncode == 0:
        os.replace(tmp, out)
    elif tmp.exists():
        tmp.unlink()
PY
```

### Mirror M3U playlists to DJSSD paths

```bash
python3 - <<'PY'
from pathlib import Path

src_m3u  = Path('$MASTER_LIBRARY/DJ_SET_POOL_4TO12.m3u')
dst_m3u  = Path('$DJ_USB_ROOT/DJ_SET_POOL_4TO12.m3u')
src_root = '$MASTER_LIBRARY/'
dst_root = '$DJ_LIBRARY/'

lines = [l.strip() for l in src_m3u.read_text(encoding='utf-8', errors='replace').splitlines()]
paths = [l for l in lines if l and not l.startswith('#')]
mapped = [p.replace(src_root, dst_root).rsplit('.',1)[0] + '.mp3' for p in paths]
dst_m3u.write_text('\n'.join(mapped) + '\n', encoding='utf-8')
PY
```

### Rekordbox import

1. Lexicon: import folder `$DJ_LIBRARY`
2. Rekordbox: import MP3 library root → Analyze BPM/beatgrid/phrase
3. Disable **Preferences → Advanced → Write tags to file**
4. Export to USB: Rekordbox Export Mode → `$DJ_USB_ROOT`

---

## Metadata Workflows

### Genre normalization

```bash
# DB backfill (dry run)
python tools/review/normalize_genres.py "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" --rules tools/rules/genre_normalization.json

# DB backfill (execute)
python tools/review/normalize_genres.py "$STAGING_ROOT" \
  --db "$TAGSLUT_DB" --rules tools/rules/genre_normalization.json --execute

# Write normalized tags into FLAC files
python tools/review/tag_normalized_genres.py "$STAGING_ROOT" \
  --rules tools/rules/genre_normalization.json --execute
```

### Sync Lexicon tag edits → DB

```bash
tools/metadata sync-tags \
  --read-files --execute \
  --db "$TAGSLUT_DB" \
  --path "$MASTER_LIBRARY"
```

Writes an M3U of tracks still missing critical tags at `$MASTER_LIBRARY/missing_tags_*.m3u`.

### ISRC enrichment (OneTagger)

```bash
# Build M3U of files missing ISRC
tools/tag-build --db "$TAGSLUT_DB" --output output/onetagger_batch.m3u

# Run OneTagger
tools/tag-run --m3u output/onetagger_batch.m3u

# Sync results back to DB
poetry run tagslut index enrich --db "$TAGSLUT_DB"
```

---

## Maintenance & Repair

### Health rescan (integrity pass over full library)

```bash
scripts/workflow_health_rescan.py \
  --db "$TAGSLUT_DB" \
  --root $MUSIC_VOLUME_ROOT \
  --workers 8 \
  --electronic-only \
  --hoard-metadata \
  --playlist-out "$MASTER_LIBRARY/HEALTHY_PRIORITY_WORKFLOW.m3u"
```

Dry run: `--dry-run --limit 500` · Skip playlist: `--no-playlist`

Outputs: `artifacts/logs/health_rescan_*.jsonl`, `*_summary.json`, `HEALTHY_PRIORITY_WORKFLOW.m3u`

### Fix `duration_status=unknown` (high unknown count)

```bash
# 1) Bootstrap refs locally (no provider tokens needed)
python scripts/bootstrap_duration_refs_local.py --db "$TAGSLUT_DB" --execute

# 2) Recompute durations
poetry run tagslut index duration-check "$MASTER_LIBRARY" \
  --db "$TAGSLUT_DB" --execute --dj-only

# 3) Optional: provider pass to fill remaining unknowns
poetry run tagslut index enrich \
  --db "$TAGSLUT_DB" --providers beatport,tidal \
  --path "$MASTER_LIBRARY/%" --recovery --retry-no-match --execute

# 4) Verify
poetry run tagslut verify duration --db "$TAGSLUT_DB" --dj-only --status ok,warn,fail,unknown
```

### Fix false `duration_status=fail` (remix/extended mismatch)

```bash
python scripts/reassess_duration_variant_mismatch.py --db "$TAGSLUT_DB" --execute

# Rebuild playlists after
poetry run tagslut report m3u "$MASTER_LIBRARY" \
  --db "$TAGSLUT_DB" \
  --source library --m3u-dir "$PLAYLIST_ROOT" --path-mode relative --name-prefix roon- --merge
```

### Playlist audit against DB (XLSX input)

```bash
python scripts/audit_playlist_xlsx.py \
  --xlsx "$HOME/Desktop/DJ_NEW.xlsx" \
  --db "$TAGSLUT_DB" \
  --library-root "$MASTER_LIBRARY"
```

Outputs: status CSV/XLSX + `*_ok.m3u`, `*_warn.m3u`, `*_fail.m3u`, `*_unknown.m3u`

### Rekordbox conversion (full playlist, 320 CBR)

```bash
python scripts/convert_m3u_to_mp3_320.py \
  --input-m3u "$MASTER_LIBRARY/BEATPORT_TIDAL_MATCHES.m3u" \
  --output-root "$HOME/Music/Rekordbox_MP3_320" \
  --dedupe --bitrate 320 --cbr

# Optional: embed artwork
python scripts/embed_artwork_from_sources.py \
  --source-m3u "$MASTER_LIBRARY/BEATPORT_TIDAL_MATCHES.m3u" \
  --target-m3u "$MASTER_LIBRARY/BEATPORT_TIDAL_MATCHES_FULL_MP3_320.m3u"
```

### Dropbox intake

```bash
# 1) Verify FLAC health
python scripts/scan_dropbox_audio_health.py --root "$DROPBOX_ROOT"

# 2) Promote valid files
poetry run tagslut execute promote-tags \
  "$DROPBOX_ROOT/Music Hi-Res" \
  --dest "$MASTER_LIBRARY" --execute

# 3) Cloud delete (requires files.content.write scope)
python scripts/delete_dropbox_cloud_paths.py \
  --token-file ~/dbtoken.txt \
  --paths-file "$REPO_ROOT/dropbox_processed_cloud_paths.txt"
```

### Relink DB after Picard renames

```bash
python scripts/bootstrap_relink_db.py \
  --from-db "$V2_DB" \
  --to-db "$V3_DB"

poetry run tagslut index register "$MASTER_LIBRARY" \
  --db "$V3_DB" \
  --source relink --execute
```

---

## Quick Troubleshooting

```bash
# Auth status
poetry run tagslut auth status
poetry run tagslut auth refresh   # if expired

# DB exists?
ls -lh "$TAGSLUT_DB"

# Command reference
poetry run tagslut --help
poetry run tagslut intake --help
poetry run tagslut intake url --help

# Latest precheck output
ls -lt output/precheck | head

# Latest intake artifacts
ls -lt artifacts/intake | head
```

See `docs/TROUBLESHOOTING.md` for failure modes and fixes.

---

## Operating Policy

- **Always precheck** before download — never download blind.
- **Never promote** without a passing integrity check and `duration_status=ok`.
- **Providers**: `beatport,tidal` only. Do not add Qobuz unless explicitly required.
- **`warn`/`fail` buckets** are review queues — not auto-delete signals.
- **Rekordbox** is a terminal consumer. It does not write back to the master library.
- **Master FLAC** is immutable. The DJ MP3 pool is always derived from it, never the source of truth.
- Rebuild Roon playlists from DB statuses after every major run.
