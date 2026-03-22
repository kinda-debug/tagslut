# Gig Execution Plan v3.3

## Summary

- `tagslut` owns pool selection, source resolution, copying, and audit artifacts. Rekordbox desktop owns analysis, curation, and USB export.
- Do not rely on repo-local Rekordbox automation for this gig window: `rekordbox_prep.py` depends on an external `rekordbox_prep_dj.py` script, and `gig build` writes a Rekordbox DB through `pyrekordbox` when available; if `pyrekordbox` is missing it errors, and if the available API surface is unsupported or cannot create/open the DB cleanly it may fall back to a lightweight local DB. That still makes Rekordbox desktop the correct last-mile owner.
- Final deliverable: one executed pool run, one Rekordbox import from that pool only, five intent playlists, seven time-of-night playlists, and two verified USBs.
- Allow a small-adds lane only for obvious gaps, capped and cut off by `T-24`.

## The Non-Negotiable Boundary

tagslut owns selection and copying. Rekordbox owns analysis, curation, and USB export. This is grounded in the actual repo structure: `classify.py` sits on top of `curation.py` and `transcode.py`; `rekordbox_prep.py` wraps an external script and is not a Rekordbox replacement; `export.py` handles curation plus optional key detection and transcode but is untrusted for the live path; `key_detection.py` depends on `keyfinder-cli` and does not guarantee populated key data. Do not touch `rekordbox_prep.py` or `export.py` for this window.

The safe path is:
1. Build one controlled MP3 gig pool from `MASTER_LIBRARY`
2. Validate the pool at file level
3. Import only that pool into Rekordbox
4. Analyze only what matters
5. Build intent playlists first, then time-of-night playlists
6. Export and verify two USBs
7. Freeze

---

## PHASE 0 — Environment Verification

Run before writing a single profile JSON. This is the most likely silent failure point.

```bash
ls -lh "$TAGSLUT_DB"
ls -ld "$MASTER_LIBRARY" "$DJ_LIBRARY" "$VOLUME_WORK"
df -h "$VOLUME_WORK"
poetry run tagslut --version
python -m tagslut dj pool-wizard --help
```

**Hard gate — stop completely if any of these are true:**
- DB path wrong or unreadable
- Master root wrong or unreadable
- Free space is tight relative to expected pool size
- CLI environment broken

Do not proceed past Phase 0 with any uncertainty. A bad environment does not become a good one after execute.

---

## A — Freeze Scope

**Output for this 36-hour window — nothing more:**
- One final MP3 pool folder
- One Rekordbox import from that pool only
- Five intent playlists (10 PRIME, 20 CLUB RESERVE, 30 BRIDGE, 40 FAMILIAR VOCALS, 99 EMERGENCY)
- Seven time-of-night playlists (00–06)
- Two exported, verified USBs

**Non-goals:**
- No schema work
- No tag refactors
- No DB cleanup campaign
- No new tooling
- No last-mile Rekordbox automation
- No changes to `MASTER_LIBRARY`

Write the freeze as a real artifact at `$VOLUME_WORK/gig_runs/gig_2026_03_13/SCOPE_FREEZE.txt`, one sentence per non-goal. Having it as a file makes it harder to silently break at 3 a.m.

---

## B — Run Directory Structure

```
gig_2026_03_13/
├── SCOPE_FREEZE.txt          ← written at step A, never touched again
├── profile.json
├── run.log
├── gig_2026_03_13_<timestamp>/  ← created by pool-wizard
│   ├── answers.json
│   ├── cohort_health.json
│   ├── cohort_duplicates.json
│   ├── selected.csv
│   ├── plan.csv
│   ├── pool_manifest.json
│   ├── pool/
│   ├── receipts.jsonl          ← after execute
│   ├── failures.jsonl          ← after execute
│   └── POOL_VERIFIED.txt       ← written by hand after validation
```

`POOL_VERIFIED.txt` is a human checkpoint, not a generated artifact. Do not import into Rekordbox until you have written it yourself.

---

