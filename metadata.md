Across those repos, there’s a pretty clear pattern: only two of them are really about generating reusable tags for your own files, one is very useful for key normalization, and the rest are mostly playlisting or recommendation layers built on already-existing features.

The strongest candidates for an actual tagging pipeline are audio-analyzer, beatlyze-analyzer, and key-tools.

sohailbhamani/audio-analyzer is the leanest practical one. It wraps Essentia and exposes a small, sane output: bpm, key, energy, has_vocals, plus bpm_confidence and key_confidence. That is a very clean tag surface if you want conservative DJ-facing metadata rather than a giant MIR science fair. It also explicitly lists Essentia and librosa as dependencies.  ￼

mg0024/beatlyze-analyzer is the richest tagging-oriented repo in your list. Its documented output includes bpm, bpm_confidence, key, scale, key_notation, key_confidence, energy, danceability, valence, loudness_lufs, mood_tags, genre_suggestions, duration_seconds, time_signature, and sections. It also offers a librosa-only “light” tier and an Essentia-backed “full” tier, which is useful if you want a fallback mode. This is the closest thing here to a modern tag schema rather than just a tool.  ￼

iammordaty/key-tools is not an extractor, but it is very good infrastructure. It converts among Camelot, Open Key, standard musical notation, Beatport notation, and the notation used by Essentia’s streaming extractor, and it supports harmonic-mixing transforms like perfect fifth, perfect fourth, whole step, and relative minor/major. So this is ideal for normalizing whatever key you get from Beatport, Essentia, or another analyzer into one canonical internal representation.  ￼

The others are much less useful as sources of file tags.

btuckerc/spotify-dj is basically an ordering tool for Spotify material. Its README says it suggests song order based on energy, BPM, key, and danceability, but that is playlist logic, not a file-tagging schema, and it is described as still in development.  ￼

Gaku52/spotify-playlist-analyzer is a web app around Spotify Web API features. It analyzes BPM, key, energy, danceability, filters tracks, and creates playlists, but again this is a UI/app layer over Spotify-derived features rather than a reusable local tagging model for your own library.  ￼

farmhutsoftwareteam/crates is interesting, but I would not treat it as a trustworthy source of canonical tags. It says it uses Claude at runtime to produce BPM, Camelot key, energy, and danceability for each track via a one-shot prompt. That may be handy for a macOS crate manager, but it is fundamentally LLM-inferred DJ metadata rather than deterministic audio analysis. I would not use that as system-of-record metadata.  ￼

deepc0py/MixScore is recommendation/scoring logic for VirtualDJ. It uses Camelot compatibility, BPM matching, energy flow, and era cohesion, and it reads a custom Grouping tag format like E3-G for energy/era. Useful idea, but not really an extraction source. It is more about how to consume tags than how to create them.  ￼

farmhutsoftwareteam/crates and MixScore do suggest a couple of tag conventions worth stealing, though: a normalized energy score and maybe an era bucket if you want DJ recommendation logic later. But those should be your own fields, not copied blindly from their app assumptions.  ￼

So if the real question is “what tags could be worth using from this whole batch?”, my answer would be:

Core canonical tags:
bpm
bpm_confidence
key
scale
key_notation
key_confidence
camelot_key
open_key

Performance / feel tags:
energy
danceability
valence
loudness_lufs
has_vocals

Semantic tags:
mood_tags
genre_suggestions

Structural tags:
duration_seconds
time_signature
sections

Derived DJ logic tags:
harmonic_neighbors
energy_bucket
era_bucket only if you define it clearly yourself

Those come mainly from beatlyze-analyzer, audio-analyzer, and key-tools, with MixScore contributing more to downstream recommendation logic than extraction.  ￼

My practical recommendation is pretty blunt:

Use beatlyze-analyzer as the broad schema reference.
Use audio-analyzer as the minimal fallback/reference for a smaller safe subset.
Use key-tools to normalize all key representations.
Ignore the Spotify projects for canonical file tags.
Treat crates as inspiration, not evidence.
Treat MixScore as a consumer of tags, not a producer of them.  ￼

