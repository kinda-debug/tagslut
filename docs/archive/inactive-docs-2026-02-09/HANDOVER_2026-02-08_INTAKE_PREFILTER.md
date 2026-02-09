# Intake Prefilter Handover - 2026-02-08

## Scope

Add a fast pre-download Beatport filter to intake so obvious duplicates are skipped before download, while keeping the pipeline move-only and operator-safe.

## Current Status (Verified In This Checkout)

1. Files and commands present:
- `tools/get-intake`
- `tools/review/beatport_prefilter.py`

2. Local validation run:
- `bash -n tools/get-intake` -> OK
- `python -m py_compile tools/review/beatport_prefilter.py` -> OK
- `tools/get-intake --help` shows:
  - `--skip-beatport-prefilter`
  - `--prefilter-margin-ms`

## Changes Applied

1. New prefilter script:
- `tools/review/beatport_prefilter.py`
- Inputs:
  - `--db`
  - `--url` (Beatport track/release/chart/playlist URL)
  - `--library-root`
  - `--credentials`
  - `--duration-margin-ms`
- Matching strategy:
  - exact `beatport_id`
  - exact `ISRC`
  - heuristic `artist + title + duration` within margin
- Outputs:
  - `artifacts/compare/beatport_prefilter_decisions_*.csv`
  - `artifacts/compare/beatport_prefilter_keep_urls_*.txt`
  - `artifacts/compare/beatport_prefilter_summary_*.json`

2. Intake orchestrator integration:
- `tools/get-intake`
- New options:
  - `--skip-beatport-prefilter`
  - `--prefilter-margin-ms` (default `4000`)
- Behavior:
  - For Beatport URLs in download mode, prefilter runs first.
  - Download step uses generated `keep_urls.txt` through `bpdl -q`.
  - If keep count is `0`, intake exits before download and scan stages.
  - Non-Beatport flows remain unchanged.

3. Documentation references:
- `README.md`
- `docs/SCRIPT_SURFACE.md`

## Runtime Semantics

1. `tools/get-intake` defaults to dry-run move planning.
2. `--execute` controls actual plan application (move execution), not only download.
3. Move execution path remains move-only through `tools/review/move_from_plan.py`.
4. Prefilter keep count `0` causes clean early exit.

## Validation

1. Verified in this checkout:
- `bash -n tools/get-intake` -> OK
- `python -m py_compile tools/review/beatport_prefilter.py` -> OK
- `tools/get-intake --help` output consistent with documented flags

2. Reported earlier integration examples:
- Chart URL `https://www.beatport.com/chart/warm-up-essentials-2026-electronica/879544`:
  - `Prefilter candidates: 19, Keep: 19, Skip: 0`
- Track URL `https://www.beatport.com/tracks/19025655`:
  - `Keep: 0`, download skipped, pipeline exits early

## Limitations

1. This is a fast prefilter, not final dedupe authority.
2. No audio fingerprinting is possible pre-download.
3. Artist/title heuristic can under-match or over-match edge cases.
4. Post-download audit/planning remains mandatory for high-confidence decisions.

## Operator Runbook

1. Dry-run intake with prefilter:
```bash
tools/get-intake \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-08/music.db \
  --batch-root /Volumes/DJSSD/beatport \
  "https://www.beatport.com/chart/warm-up-essentials-2026-electronica/879544"
```

2. Execute moves after reviewing plans:
```bash
tools/get-intake \
  --execute \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-08/music.db \
  --batch-root /Volumes/DJSSD/beatport \
  "https://www.beatport.com/chart/warm-up-essentials-2026-electronica/879544"
```

3. Disable prefilter (legacy behavior):
```bash
tools/get-intake \
  --skip-beatport-prefilter \
  --db /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-02-08/music.db \
  --batch-root /Volumes/DJSSD/beatport \
  "https://www.beatport.com/chart/warm-up-essentials-2026-electronica/879544"
```

4. Tighten heuristic duration margin:
```bash
tools/get-intake ... --prefilter-margin-ms 2500
```

## Next Action

Run one full `tools/get-intake --execute` batch on a fresh Beatport chart and review:
- prefilter summary JSON
- promote/stash/quarantine plan counts
- final move logs