## C — Profile JSON

Start conservative and broad. The initial pool must reveal the cohort before you tighten anything.

```json
{
  "pool_name": "gig_2026_03_13",
  "layout": "by_role",
  "filename_template": "{artist} - {title}.mp3",
  "require_flac_ok": true,
  "integrity_states": ["ok"],
  "require_artist_title": false,
  "only_profiled": false,
  "create_playlist": false,
  "pool_overwrite_policy": "always"
}
```

**Strategic note:** do not try to encode bridge, familiar-vocal, or emergency logic into the initial profile. Keep the source build broad. The socially strategic curation — which tracks cross over, which tracks rescue — belongs in Rekordbox where you can hear and judge, not in a filter pass where metadata makes those calls blindly.

**Before trusting `layout: "by_role"`:** confirm in plan mode that role distribution is not degenerate. If 70%+ of selected tracks have no role assigned, `by_role` is noise. Switch to `by_genre` as fallback rather than proceeding with a misleading layout.

**Tightening order — one axis at a time, always:**
1. `genre_include` / `genre_exclude` (core identity)
2. `bpm_min` / `bpm_max` (bar usability)
3. `min_energy`
4. `min_rating`
5. `set_role_include` (only after confirming role spread is healthy)
6. `require_artist_title: true` (last resort only, after cohort count is confirmed safe)

**Small-adds lane:**
- Only for clear holes in `BRIDGE`, `FAMILIAR VOCALS`, or `EMERGENCY`
- Max 10 to 15 tracks
- No new adds after `T-24`
- If used, rerun plan mode and re-evaluate before execute

---

## D — Plan Mode First, Always

```bash
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_LIBRARY" \
  --out-root "$VOLUME_WORK/gig_runs/gig_2026_03_13" \
  --non-interactive \
  --profile /path/to/profile.json
```

**Inspect in this order:**

| Artifact | What to check |
|---|---|
| `cohort_health.json` | Cohort size, identity coverage, relink/export/transcode summary |
| `selected.csv` | Final count, genre/role spread, readability, bridge/emergency candidates |
| `plan.csv` | `cache_action`, `pool_action`, `warning`, `final_dest_path` |
| `pool_manifest.json` | Selected/skipped/failed summary, total size vs free space |

**Hard abort conditions:**
- `selected = 0`
- Role distribution is degenerate and you were depending on it
- Too many `cache_action=transcode` rows for the time budget
- Pool cannot support all five intent functions
- Filenames or destination layout are too messy for emergency browsing

**Added check:** after reading `selected.csv`, ask whether the pool already supports four functions — core prime-time, club reserve, bridge, emergency. If the shape is clearly absent, fix the profile before execute. Do not run execute hoping the shape appears.

---

## E — Pool Health and Pressure-Test Gates

**Recommended pool size:**
- 90–150 tracks for a flexible bar night
- 70–100 if you know the room well
- Never more than you can mentally navigate cold under pressure

**Required composition inside the pool:**

| Layer | Target share | Approx track count |
|---|---|---|
| Core prime-time | 55–65% | 55–90 |
| Bridge | 15–20% | 15–25 |
| Club reserve | 10–15% | 10–20 |
| Emergency | 5–10% | 8–15 |
| Warmup/closing/left-turn | remainder | as needed |

**Bridge qualification rule — a bridge track must pass at least two of these three:**
- Ordinary bar listeners recognize it or emotionally grab onto it
- It still mixes naturally with your core sound
- You would not hate hearing it next to one of your real records

If it only passes the first test, it belongs in 99 EMERGENCY, not 30 BRIDGE. This distinction protects Prime from being diluted by recognition-only material.

**Key data check:** `key_detection.py` depends on `keyfinder-cli` and degrades gracefully. Decide now whether harmonic sorting is central to this gig. If yes, spot-check key coverage in `selected.csv` before execute — a pool where key is blank on most tracks still works, but you need to know before you are in Rekordbox expecting key columns to be useful.

---

## F — Execute Once