One important caveat: beatlyze-analyzer declares AGPLv3 because of Essentia, and audio-analyzer is GPL-3.0, so license implications matter if you want to embed or redistribute code rather than just borrow ideas for your own schema.  ￼

If you want, the next useful step is a concrete tagslut-ready field dictionary with exact names, types, allowed ranges, and which source should populate each one.

Yes. Beatport should sit in the schema as a first-class upstream metadata source, not as an afterthought.

The right model is: Beatport provides authoritative catalog metadata for release and track identity fields, plus DJ-facing vendor metadata like BPM, key, genre, subgenre, ISRC, label, release, mix name, and track/release linkage. Essentia/librosa/Beatlyze provide analysis fields from the audio itself. key-tools normalizes key notation across vendors and analyzers. That separation keeps vendor facts and audio inference from contaminating each other.  ￼

So the schema should be split into five blocks.

First, Beatport source-of-truth catalog fields:

beatport_track_id
beatport_release_id
beatport_name
beatport_mix_name
beatport_artists
beatport_remixers
beatport_bpm
beatport_key_raw
beatport_isrc
beatport_genre
beatport_subgenre
beatport_label
beatport_catalog_number
beatport_upc
beatport_release_date
beatport_track_number
beatport_url
beatport_last_synced_at

These should be stored as raw vendor metadata exactly because the Beatport catalog tracks endpoint is the canonical upstream source for Beatport’s own track catalog data, while your analyzer stack is doing something different: estimating properties from the file.  ￼

Second, normalized cross-source canonical fields:

bpm
bpm_source
key_notation_canonical
key_camelot
key_open
key_source
isrc
genre_primary
genre_secondary
genre_source
release_label
release_catalog_number
release_upc
release_date

These are the fields the rest of tagslut should query. They should be derived from source-specific fields by precedence rules, not written directly by every importer. key-tools is what makes this sane for key handling because it explicitly supports Beatport musical notation, Essentia extractor notation, Camelot, Open Key, and standard musical notation.  ￼

Third, audio-analysis fields that should remain separate from Beatport vendor facts:

analysis_bpm
bpm_confidence
analysis_key_raw
key_confidence
energy
danceability
valence
loudness_lufs
has_vocals
mood_tags
genre_suggestions
time_signature
duration_seconds
sections
analysis_profile
analysis_version
analysis_timestamp

That’s the layer informed by Beatlyze-style analyzer output, Essentia models, and librosa features. Essentia’s published models cover genre, mood/theme, instrumentation, top tags, tonal/atonal, and related music-tagging tasks, while librosa is strongest as a feature-extraction layer for tempo and low-level descriptors rather than listener-facing semantic tags.  ￼

Fourth, raw low-level descriptor fields, which should never be mistaken for tags:

rms_mean
spectral_centroid_mean
spectral_bandwidth_mean
spectral_flatness_mean
tonnetz_mean
tempo_curve
onset_strength_mean

librosa explicitly documents tempo, tempogram, RMS, spectral centroid, spectral bandwidth, spectral flatness, and tonnetz as feature outputs, so these are useful as support data and QA inputs, not as canonical user-facing metadata.  ￼

Fifth, DJ helper fields derived from canonical fields:

energy_bucket
valence_bucket
danceability_bucket
harmonic_neighbors
dj_compatibility_key_set

Those are downstream convenience fields. They should be recomputable and disposable.

The precedence rules should be explicit.

For isrc, Beatport should usually win when present because that is catalog identity metadata, not something inferred from audio. For bpm, I would use: manual override > trusted Beatport BPM > audio analysis BPM. Beatport BPM is useful and practical, but analysis BPM should still be preserved separately because vendor BPM can differ from what your actual file analysis yields. For key, I would use: manual override > trusted Beatport key as vendor key > analyzer key, then normalize through key-tools into canonical notation plus Camelot/Open Key variants. For genre, store Beatport genre/subgenre separately from analysis-driven genre_suggestions; do not collapse them too early into one mushy field.  ￼

So the minimum Beatport-aware canonical mapping should look like this:

