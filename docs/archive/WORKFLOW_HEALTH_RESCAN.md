# Health Rescan Workflow (Trusted First, DJ Next)

This workflow rescans files in DB order of trust priority without moving anything.

Priority order:
1. `accepted`
2. `staging`
3. `suspect` DJ-like first (`is_dj_material=1` or DJ/electronic genre hints)
4. remaining `suspect`
5. `archive`
6. `quarantine`/other

Health rule:
- Only tracks with `flac_ok=1` and `integrity_state='valid'` are included in output playlist.

Electronic-only rule:
- Add `--electronic-only` to exclude non-electronic tracks from both scan queue and playlist output.

Metadata hoarding:
- Add `--hoard-metadata` to hoard embedded tags from healthy files into `files.metadata_json`.

## Execute

### Option A: Current relink DB
```bash
scripts/workflow_health_rescan.py \
  --db /Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --root /Volumes/MUSIC \
  --workers 8 \
  --electronic-only \
  --hoard-metadata \
  --playlist-out /Volumes/MUSIC/LIBRARY/HEALTHY_PRIORITY_WORKFLOW.m3u
```

### Option B: Larger accepted snapshot DB
```bash
scripts/workflow_health_rescan.py \
  --db /Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-08/music.db \
  --root /Volumes/MUSIC \
  --workers 8 \
  --electronic-only \
  --hoard-metadata \
  --playlist-out /Volumes/MUSIC/LIBRARY/HEALTHY_PRIORITY_WORKFLOW.m3u
```

## Optional

Dry run (no DB writes):
```bash
scripts/workflow_health_rescan.py --db /path/to/music.db --dry-run --limit 500
```

Skip playlist generation:
```bash
scripts/workflow_health_rescan.py --db /path/to/music.db --no-playlist
```

## Outputs

- JSONL per-track scan log: `artifacts/logs/health_rescan_*.jsonl`
- Summary JSON: `artifacts/logs/health_rescan_*_summary.json`
- Playlist (health-pass only): `/Volumes/MUSIC/LIBRARY/HEALTHY_PRIORITY_WORKFLOW.m3u`