```bash
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_LIBRARY" \
  --out-root "$VOLUME_WORK/gig_runs/gig_2026_03_13" \
  --execute \
  --non-interactive \
  --profile /path/to/profile.json \
  2>&1 | tee "$VOLUME_WORK/gig_runs/gig_2026_03_13/run.log"
```

Pipe to `tee` unconditionally. A mid-run failure without a log means debugging from memory. Treat the exact `Run directory:` printed by execute as canonical.

**Immediate post-execute check:**
```bash
RUN_DIR="/absolute/path/to/gig_2026_03_13_<timestamp>"
find "$RUN_DIR/pool" -name "*.mp3" | wc -l
```

This count must match `selected` in `pool_manifest.json`. A mismatch is a copy failure. Do not proceed to Rekordbox if counts diverge.

**Success criteria:**
- `selected > 0`
- `failed = 0` in pool_manifest.json
- No copy failures in `run.log`
- All output under the timestamped run directory
- No writes to `MASTER_LIBRARY` or unintended writes to `DJ_LIBRARY`

**Do not rerun execute unless the first pool is clearly unusable.** Every rerun adds confusion and erodes your confidence in which version is canonical.

---

## G — Pool File Validation

```bash
RUN_DIR="/absolute/path/to/gig_2026_03_13_<timestamp>"
bash scripts/gig/03_validate_pool.sh "$RUN_DIR"
```

Then do a real-world sanity pass:
- Open a random sample and confirm files actually play
- Confirm filenames are legible enough for emergency browsing
- Confirm there are no obviously broken or missing copies

**Only after all checks pass, write `POOL_VERIFIED.txt` by hand inside the timestamped run directory.**

---

## H — Import into Rekordbox

Import only the timestamped `pool/` directory. Nothing else. Do not import your whole DJ library. Do not mix this run with any older half-prepared folders. The goal is a small, deterministic, fully legible gig collection.

---

## I — Analyze Only What Matters

- Analyze all imported tracks
- Confirm waveform generation
- Fix only obviously broken beatgrids on tracks you know you will play
- Add hot cues only on high-impact or high-pressure tracks

This is a gig-prep pass, not a library-prep campaign. Depth only where it directly protects the performance.

---

## J — Build Intent Playlists First

Before building any time-of-night playlist, carve the imported pool into the five intent playlists. These are your musical identity map for the night.

| Playlist | Description | Target count |
|---|---|---|
| 10 PRIME | Leftfield / Deep / Indie Electro / Nu Disco — the real voice of the night | 35–60 |
| 20 CLUB RESERVE | Techno / Club Pressure — tougher material, available but not the focus | 10–20 |
| 30 BRIDGE | Known But Cool — crossover between your taste and crowd recognition | 15–25 |
| 40 FAMILIAR VOCALS | Edits / Remixes / Bar Hooks — vocals and recognition matter explicitly here | 8–15 |
| 99 EMERGENCY | Rescue / Singalong / Reset — must work if everything else fails | 10–20 |

**Separation rules:**
- A track should not live in BRIDGE just because it is known
- A track should not live in PRIME if its primary value is recognition
- A track in FAMILIAR VOCALS should still be something you can mix confidently
- EMERGENCY must be curated to actually rescue — do not dump low-quality filler there

This separation is how you prevent the core voice of the night from being diluted under crowd pressure.

---

## K — Build Time-of-Night Playlists Second

Once intent playlists exist, draw from them to build the time-of-night structure.

| Playlist | Target count | Primary source |
|---|---|---|
| 00 Warmup | 15–25 | PRIME (low energy end), BRIDGE |
| 01 Builders | 15–25 | PRIME, BRIDGE |
| 02 Peak A | 15–20 | PRIME, CLUB RESERVE |
| 03 Peak B | 15–20 | PRIME, CLUB RESERVE |
| 04 Left Turns / Vocals / Classics | 8–15 | BRIDGE, FAMILIAR VOCALS |
| 05 Reset / Breath | 8–12 | PRIME (low energy), BRIDGE |
| 06 Closing | 8–12 | PRIME, BRIDGE, FAMILIAR VOCALS |