isrc := beatport_isrc unless manually overridden
release_label := beatport_label unless manually overridden
release_catalog_number := beatport_catalog_number unless manually overridden
release_upc := beatport_upc unless manually overridden
release_date := beatport_release_date unless manually overridden
genre_primary := normalized(beatport_genre) unless editorial override exists
genre_secondary := normalized(beatport_subgenre) when present
bpm := beatport_bpm or analysis_bpm depending on precedence policy
bpm_source := "beatport" | "analysis" | "manual"
key_source_raw := beatport_key_raw or analysis_key_raw
key_source := "beatport" | "analysis" | "manual"
key_notation_canonical := normalize(key_source_raw via key-tools)

That gives you clean provenance instead of silent overwrites.  ￼

The part I would strongly avoid is stuffing Beatport values directly into the same fields as analyzer outputs without source tracking. beatport_bpm and analysis_bpm are not the same kind of truth. Same for beatport_genre versus model-predicted genre_suggestions. Beatport is catalog/editorial metadata. Essentia/librosa-style tools are observational metadata from the file. Both are useful, but they answer different questions.  ￼

So yes: Beatport absolutely belongs in the schema, and it should upgrade the earlier dictionary. The core addition is not “more tags.” It is source-specific vendor fields plus provenance-aware canonical fields.

Revised must-have fields, with Beatport included, are:

beatport_track_id, beatport_release_id, beatport_bpm, beatport_key_raw, beatport_isrc, beatport_genre, beatport_subgenre, beatport_label, beatport_catalog_number, beatport_upc, beatport_release_date, analysis_bpm, bpm, bpm_source, analysis_key_raw, key_notation_canonical, key_camelot, key_open, key_source, energy, danceability, valence, loudness_lufs, has_vocals, mood_tags, genre_suggestions, genre_primary, genre_secondary, analysis_version, analysis_profile, analysis_timestamp.

That is the version I’d actually build.

The next correct step is the SQL schema with source tables and precedence logic baked in, not just a flat list of columns.

That worked.

The important bit is that tidal_isrc_data.csv is empty because your script did not write to that file. It wrote to playlist_isrcs.csv, which is why tidal_isrc_data.csv only contains the header row while playlist_isrcs.csv contains the 24 extracted tracks. Your code snippet shows with open('playlist_isrcs.csv', 'w', newline='', encoding='utf-8') ..., and Python’s csv.DictWriter writes exactly to the file object you open there.  ￼

So the result is:

tidal_isrc_data.csv → header only
playlist_isrcs.csv → the real output with 24 rows

Also, the TIDAL side looks consistent with the library behavior you used: tidalapi supports playlist access and iterating playlist tracks, so extracting track.name, track.artist.name, and track.isrc from playlist tracks is in line with the documented library surface.  ￼

If you want the output file to be tidal_isrc_data.csv, change just this line:

with open('tidal_isrc_data.csv', 'w', newline='', encoding='utf-8') as f:

Or, without rerunning anything, just rename the file in Terminal:

mv playlist_isrcs.csv tidal_isrc_data.csv

And for the record, the extracted CSV you showed is valid and includes these columns:

name,artist,isrc,id

That structure is exactly what DictWriter is meant to produce when the fieldnames match the dict keys you append to results.  ￼

Yes. The plan is now straightforward.

Phase 1 is source separation. Keep vendor metadata, extracted identifiers, and audio analysis in separate layers instead of collapsing them into one CSV or one set of tags. Beatport should be treated as catalog/editorial metadata for fields like track ID, release ID, BPM, key, ISRC, genre, subgenre, label, catalog number, UPC, and release date. TIDAL, in your current flow, is mainly giving you playlist membership plus track-level identifiers like ISRC and track ID. Audio analyzers then supply observational fields like BPM, key, energy, danceability, valence, loudness, vocals, moods, and genre suggestions.  ￼

Phase 2 is the canonical schema. Build one record per track with four grouped blocks: source_tidal_*, source_beatport_*, analysis_*, and canonical_*. The canonical layer should only contain fields the rest of tagslut will query: isrc, bpm, bpm_source, key_notation_canonical, key_camelot, key_open, key_source, genre_primary, genre_secondary, energy, danceability, valence, loudness_lufs, has_vocals, mood_tags, analysis_version, analysis_profile, and analysis_timestamp. That structure is justified because Beatport exposes catalog track metadata, Beatlyze exposes the richer analyzer surface, and key-tools exists specifically to normalize keys across notation systems.  ￼

