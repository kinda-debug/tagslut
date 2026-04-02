<!-- Status: Active audit note. Captured from local runtime on 2026-03-15. -->

# `tools/get --dj` Runtime Trace — 2026-03-15

This note captures two real `tools/get --dj --verbose` runs against the local repo and compares them to the documented branching behavior in [DJ_WORKFLOW_TRACE.md](/Users/georgeskhawam/Projects/tagslut/docs/audit/DJ_WORKFLOW_TRACE.md).

## Environment

- `TAGSLUT_DB`: `/Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-03-04/music_v3.db`
- `NEW_TRACK`: `https://www.beatport.com/track/done-up/23647340`
- `EXISTING_TRACK`: `https://www.beatport.com/track/the-takeover/20280380`

Captured artifacts:

- [new_track.stdout](/Users/georgeskhawam/Projects/tagslut/artifacts/audit/get_dj_runs/new_track.stdout)
- [new_track.stderr](/Users/georgeskhawam/Projects/tagslut/artifacts/audit/get_dj_runs/new_track.stderr)
- [existing_track.stdout](/Users/georgeskhawam/Projects/tagslut/artifacts/audit/get_dj_runs/existing_track.stdout)
- [existing_track.stderr](/Users/georgeskhawam/Projects/tagslut/artifacts/audit/get_dj_runs/existing_track.stderr)

Both runs exited `0`.

## Stage execution order