**Hard rules for every playlist:**
- Playable standalone
- At least 3 strong openers
- At least 3 clean exits
- 99 EMERGENCY remains a separate standalone playlist, not a time-of-night entry

---

## L — Stress-Test Before Export

**Standard transition check:**
- First three transitions of each time-of-night playlist
- Remove weak duplicates and same-function redundancy
- Fix any waveform, beatgrid, or phrasing anomalies on key tracks
- Confirm enough bridges exist between neighboring time-of-night playlists

**Social transition check — specific to this gig type:**

Test these moves explicitly before you declare the set ready:

| Transition | Why it matters |
|---|---|
| PRIME → BRIDGE | The most common crowd-management move |
| BRIDGE → PRIME | The hardest — can you pull the room back? |
| BRIDGE → FAMILIAR VOCALS | When the crowd needs a hook |
| FAMILIAR VOCALS → PRIME | Reclaiming identity after a concession |
| PRIME → CLUB RESERVE | Raising the floor when the room earns it |
| CLUB RESERVE → PRIME | Bringing it back without it feeling like a retreat |
| EMERGENCY → recovery | Can you get back to your real sound from the rescue? |

If any of these transitions has no natural path in the material, fix it now, not during the gig.

---

## M — Export and Verify

Export USB A first. Verify USB A completely. Then export or clone USB B from the verified Rekordbox state. Do not assume USB B is valid because USB A was.

**Verification checklist for each USB:**
- All playlists (intent + time-of-night) visible
- All tracks load without missing path warnings
- Hot cues visible on critical tracks
- Random sample of 10 tracks plays cleanly
- **Mandatory coverage check:** at least one PRIME track, one BRIDGE track, one CLUB RESERVE track, one FAMILIAR VOCALS track, and one EMERGENCY track all load correctly

---

## N — Freeze

Once both USBs pass verification, the work is done.

- No more pool reruns
- No more playlist restructuring
- No more broad retagging
- No more curation redesign
- Only microscopic fixes to clearly broken items

This is the finish line. Treat it as one.

---

## Timeline

| Window | Work |
|---|---|
| T‑36 to T‑34 | Phase 0: environment verification |
| T‑34 to T‑30 | Freeze scope, write profile, run plan mode, inspect artifacts |
| T‑30 to T‑24 | Tighten filters, optional small adds, rerun plan only as needed, stop when pool shape is right |
| T‑24 to T‑20 | Execute, validate counts, validate files, write POOL_VERIFIED.txt |
| T‑20 to T‑14 | Import Rekordbox, analyze, carve intent playlists |
| T‑14 to T‑8 | Build time-of-night playlists, stress-test all transitions |
| T‑8 to T‑4 | Export USB A → verify → export USB B → verify |
| T‑4 to gig | Freeze completely |

---

## Definition of Done

You are done when every item on this list is true — not most of them:

- One executed pool run exists with clean artifacts under the timestamped run directory
- `POOL_VERIFIED.txt` exists and was written by hand after file-level checks passed
- Rekordbox has imported and fully analyzed the pool
- All five intent playlists exist with correct separation between PRIME and BRIDGE
- All seven time-of-night playlists are complete and pressure-usable
- Every playlist has at least 3 openers and 3 exits
- 99 EMERGENCY can carry the night alone
- Social transitions (PRIME ↔ BRIDGE, EMERGENCY → recovery) have been explicitly tested
- USB A and USB B both load all playlists and tracks correctly

---

## The Offline Cheat Sheet

Fill this in before export. It forces commitment to actual track names — the only thing that helps when the software is slow, the lighting is bad, and your read was wrong.

```
OPENERS (10):         [fill before export]
BRIDGE (10):          [fill before export]
PEAK WEAPONS (10):    [fill before export]
EMERGENCY (10):       [fill before export]

USB A: verified ___    USB B: verified ___
Last Rekordbox backup: ___
```
