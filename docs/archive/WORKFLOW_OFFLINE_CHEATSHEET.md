# Offline Workflow Cheat Sheet (FLAC → MP3 → Lexicon → Rekordbox)

This is the exact, minimal workflow you can run while offline. Items that require internet are clearly marked.

Paths used
- FLAC master: `/Volumes/MUSIC/LIBRARY`
- Staging downloads: `<USER_HOME>/Music/tiddl`
- DJ MP3 library (USB): `/Volumes/DJSSD/DJ_LIBRARY_MP3`
- Tagslut DB: `<TAGSLLUT_REPO>_db/EPOCH_2026-02-10_RELINK/music.db`
- Tagslut repo: `<TAGSLLUT_REPO>`

## A) ONLINE STEPS (do these before going offline)

### Quick interactive pipeline (recommended)
If you want a single command that prompts for the root folder and runs the full pipeline:
```bash
cd <TAGSLLUT_REPO>
export PYTHONPATH=.
tools/review/process_root.py
```

Notes:
- It **auto‑sets trust** (pre/post = 3) and will not prompt.
- It runs integrity with `--execute` so `flac_ok` is written.
- It runs hoarding enrichment, genre normalization, tag writes, art embedding, and promote/replace.

1) Download from Tidal (online)
```bash
TIDDL_BIN=<USER_HOME>/.local/pipx/venvs/tiddl/bin/tiddl \
<TAGSLLUT_REPO>/tools/tiddl download \
  --path <USER_HOME>/Music/tiddl \
  --scan-path <USER_HOME>/Music/tiddl \
  url https://tidal.com/album/XXXX/u
```

2) Register into DB (can be offline, but usually run immediately after download)
```bash
PYTHONPATH=<TAGSLLUT_REPO> \
python3 -m tagslut index register <USER_HOME>/Music/tiddl \
  --source tidal \
  --db <TAGSLLUT_REPO>_db/EPOCH_2026-02-10_RELINK/music.db \
  --dj-only --no-prompt --execute
```

3) Enrich metadata from providers (online)
```bash
PYTHONPATH=<TAGSLLUT_REPO> \
python3 -m tagslut index enrich \
  --db <TAGSLLUT_REPO>_db/EPOCH_2026-02-10_RELINK/music.db \
  --hoarding \
  --providers beatport,deezer,apple_music,itunes \
  --path '<USER_HOME>/Music/tiddl/%' \
  --zones staging \
  --execute
```

## B) OFFLINE STEPS (safe without internet)

4) Integrity check (writes `flac_ok`)
```bash
PYTHONPATH=<TAGSLLUT_REPO> \
python3 tools/review/check_integrity_update_db.py <USER_HOME>/Music/tiddl \
  --db <TAGSLLUT_REPO>_db/EPOCH_2026-02-10_RELINK/music.db \
  --execute
```

5) Normalize genres (DB backfill)
```bash
PYTHONPATH=<TAGSLLUT_REPO> \
python3 tools/review/normalize_genres.py <USER_HOME>/Music/tiddl \
  --db <TAGSLLUT_REPO>_db/EPOCH_2026-02-10_RELINK/music.db \
  --rules tools/rules/genre_normalization.json \
  --execute
```

6) Write normalized genre tags into FLAC files
```bash
PYTHONPATH=<TAGSLLUT_REPO> \
python3 tools/review/tag_normalized_genres.py <USER_HOME>/Music/tiddl \
  --rules tools/rules/genre_normalization.json \
  --execute
```

7) Promote FLAC to master library (replace+merge)
```bash
PYTHONPATH=<TAGSLLUT_REPO> \
python3 tools/review/promote_replace_merge.py <USER_HOME>/Music/tiddl \
  --dest /Volumes/MUSIC/LIBRARY \
  --db <TAGSLLUT_REPO>_db/EPOCH_2026-02-10_RELINK/music.db \
  --execute
```

8) Transcode **new tracks only** (from `MDL_NEW_TRACKS.m3u`) to DJSSD
```bash
python3 - <<'PY'
import os, subprocess
from pathlib import Path

SRC_ROOT = Path('/Volumes/MUSIC/LIBRARY')
DST_ROOT = Path('/Volumes/DJSSD/DJ_LIBRARY_MP3')
M3U = Path('/Volumes/MUSIC/LIBRARY/MDL_NEW_TRACKS.m3u')

lines = [l.strip() for l in M3U.read_text(encoding='utf-8', errors='replace').splitlines()]
paths = []
seen = set()
for l in lines:
    if not l or l.startswith('#'):
        continue
    p = Path(l)
    if p in seen:
        continue
    seen.add(p)
    paths.append(p)

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
    res = subprocess.run(cmd)
    if res.returncode != 0:
        if tmp.exists():
            tmp.unlink()
        continue
    os.replace(tmp, out)
PY
```

9) Update MP3 playlists (mirror the kept M3U names)
Use this pattern when you’re ready to mirror the FLAC playlists on DJSSD:
```bash
# Example: mirror DJ_SET_POOL_4TO12.m3u to DJSSD paths
python3 - <<'PY'
from pathlib import Path

src_m3u = Path('/Volumes/MUSIC/LIBRARY/DJ_SET_POOL_4TO12.m3u')
dst_m3u = Path('/Volumes/DJSSD/DJ_SET_POOL_4TO12.m3u')

src_root = '/Volumes/MUSIC/LIBRARY/'
dst_root = '/Volumes/DJSSD/DJ_LIBRARY_MP3/'

lines = [l.strip() for l in src_m3u.read_text(encoding='utf-8', errors='replace').splitlines()]
paths = [l for l in lines if l and not l.startswith('#')]

mapped = [p.replace(src_root, dst_root).rsplit('.',1)[0] + '.mp3' for p in paths]
dst_m3u.write_text('\n'.join(mapped) + ('\n' if mapped else ''), encoding='utf-8')
PY
```

## C) LEXICON + REKORDBOX (offline)

10) Lexicon import
- Import folder: `/Volumes/DJSSD/DJ_LIBRARY_MP3`

11) Rekordbox import + analysis
- Import MP3 library root
- Analyze BPM/beatgrid/phrase
- Disable **Preferences → Advanced → Write tags to file**

12) Export to USB
- Rekordbox Export Mode → export to `/Volumes/DJSSD`

---

## Notes
- **Genre/BPM/Key** are written into the DB during enrichment; tags are only written into files by steps 5–6.
- Transcode step preserves artwork and uses ID3v2.3 (best Rekordbox compatibility).
- If you go fully offline, just skip Step A3 (enrich) until you’re back online.