| Scenario | Observed stage order | Code path called |
|---|---|---|
| New track (`done-up`) | `Pre-download check` → `Download from Beatport` → `Quick duplicate check` → `Trust scan + integrity registration` → `Local identify + tag prep` → `Cross-root fingerprint audit` → `Plan promote/fix/quarantine/discard` → `Apply plans` → `Generate Roon M3U` → `Build DJ MP3 copies` | Promotion-fed branch in [tools/get-intake](/Users/georgeskhawam/Projects/tagslut/tools/get-intake#L2272) using `PROMOTED_FLACS_FILE`; gated before `build_pool_v3` because zero promoted identities were resolved |
| Existing track (`the-takeover`) | `Pre-download check` → `Download from Beatport` (skipped) → `Link existing inventory to DJ` → exit | Precheck-hit fallback via `link_precheck_inventory_to_dj()` in [tools/get-intake](/Users/georgeskhawam/Projects/tagslut/tools/get-intake#L225) calling [precheck_inventory_dj.py](/Users/georgeskhawam/Projects/tagslut/tagslut/exec/precheck_inventory_dj.py#L347) |

## MP3 output difference

| Scenario | Precheck result | Promotion result | DJ MP3 result |
|---|---|---|---|
| New track | `keep=1 skip=0` | `promoted=1` | DJ phase started, but `Resolved 0 promoted identity ids` and `No promoted identities resolved for DJ export; skipping.` No DJ MP3 created |
| Existing track | `keep=0 skip=1` | No download, no promotion | Fallback linker ran, but `existing_mp3_rows=0`, `transcoded_rows=0`, `resolved_rows=0`, `unresolved_rows=1`. No DJ MP3 created |

## Captured command output

### `tools/get $NEW_TRACK --dj --verbose`

**stdout excerpt**

```text
[1/10] Pre-download check
...
  keep=1 skip=0
Precheck summary: keep=1 skip=0 total=1

[2/10] Download from Beatport
Selected for download: 1 track(s)
...
Download result:
  batch after:  1 audio files under /Volumes/MUSIC/mdl/bpdl

[8/10] Apply plans
...
EXECUTE: planned=1 moved=1 skipped_missing=0 skipped_exists=0 failed=0
Promoted file list: /Users/georgeskhawam/Projects/tagslut/artifacts/compare/promoted_flacs_20260315_133351.txt (1 files)

[10/10] Build DJ MP3 copies
→ poetry run python - /Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-03-04/music_v3.db /Users/georgeskhawam/Projects/tagslut/artifacts/compare/promoted_flacs_20260315_133351.txt /Users/georgeskhawam/Projects/tagslut/artifacts/compare/dj_identity_ids_20260315_133353.txt
Resolved 0 promoted identity ids
No promoted identities resolved for DJ export; skipping.
```

**stderr excerpt**

```text
[LEGACY] WARNING: tools/get --dj is deprecated.
  The --dj flag has two divergent code paths and may produce non-deterministic results.
  For a curated DJ library, use the explicit 4-stage pipeline:
    tagslut mp3 reconcile  --db $TAGSLUT_DB --mp3-root $DJ_LIBRARY --execute
    tagslut dj backfill    --db $TAGSLUT_DB
    tagslut dj validate    --db $TAGSLUT_DB
    tagslut dj xml emit    --db $TAGSLUT_DB --out rekordbox.xml
```

### `tools/get $EXISTING_TRACK --dj --verbose`

**stdout excerpt**

```text
[1/10] Pre-download check
...
  keep=0 skip=1
Precheck summary: keep=0 skip=1 total=1

[2/10] Download from Beatport
Selected for download: 0 track(s)
All candidates already have same-or-better inventory matches; skipping download.

[3/10] Link existing inventory to DJ
→ poetry run python -m tagslut.exec.precheck_inventory_dj --db /Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-03-04/music_v3.db --decisions-csv /Users/georgeskhawam/Projects/tagslut/artifacts/compare/precheck_decisions_20260315_133407.csv --dj-root /Volumes/MUSIC/DJ_LIBRARY --playlist-dir /Volumes/MUSIC/DJ_LIBRARY --playlist-base-name dj-precheck-inventory --artifact-dir /Users/georgeskhawam/Projects/tagslut/artifacts/compare/precheck_inventory_dj_20260315_133414
{
  "existing_mp3_rows": 0,
  "playlist_rows_written": 0,
  "resolved_rows": 0,
  "skip_rows": 1,
  "transcoded_rows": 0,
  "unresolved_rows": 1
}
Inventory-backed DJ playlist: /Volumes/MUSIC/DJ_LIBRARY/dj-precheck-inventory.m3u
No new candidates to process; intake pipeline finished.
```

**stderr excerpt**

```text
[LEGACY] WARNING: tools/get --dj is deprecated.
...
CONTRACT NOTE: All tracks are precheck-hit inventory. DJ output will be produced via
  the precheck-inventory fallback path (link_precheck_inventory_to_dj), NOT the
  promotion-driven build_pool_v3 path. Results may differ from a first-time intake run.
  For a deterministic DJ build from canonical state, use: tagslut dj pool-wizard
```

## Match against `DJ_WORKFLOW_TRACE.md`

| Trace doc claim | Runtime result | Match? |
|---|---|---|
| New candidates: download → promote → `PROMOTED_FLACS_FILE` → DJ build | Observed through promotion and `PROMOTED_FLACS_FILE` generation | ✓ |
| Precheck-hit inventory: skip download/promotion → `link_precheck_inventory_to_dj` | Observed exactly, including explicit contract note | ✓ |
| Primary DJ path is tied to promoted FLACs from the same run | Observed; DJ stage read promoted FLAC list | ✓ |
| Precheck-hit fallback is alternate-path behavior, not the same contract | Observed; stderr says results may differ from promotion-driven path | ✓ |
| Reliable DJ-usable MP3 without new FLAC promotion is not guaranteed | Observed; fallback produced `transcoded_rows=0`, `resolved_rows=0`, `unresolved_rows=1` | ✓ |
| Rekordbox/DJ output is accessory rather than stable contract under `tools/get --dj` | Supported by both runs and by the runtime deprecation warning | ✓ |

## Divergences documented

1. The branch split is real and user-visible.
   New track takes the promotion-fed path.
   Existing track takes the `precheck_inventory_dj` fallback path.

2. Promotion does not guarantee DJ MP3 output.
   In the new-track run, the file was downloaded and promoted successfully, but the DJ stage still skipped because it resolved zero promoted identity IDs before `build_pool_v3`.

3. Precheck-hit fallback did not produce a DJ MP3.
   In the existing-track run, the fallback path executed but found no existing MP3, did not transcode, and left the row unresolved.

4. `tools/get --dj` remains explicitly legacy and non-deterministic.
   The runtime warning matches the audit docs and contradicts any expectation that `--dj` is a clean primary workflow.
