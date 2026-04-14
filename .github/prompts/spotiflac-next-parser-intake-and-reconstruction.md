You are auditing and extending the `tagslut` repository to build the cleanest possible ingestion path for mixed historical SpotiFLAC / SpotiFLAC Next batches, and a solid forward path for future SpotiFLAC Next batches.

This is not a greenfield design exercise. Treat the staging area, logs, reports, playlists, embedded tags, shell history, and existing DB/state as a messy live system in transition. Follow evidence. Prefer durable identifiers and extracted file/tag truth over assumptions.

Context you must anchor on:

- From now on, only **SpotiFLAC Next** will be used for new batches.
- But during this trial-and-error period, **both SpotiFLAC and SpotiFLAC Next were used**, so the ingestion path must handle mixed historical artifacts and infer the cleanest reconstruction possible from whatever exists.
- The SpotiFLAC Next logs copied from the UI are being saved to:
  `/Users/georgeskhawam/Projects/tagslut/_ingest/spotiflac_logs`
- You also have pasted, truncated terminal output from prior runs. Treat those pasted terminal snippets as evidence, not as exhaustive truth.
- Additional evidence source you are allowed to use:
  `/Users/georgeskhawam/.zsh_history`
- Do not assume provider from extension.
  - FLAC is not always “Tidal”.
  - Qobuz can also yield FLAC.
  - Tidal may not be the only source of lossless.
  - Apple Music ALAC shows up as `.m4a`.
  - There is auto-convert to `.mp3`.
  - Infer provider/source/mode from logs, DB/state, embedded tags, report files, shell history, and path/report context combined. Never from extension alone.

Observed behavior and local state to respect:

- Current SpotiFLAC Next config writes to:
  `/Volumes/MUSIC/staging/SpotiFLACnext`
- Current Next config has:
  - `autoConvertAudio: true`
  - `autoConvertFormat: mp3`
  - `autoConvertBitrate: 320k`
  - `createM3u8File: true`
  - `createM3u8ForConvertedAudio: true`
  - folder template: `{album_artist}/({year}) {album}`
  - newer filename template: `{track}. {title} - {artist}`
  - earlier config snapshot used: `{title} - {artist}`
  - config drift exists across runs and must be handled, not ignored.
- Next recent fetch memory includes mixed upstream inputs:
  - Spotify album/track URLs
  - Qobuz direct album URLs
  - Tidal track URLs
- There is at least one malformed recent_fetch record where `artist` is actually a Spotify artist URL.
- Historical SpotiFLAC logs show classic staging under:
  `/Volumes/MUSIC/staging/SpotiFLAC/...`
- Historical SpotiFLAC terminal output shows:
  - `Found ISRC in cache`
  - `Found identifiers via Spotify metadata: isrc=... upc=...`
  - `Using Tidal URL: ...`
  - provider resolution through Songlink / Odesli / Deezer / Songstats
  - downloads to FLAC
  - lyrics embedding
  - metadata embedding
- Current Next terminal output shows:
  - mixed resolver/provider behavior
  - Apple Music ALAC `.m4a`
  - auto-convert to `.mp3`
  - metadata embedding
  - ISRC and UPC seen in terminal output
  - provider URL resolution through Odesli and fallbacks
- The `.txt` report is useful but incomplete.
  - It is not the only truth surface.
  - Success metadata is often richer in file tags and terminal output than in the report.
- The UI logs are ephemeral; copied logs are a provenance source and should be treated as first-class ingest artifacts.
- `.zsh_history` is a supplemental reconstruction surface for operator actions and run history, especially to recover:
  - how SpotiFLAC / SpotiFLAC Next was launched
  - whether runs were started via the app binary directly, `wails dev`, wrappers, or shell pipelines
  - whether stdout was redirected via `tee`
  - historical staging roots and ad hoc test paths
  - related inspection commands run by the operator around the same time
  - command-order context for mixed trial-and-error batches

Important constraints for `.zsh_history`:

- Treat it as suggestive provenance, not perfect truth.
- A command in shell history proves operator intent and likely execution attempt, but not successful completion.
- Corroborate `.zsh_history` with stronger evidence when possible:
  - copied UI logs
  - pasted terminal output
  - `.txt` reports
  - `.m3u8` / `_converted.m3u8`
  - embedded file tags
  - `history.db`
  - `isrc_cache.db`
  - `recent_fetches.json`
  - `config.json`