Phase 3 is precedence rules, written down before any code. The clean order is: manual override first, then trusted vendor metadata, then analyzer output. So isrc should usually come from TIDAL or Beatport if present, not from inference. bpm should preserve both beatport_bpm and analysis_bpm, but canonical bpm should resolve by policy. key should preserve raw source keys and then normalize through key-tools into one canonical notation plus Camelot and Open Key forms. genre_primary and genre_secondary should come from normalized vendor/editorial values first, while model outputs should live in genre_suggestions unless explicitly promoted.  ￼

Phase 4 is fixing the TIDAL extraction step so it becomes reliable input instead of ad hoc output. The immediate issue is not TIDAL itself but file discipline: one script wrote only a header row to tidal_isrc_data.csv, while the later successful run wrote 24 rows to playlist_isrcs.csv. Python’s CSV writer writes to the exact file object you open, and opening with write mode replaces prior contents. So the extractor needs one fixed output path, one stable header, and one row per playlist item.  ￼

Use this as the stable extractor contract:

playlist_url, tidal_track_id, title, artist, isrc

Then enrich that file rather than regenerating different CSVs with different names. TIDAL’s playlist API surface supports iterating playlist tracks, which matches the working script behavior you showed.  ￼

Phase 5 is enrichment. For each TIDAL row, look up Beatport by ISRC first, then by normalized artist/title fallback only if ISRC fails. Beatport track metadata is the right place to populate beatport_track_id, beatport_release_id, beatport_bpm, beatport_key_raw, beatport_genre, beatport_subgenre, beatport_label, beatport_catalog_number, beatport_upc, and beatport_release_date.  ￼

Phase 6 is audio analysis. Once the identity row exists, run analysis on the actual local file, not on streaming metadata. The minimal safe analyzer set is BPM, BPM confidence, key, key confidence, energy, and vocals. The richer set adds danceability, valence, loudness LUFS, mood tags, genre suggestions, time signature, duration, and sections. Beatlyze documents the richer surface; audio-analyzer documents the smaller fallback; Essentia’s published models support broader genre, mood/theme, instrumentation, and voice-related tagging; librosa is useful mainly for low-level feature extraction rather than end-user semantic tags.  ￼

Phase 7 is key normalization. Never store only one human-readable key string. Store key_source_raw, key_source_notation, key_notation_canonical, key_camelot, and optionally key_open. key-tools explicitly supports notation conversion and harmonic-neighbor logic, so it should be the one translation layer instead of hand-rolled conversions all over the codebase.  ￼

Phase 8 is controlled vocabularies. Do not let every analyzer invent free-text labels. For moods, use a whitelist. For genres, keep raw suggestions in a list but map promoted canonical values to your own normalized taxonomy. Essentia publishes broad model families for mood/theme, instruments, top tags, and genre/style, which is useful for recall, but too loose to become direct system-of-record labels without normalization.  ￼

Phase 9 is implementation order. The correct order is:
	1.	freeze the CSV contract for the TIDAL extractor,
	2.	build the canonical row model,
	3.	add Beatport enrichment by ISRC,
	4.	add key normalization,
	5.	add audio analysis,
	6.	add tag normalization,
	7.	only then wire it into tagslut DB writes.

That order reduces the chance of mixing up vendor facts with analyzer guesses.

So the immediate concrete next actions are these:

First, standardize one extractor output file, for example tidal_playlist_seed.csv, and stop writing to multiple names.

Second, define one canonical table or dataframe schema with:
tidal_track_id, tidal_url, title, artist, isrc, beatport_track_id, beatport_release_id, beatport_bpm, beatport_key_raw, beatport_genre, beatport_subgenre, beatport_label, beatport_catalog_number, beatport_upc, beatport_release_date, analysis_bpm, bpm_confidence, analysis_key_raw, key_confidence, energy, danceability, valence, loudness_lufs, has_vocals, mood_tags, genre_suggestions, key_notation_canonical, key_camelot, key_open, bpm, bpm_source, key_source, genre_primary, genre_secondary.

