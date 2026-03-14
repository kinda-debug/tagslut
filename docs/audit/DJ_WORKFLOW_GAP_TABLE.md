# DJ Workflow Gap Table

| Area | Current implementation evidence | Actual behavior | Why it fails | Classification | Required target |
|---|---|---|---|---|---|
| DJ build source | `tools/get-intake` uses `PROMOTED_FLACS_FILE` | DJ build depends on same-run promoted FLAC list | Not repeatable from canonical masters | Design flaw | `mp3 build` from canonical identity/master asset |
| Precheck-hit DJ path | `tools/get-intake` -> `link_precheck_inventory_to_dj`; `tagslut/exec/precheck_inventory_dj.py` | Alternate linking/tag-match/transcode flow | Same command changes semantics by inventory state | Misleading command contract | explicit `mp3 reconcile` + `dj admit` |
| MP3 state modeling | `files.dj_pool_path` in schema/migrations | One path field stands in for derivative library | No normalized derivative asset model | Broken data contract | `mp3_asset` table |
| DJ state modeling | `files.dj_flag`, `files.rekordbox_id`, `files.dj_set_role`, `gig_sets`, `gig_set_tracks`, CLI export logic | DJ meaning spread across table columns and utilities | No single admission/export truth | Broken data contract | `dj_admission`, playlist, export-state tables |
| Enrichment lifecycle | `tools/get-intake` skips background enrich when `DJ_MODE == 0` condition fails | DJ mode suppresses normal enrich/art | Metadata timing diverges by flag | Missing safeguard | enrichment independent of DJ export mode |
| Existing MP3 backfill | partial in `precheck_inventory_dj.py` | opportunistic path reuse or tag matching | Not a clean retroactive admission contract | Missing command + data model | `mp3 reconcile`, `dj backfill` |
| Rekordbox identity | `files.rekordbox_id` | TrackID stored on master file row | Wrong level for external interoperability ID | Broken XML contract | dedicated TrackID map in DJ layer |
| Playlist projection | utilities under DJ/Rekordbox modules | not proven as canonical projection | Unclear rebuild/patch semantics | Broken XML contract | DB playlist tables projected to XML |
| XML rebuild safety | `prep-rekordbox` utility shape | utility output, not formal projection contract | No guaranteed deterministic emit/patch | Broken XML contract | `dj xml emit` + `dj xml patch` with manifest |
| Operator interface | `tools/get --dj` | hidden branching and side effects | misleading and unreliable | Misleading command contract | separate explicit commands |