- Use `.zsh_history` to improve run reconstruction, app-generation attribution, and operator workflow context, especially where logs are missing or truncated.
- When reconstructing batches, include `.zsh_history` in the evidence merge and persist any useful shell-derived context in the DB as low-to-medium trust provenance, with clear source attribution.

Your job:

Build or patch the ingestion path so that tagslut can ingest these batches cleanly and preserve provenance and metadata as completely as possible, while also establishing a robust future path for SpotiFLAC Next.

Primary output goals:

1. Lossless originals go to `MASTER_LIBRARY`.
2. Lossy converted files go to `MP3_LIBRARY`.
3. Both should be fully tagged.
   - The lossy side stays rich now; it will be stripped down later when entering the DJ pool.
4. The database should retain as much provenance and metadata as possible from every available source, even when some fields are missing in some runs.

High-level ingestion rules:

- Treat each downloaded asset as a provenance event with potentially multiple evidence surfaces:
  - copied UI logs
  - pasted terminal logs
  - `.txt` report
  - `.m3u8`
  - `_converted.m3u8`
  - embedded file tags
  - `history.db`
  - `isrc_cache.db`
  - `recent_fetches.json`
  - `config.json`
  - `.zsh_history`
- Reconstruct the cleanest per-track truth by merging evidence, not by trusting a single surface.
- Prefer stable identifiers in this order when available:
  - ISRC
  - upstream provider track ID if clearly attributable
  - Spotify track ID
  - exact file path hash / audio fingerprint fallback if needed
- Persist partial truth instead of dropping it.
  - If a field is present in one source but not another, keep it with provenance.
  - Missing UPC is normal. Missing Spotify URL is normal. Some tracks will have one but not the other.
  - Everything useful should be collected and stored in the DB with source attribution.

What metadata must be collected and retained if present:

- ISRC
- UPC
- Spotify URL
- Spotify track ID / album ID / playlist ID where relevant
- provider URLs:
  - Qobuz
  - Tidal
  - Apple Music
  - Deezer
  - Amazon
- provider actually used for download
- input mode:
  - resolver / Spotify-seeded
  - direct-link / Qobuz
  - direct-link / Tidal
  - other direct input if observed
- source app generation:
  - SpotiFLAC
  - SpotiFLAC Next
- launch mode if inferable:
  - app binary
  - `wails dev`
  - wrapper script
  - shell pipeline
  - other observed execution path
- stdout/stderr capture mode if inferable:
  - direct terminal
  - redirected
  - `tee`
  - unknown
- output file path
- output container/format:
  - flac
  - m4a
  - mp3
- whether file is original or auto-converted derivative
- cover embedded / lyrics embedded if detectable
- title
- artists
- album
- album artist
- track number / disc number
- release year/date
- any MusicBrainz / lyrics provenance if present
- staging path
- historical staging root if inferable
- ad hoc test path if observed
- final library path
- run / batch grouping if inferable
- config snapshot or config-derived context that materially affects interpretation
- shell-derived operator context if useful and attributable
- anomaly flags:
  - malformed artist URL
  - path template drift
  - sparse metadata
  - missing tags
  - duplicate/conflicting identifiers
  - weak provider attribution
  - shell-history-only inference

Important modeling constraints:

- Do not collapse originals and converted derivatives into one row.
  - They are related assets with shared identity but different file roles.
- Preserve the relationship between:
  - original lossless source file in staging
  - converted mp3 derivative in staging
  - final destination in MASTER_LIBRARY or MP3_LIBRARY
- Do not assume every success has a useful `.txt` row.
- Do not assume every file has every tag.
- Do not assume current config applied to all historical batches.
  - There is config drift and mixed generations.
- Do not assume `.m4a` means lossy.
  - It may be ALAC.
- Do not assume `.flac` means Tidal.
  - Infer provider from logs/evidence.
- Do not assume Spotify is the downloader.
  - Spotify is often only the metadata/resolver input.
- Do not treat shell history as completion evidence.
  - It is provenance context, not success proof.

What I want you to do in the repo:

1. Find the existing SpotiFLAC / SpotiFLAC Next parser and intake path.
2. Audit where it is still assuming:
   - one log source
   - one app generation
   - extension → provider inference
   - report-only ISRC handling
   - weak provenance retention
   - no shell-history reconstruction layer
3. Patch it so it can ingest mixed historical batches and future Next batches robustly.
4. Update all active documentation affected by the change.
   - This includes operator-facing workflow docs, intake docs, architecture/storage docs, migration/backfill notes, and any prompt/instruction surfaces that describe the SpotiFLAC intake path.
   - Do not update archived or obviously obsolete docs unless they are still referenced by active docs.
   - Where docs and code diverge, bring active docs into alignment with implemented behavior.