Third, make the resolver deterministic:
ISRC match -> Beatport enrichment -> key normalization -> file analysis -> canonical resolution.

That is the plan I would follow. It is narrow enough to build cleanly and broad enough to cover the full pipeline.

If you want the next step, it should be the exact SQL table design and column types, not more concept work.


Yes.

This is exactly the kind of bounded repo task Codex is good at: reading the existing codebase, wiring a small end-to-end flow, editing files, and running validation/tests in an isolated environment or locally through the IDE/CLI. OpenAI’s current Codex docs describe it as a coding agent that can inspect a repo, edit files, and run commands, and the best-practices docs lean heavily toward giving it a clear scoped task with validation criteria.  ￼

And your scope is now clean enough to delegate: TIDAL is the intake source, Beatport is the enrichment source, and Beatport’s track catalog endpoint is the authoritative place for its own track metadata. The tidalapi docs/history also support the workflow you already proved: playlist handling plus ISRC-related track support.  ￼

The right move is not “ask Codex vaguely to wire this in.” The right move is to hand it a very strict implementation brief. Paste this to Codex as one task:

Wire in a TIDAL → Beatport enrichment pipeline for the current repo.

Objective
Implement a deterministic vendor-only metadata flow with no audio analysis and no third-party metadata sources beyond TIDAL and Beatport.

Scope
1. Add a TIDAL intake step that exports one stable seed CSV from a playlist URL.
2. Add a Beatport enrichment step that resolves rows primarily by ISRC.
3. Produce one final merged CSV.
4. Keep source fields and canonical fields separate.
5. Do not add Essentia, librosa, or any MIR/analyzer dependencies.

Required row model
tidal_playlist_id
tidal_track_id
tidal_url
title
artist
isrc
beatport_track_id
beatport_release_id
beatport_url
beatport_bpm
beatport_key
beatport_genre
beatport_subgenre
beatport_label
beatport_catalog_number
beatport_upc
beatport_release_date
match_method
match_confidence
last_synced_at

Rules
- TIDAL is intake only.
- Beatport is enrichment only.
- ISRC is the primary join key.
- Title/artist fallback is allowed only if ISRC lookup fails.
- If fallback is used, mark match_method=title_artist_fallback and lower confidence.
- If no Beatport match exists, preserve the TIDAL row with Beatport fields null.
- Do not overwrite source-specific fields with canonicalized guesses.
- Keep implementation small, explicit, and auditable.

Required outputs
1. One command to export TIDAL seed CSV from a playlist URL.
2. One command to enrich that CSV from Beatport.
3. One final merged CSV, preferably named tidal_beatport_enriched.csv.
4. README or docs section explaining:
   - exact commands
   - required env vars / auth
   - column meanings
   - match precedence
   - known failure modes

Implementation constraints
- Reuse existing repo patterns where possible.
- Do not refactor unrelated parts of the repo.
- Keep diffs narrow.
- Add logging for row counts, matched rows, unmatched rows, and fallback matches.
- Add at least one happy-path test and one no-match test.
- If networked tests are inappropriate, isolate logic and mock vendor responses.

Deliverable format
- Make the code changes.
- Show the file list changed.
- Explain the command-line interface added.
- Explain any assumptions.
- Do not claim behavior that was not verified.

Then add this short rider underneath it:

Important:
Use the existing repo style. Prefer additive changes over architectural rewrites. Keep the work split into small reviewable commits if possible. Preserve provenance. Source-specific vendor fields must remain separate from any future canonical fields.

That is the version worth delegating.

One practical note: if you run Codex from the IDE extension or CLI, it can work directly in the repo and run commands there; the current docs also say the VS Code extension supports side-by-side work and delegating tasks to Codex Cloud. For most tasks, OpenAI currently recommends gpt-5.4 as the default starting model in Codex.  ￼

My recommendation is: yes, hand this to Codex now, but only with that tight brief. The implementation problem is clear. The main risk now is prompt sloppiness, not technical ambiguity.
