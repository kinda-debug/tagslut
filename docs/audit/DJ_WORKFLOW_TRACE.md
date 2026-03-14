# DJ Workflow Trace

This document traces the implemented workflow in repo-relative terms and answers the required end-to-end questions.

## Path trace

### A. Download / intake

1. Operator runs `tools/get <provider-url> [--dj]`.
2. `tools/get` parses flags and routes provider/input handling.
3. General intake work is delegated to `tools/get-intake`.
4. `tools/get-intake` performs precheck/prefilter decisions.
5. If candidates remain, download and promote stages proceed.

**Runtime verification still required:** exact shell execution in the checked-out repo could not be rerun in the current writable sandbox.

### B. `--dj`

1. `tools/get` forwards `--dj` into intake flow.
2. `tools/get-intake` sets `DJ_MODE=1`.
3. After promote-time stages, the DJ build stage is reached.
4. The stage counts lines in `PROMOTED_FLACS_FILE`.
5. If zero, it warns and exits without DJ copies.

### C. Promotion

1. Promotion creates the run-local list of promoted FLACs.
2. That list feeds DJ MP3 generation.
3. No promoted FLAC list means no normal DJ build from that run.

### D. MP3 generation

There are two verified paths:

1. **Primary intake path**
   - Source feed: `PROMOTED_FLACS_FILE`.
   - Consumer: DJ pool/build flow referenced from `tools/get-intake` and `scripts/dj/build_pool_v3.py`.

2. **Precheck-hit fallback path**
   - Source feed: precheck skip rows + DB lookups in `tagslut/exec/precheck_inventory_dj.py`.
   - Behavior: reuse `dj_pool_path`, tag-match under DJ root, or transcode from source/snapshot using `tagslut.exec.transcoder`.

## Explicit answers

### What exact artifact feeds MP3 generation today?

`PROMOTED_FLACS_FILE` feeds the normal intake DJ build path.

### Whether MP3 generation is tied to promoted FLACs from the same run?

Yes, on the primary intake DJ path.

### What happens when precheck decides the track already exists?

`tools/get-intake` short-circuits download/promotion and calls `link_precheck_inventory_to_dj`, which is backed by `tagslut/exec/precheck_inventory_dj.py`.

### Whether a user can reliably get a DJ-usable MP3 without a new FLAC promotion event?

No. The repo provides a fallback linker/transcoder path, but it is conditional, alternate-path behavior, not a clean reliable primary contract.

### Whether existing MP3s can be retroactively admitted cleanly?

No clean first-class admission flow was verified. The repo contains path/tag matching and some transcoding fallbacks, but not a dedicated normalized admission model.

### Whether Rekordbox XML is currently a stable output contract or just an accessory utility?

Accessory utility.

## Real code path evidence

| Workflow step | Exact repo path | Symbol/script | Verified behavior |
|---|---|---|---|
| Entry wrapper | `tools/get` | shell script | Parses `--dj`, dispatches intake/provider flow |
| Intake engine | `tools/get-intake` | shell script | Precheck, download, promote, DJ build gating |
| Precheck DJ link | `tools/get-intake` | `link_precheck_inventory_to_dj` | Alternate DJ path when inventory already satisfies request |
| Precheck DJ resolver | `tagslut/exec/precheck_inventory_dj.py` | `_load_skip_rows`, `_query_exact_row`, `_DjTagIndex`, transcode imports | Resolves skip rows to existing or newly transcoded MP3s |
| MP3 transcode | `tagslut/exec/transcoder.py` | `transcode_to_mp3`, `transcode_to_mp3_from_snapshot` | Produces MP3s in fallback flow |
| DJ export/prep CLI | `tagslut/cli/commands/dj.py` | `export`, `prep-rekordbox` | Separate DJ-facing export/prep commands |
| Rekordbox support | `tagslut/adapters/rekordbox/`, `tagslut/dj/rekordbox_prep.py` | modules/utilities | XML/prep-related helpers exist but are not proven as formal contract |

## Trace implications

The end-to-end flow is not a single pipeline. It is a branching system:

- branch 1: new candidates -> download -> promote -> `PROMOTED_FLACS_FILE` -> DJ build
- branch 2: precheck-hit inventory -> skip download/promote -> precheck inventory DJ link/transcode

Those branches do not express the same data contract, and they should not share one operator-facing `--dj` promise.