Design requirements for the solution:

- Start from observed artifacts on disk and in logs, not from theory.
- Use `.m3u8` and `_converted.m3u8` as strong file-path truth surfaces when available.
- Read embedded metadata from actual files after path resolution.
- Mine copied logs and pasted terminal output for provider/mode/provenance that the files do not contain.
- Mine DB/state (`history.db`, `isrc_cache.db`, `recent_fetches.json`, `config.json`) for identifiers and input provenance.
- Mine `.zsh_history` for launch mode, shell redirection behavior, run adjacency, staging-path drift, and operator workflow context.
- Store provenance source per field where feasible, or at minimum per record.
- Make the solution robust to partial evidence.
- Prefer append-only provenance/event recording over destructive normalization.
- Maintain idempotence: rerunning intake on the same batch should reconcile, not duplicate blindly.
- Emit clear anomalies and low-trust flags where data conflicts or is incomplete.
- Clearly separate:
  - file/tag truth
  - log-derived truth
  - DB/state-derived truth
  - shell-history-derived inference

What I expect as concrete outputs from you:

- A code audit summary of the current ingestion path and its specific gaps.
- The exact files/functions/modules you changed.
- A clear explanation of the reconciliation logic for:
  - original vs converted files
  - historical SpotiFLAC vs SpotiFLAC Next
  - mixed metadata completeness
  - provider attribution
  - shell-history-assisted run reconstruction
- Tests covering representative mixed cases:
  - Tidal FLAC + MP3 derivative
  - Apple Music ALAC `.m4a` + MP3 derivative
  - resolver-mode Spotify input ending in non-Spotify download
  - Qobuz direct-link batch
  - missing UPC
  - missing Spotify URL
  - malformed artist URL in recent fetches
  - historical SpotiFLAC staging layout
  - `.zsh_history` indicating `wails dev` launch without corroborated success
  - `.zsh_history` indicating `tee`-captured runs
  - shell-only staging path clue later corroborated by playlists or files
- A migration if the DB schema needs to change.
- A backfill/reconciliation plan for already downloaded staging batches.
- A documentation update summary covering all active docs changed.
- A recommendation for the cleanest future ingestion workflow using only SpotiFLAC Next.

DB/storage expectations:

You should extend the DB/schema as needed so that tagslut can retain:
- track identity
- asset identity
- derivative relationships
- provenance events
- field-level or record-level source attribution
- anomalies / trust levels
- final routing result:
  - MASTER_LIBRARY
  - MP3_LIBRARY

It should also retain, where inferable and attributable:
- shell-derived launch context
- app-generation attribution confidence
- redirection / `tee` evidence
- run reconstruction confidence
- source-of-claim for any shell-history-derived field

Routing expectations:

- Lossless originals:
  - send to `MASTER_LIBRARY`
- Lossy derivatives:
  - send to `MP3_LIBRARY`
- Both should be fully tagged before final placement.
- Do not prematurely strip tags for DJ use.
  - That happens later when building the DJ pool.

Working style:

- Do not rewrite everything blindly.
- Start from the active operator/docs/code surface.
- Follow evidence from the logs and artifacts.
- Distinguish between:
  - confirmed defect
  - design gap
  - historical compatibility debt
  - missing provenance retention
  - shell-history-only inference
- Prefer the cleanest solution that works for both backfill and future batches.
- Be concrete. No vague architecture prose.
- Show the exact patch plan and then implement it.
- Update active docs as part of the same change set, not as an afterthought.

Reference artifacts you must account for during your audit/patch:

- copied SpotiFLAC Next logs:
  `/Users/georgeskhawam/Projects/tagslut/_ingest/spotiflac_logs`
- pasted truncated terminal output from both SpotiFLAC and SpotiFLAC Next
- mixed staging roots:
  - `/Volumes/MUSIC/staging/SpotiFLAC`
  - `/Volumes/MUSIC/staging/SpotiFLACnext`
- supplemental shell history:
  `/Users/georgeskhawam/.zsh_history`

Deliverable format:

1. Findings
2. Patch plan
3. Implemented changes
4. Tests added/updated
5. Documentation updated
6. Remaining ambiguities or operator decisions
7. Recommended future-only SpotiFLAC Next workflow

Do the work, not just the analysis.
