# Decommission Archive — 2026-02-15

Files moved here are no longer actively used by the tagslut project.
They are preserved for reference only. Do not depend on them.

## Origin Map

| New location | Old location | Reason |
|---|---|---|
| `mp3tag_sources/` | `legacy/mp3tag_sources/` | Third-party MP3Tag web source scripts; not part of tagslut pipeline |
| `legacy-scripts/` | `legacy/scripts/` | Superseded utility scripts (env_exports, filter_plan, roon_playlist_builder, etc.) |
| `legacy-tools/` | `legacy/tools/` | Old tooling (analysis, batch_process, decide, integrity, review); replaced by `tools/` and `tagslut/` |
| `legacy-match/` | `legacy/match/` | Old standalone matching code with its own uv.lock |
| `postman-chat/` | `legacy/postman/chat/` | Chat/conversation logs — not code |
| `promote_by_tags_versions/` | `tools/archive/promote_by_tags_versions/` | 13 timestamped snapshots of one script; git history serves this purpose |
| `beatport-pdfs/` | `docs/archive/inactive-assets-2026-02-09/beatport{1,2}.pdf` | Binary PDF blobs; unnecessary git bloat |

## Files deleted (not archived)

These were removed from git and filesystem in PASS 1 (same commit series):

| File | Reason |
|---|---|
| `legacy/mp3tag_sources/Apple Music Web Source 4/localhost.key` | Private key — should never be in git |
| `legacy/mp3tag_sources/Apple Music Web Source 4/localhost.pem` | Certificate — should never be in git |
| `legacy/mp3tag_sources/localhost/localhost.key` | Private key (duplicate) |
| `legacy/mp3tag_sources/localhost/localhost.pem` | Certificate (duplicate) |
| `legacy/mp3tag_sources/Apple Music Web Source 4/mp3tag_proxy.py.bak.*` | Backup file |
| `legacy/scripts/partner_token_collector.py.save` | Editor save file |
| `legacy/scripts/sh.sh` | Scratch/junk file |
| `output/precheck/*.md` (10 files) | Generated reports — now gitignored |
| `output/repo_audit/*.md` (8 files) | Generated reports — now gitignored |
| `output/repo_audit_v2/*.md` (6 files) | Generated reports — now gitignored |
