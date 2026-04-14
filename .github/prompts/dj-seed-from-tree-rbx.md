# Codex prompt — tagslut feature: build DJ seed from `tree_rbx.js`

Work from repo root.

Read first:
- `AGENT.md`
- `PROJECT_DIRECTIVES.md`
- `docs/CORE_MODEL.md`
- `docs/DB_V3_SCHEMA.md`
- `tree_rbx.js`

Do not redesign the system. Implement the smallest coherent patch set that satisfies this spec.

## Why this feature exists

`tools/centralize_lossy_pool` already solved **cleanliness** by building a broad clean lossy universe at:

`/Volumes/MUSIC/MP3_LIBRARY_CLEAN`

That root is **not** DJ-only. It is the clean candidate universe, not the approved DJ pool.

The missing layer is **relevance reconstruction** from prior approved Rekordbox material. The historical seed signal now lives in:

`/Users/georgeskhawam/Projects/tagslut/tree_rbx.js`

Treat that file as a real operator input. It is a large exported JavaScript object rooted at a Rekordbox/USB contents tree. Its files represent prior DJ-approved material. It also contains junk entries such as AppleDouble `._*`, which must be ignored.

Correct model:
- `tools/centralize_lossy_pool` solved cleanliness
- `tree_rbx.js` represents prior approved DJ material
- `/Volumes/MUSIC/MP3_LIBRARY_CLEAN` is the clean candidate universe
- this task reconstructs a practical starting DJ seed from that prior approved material

This tool is a **matcher**, not another pool cleaner.

## Task

Add a new non-interactive Python CLI script:

`tools/build_dj_seed_from_tree_rbx`

This utility must:

1. parse `tree_rbx.js` into ordered historical seed rows
2. optionally inspect seed files at their original paths when those paths still exist
3. scan `/Volumes/MUSIC/MP3_LIBRARY_CLEAN`
4. match seed rows onto the clean pool by strict confidence tiers
5. emit reviewable outputs:
   - matched DJ seed playlist
   - missing report
   - ambiguous report
   - match manifest

This tool is filesystem-only and report-oriented. Do not force it into the DB-backed DJ validation path in this task.

## Success criteria

The implementation is correct when all of the following are true:

- `tree_rbx.js` is parsed without introducing a JS runtime dependency
- historical seed rows preserve the original traversal order from the exported tree
- AppleDouble junk and unsupported files are ignored
- pool candidates are matched conservatively and deterministically
- outputs are written only under an operator-specified output directory
- no DB writes, retagging, transcoding, moves, or deletes occur
- the final M3U is a useful DJ seed, not a broad export of the entire clean pool

## Scope and safety model

This is an external operator utility, not a canonical-identity writer.

Do not:
- write to any DB
- retag files
- transcode files
- move or delete files
- mutate `MP3_LIBRARY_CLEAN`
- treat path-based inference as canonical truth
- add a new CLI group command in this task

It is acceptable to use filename/path ancestry as a **matching aid** because the input itself is a historical Rekordbox export tree, but confidence must be explicit and conservative.

## CLI contract

Required:
- `--tree-js /Users/georgeskhawam/Projects/tagslut/tree_rbx.js`
- `--pool-root /Volumes/MUSIC/MP3_LIBRARY_CLEAN`
- `--output-dir <dir>`

Optional but implemented and documented:
- `--m3u-name dj_seed_from_tree_rbx.m3u`
- `--missing-name dj_seed_missing.csv`
- `--ambiguous-name dj_seed_ambiguous.csv`
- `--manifest-name dj_seed_match_manifest.jsonl`
- `--limit <n>` for smoke tests
- `--path-context-depth 3`
- `--duration-tolerance-seconds 2`

Rules:
- default mode is normal read-only execution
- output files may be overwritten inside `--output-dir`
- `--limit` applies after parsing + ignore filtering, preserving original seed order
- use normal `argparse` help and error behavior
- fail clearly if `--tree-js` or `--pool-root` does not exist

## Output goals

Produce at least:
- `dj_seed_from_tree_rbx.m3u`
- `dj_seed_missing.csv`
- `dj_seed_ambiguous.csv`
- `dj_seed_match_manifest.jsonl`

All outputs must go under `--output-dir`. Do not write repo artifact files by default.

## Input parsing requirements

### `tree_rbx.js`

The file is a JavaScript module that begins with:

`export default { ... }`

Implementation requirements:
- do not add a JS runtime dependency
- do not evaluate arbitrary JavaScript
- strip the leading `export default`
- strip one optional trailing semicolon
- decode the remaining payload as JSON when valid
- if tiny normalization is required for safe parsing, keep it minimal and local to this script only

Traverse recursively and emit one seed row per file node.

Preserve the original order as a depth-first traversal following `children` array order exactly as stored in the file.

Ignore:
- directory nodes as final outputs
- hidden junk such as `._*`
- unsupported file types
- zero-length junk files if encountered

Treat `.mp3` and `.m4a` as in-scope by default.

For each seed file row, collect at least:
- `seed_path`
- `seed_name`
- `seed_ext`
- `seed_size`
- `seed_parent_dirs` as ordered list
- `seed_context_path` as a stable joined ancestry string
- `seed_source_mode`:
  - `seed_file_inspected`
  - `seed_path_only`
- parsed hints, using actual file tags first when the seed file still exists:
  - `artist`
  - `title`
  - `album`
  - `album_artist`
  - `track_number`
  - `year`
  - `isrc`
  - `duration_seconds`
- normalized basename and token fields used for matching

Important:
- if a seed file path still exists on disk, inspect it with the same lightweight media/tag helpers used for pool candidates
- if a seed file path does not exist, do not fail the run; fall back to filename/path-derived hints only

### candidate pool

Scan `/Volumes/MUSIC/MP3_LIBRARY_CLEAN` recursively for regular `.mp3` and `.m4a` files.

For each candidate, collect:
- `path`
- `extension`
- `size`
- `duration_seconds` if cheaply available
- tags when available:
  - `artist`
  - `title`
  - `album`
  - `album_artist`
  - `isrc`
  - `track_number`
  - `label`
- normalized filename/path tokens
- parent-dir context up to the configured `--path-context-depth`

Use existing repo inspection patterns for Mutagen and `ffprobe` where appropriate. Do not add new dependencies.

## Normalization

Use one shared normalization helper everywhere for seed and candidate comparisons.

Normalize strings by:
- Unicode normalize
- casefold
- trim
- collapse whitespace
- replace `_`, `-`, `/`, and repeated punctuation with spaces
- optionally normalize `&` to `and`
- strip surrounding punctuation

The same helper must be used for:
- artist
- title
- album
- basename/path token comparisons
- tie-break reasoning

Do not add fuzzy edit-distance or ML-style ranking.

## Matching strategy

Apply matching in strict tier order. Once a seed row gets an unambiguous higher-confidence match, do not continue to weaker tiers.

If a seed row lacks the minimum fields required for a tier, skip that tier and continue only if the next tier still has enough deterministic context.

### Tier 1 — ISRC match

Match when:
- seed has a normalized ISRC
- candidate has the same normalized ISRC
- if duration exists on both sides, the duration delta is within tolerance

Confidence:
- `isrc_exact`

### Tier 2 — exact normalized artist + title

Match when:
- seed has normalized artist and title
- candidate normalized artist equals seed normalized artist
- candidate normalized title equals seed normalized title

Tightening:
- if duration exists on both sides, prefer candidates within tolerance
- if album exists on both sides and matches exactly, keep that as supporting evidence but do not rename the tier

Confidence:
- `artist_title_exact`

### Tier 3 — artist + title + context

Use only when tier 2 does not produce a clean result.

Match aids may include:
- normalized album
- immediate parent directory names
- limited ancestry from `tree_rbx.js`
- candidate parent dirs under `MP3_LIBRARY_CLEAN`
- normalized basename similarity only as a supporting signal, not as a standalone tier

Confidence:
- `artist_title_context`

### Forbidden matching

Do not add looser heuristics in this task.
Do not do:
- token-set guessing
- edit-distance scoring
- phonetic matching
- ML ranking
- broad “looks close enough” auto-picks

If deterministic evidence is weak, classify as `missing` or `ambiguous`.

## Match outcomes

Every seed row must resolve to exactly one of:
- `matched`
- `missing`
- `ambiguous`
- `ignored`

Definitions:
- `matched`: exactly one candidate chosen at the highest applicable tier
- `missing`: no acceptable candidate found
- `ambiguous`: more than one plausible candidate remains at the best tier, or the result is not safe to auto-pick
- `ignored`: intentionally skipped seed row, such as AppleDouble or unsupported extension

## Deterministic tie-breaks

If multiple candidates survive inside the same tier and exact equality still holds, apply this order:

1. candidate with ISRC present
2. candidate with more complete metadata among:
   - artist
   - title
   - album
   - track number
3. candidate with duration closest to seed, if duration exists
4. lexical sort of full candidate path

Safety rule:
- if the result still feels semantically unsafe after tie-breaks, classify as `ambiguous`
- do not over-resolve just to increase match count

## Output requirements

### 1. M3U playlist

Write `dj_seed_from_tree_rbx.m3u` containing matched candidate paths only.

Rules:
- emit UTF-8
- begin with `#EXTM3U`
- use absolute candidate paths
- preserve original seed traversal order
- do not include `missing`, `ambiguous`, or `ignored` rows

### 2. Missing CSV

Write `dj_seed_missing.csv` with at least:
- `seed_path`
- `seed_name`
- `seed_context_path`
- `seed_source_mode`
- `seed_artist`
- `seed_title`
- `seed_album`
- `seed_isrc`
- `best_tier_attempted`
- `note`

### 3. Ambiguous CSV

Write `dj_seed_ambiguous.csv` with at least:
- `seed_path`
- `seed_name`
- `seed_context_path`
- `seed_source_mode`
- `candidate_count`
- `best_tier_reached`
- `candidate_paths_json`
- `note`

Store candidate paths as a JSON array string in one CSV field. Do not invent a custom delimiter.

### 4. Manifest JSONL

Write one row per seed file, including at least:
- `outcome`
- `best_tier_reached`
- all important seed fields
- `seed_source_mode`
- `chosen_candidate_path` if matched
- `chosen_confidence`
- `candidate_summary` if ambiguous
- `ignore_reason` if ignored

### 5. Summary on stdout

Print a short final summary:
- total seed rows
- matched
- missing
- ambiguous
- ignored
- counts by match tier

## Tree context handling

Preserve enough ancestry from `tree_rbx.js` that later review can answer:
- which folder lineage the seed came from
- whether the seed looked album-like, artist-like, or crate-like
- whether ambiguity may be resolvable by local context

Do not throw away tree context during parsing.

## Tests

Add targeted tests only.

Create:
- `tests/tools/test_build_dj_seed_from_tree_rbx.py`

Cover at least:
- parser handles `export default { ... }`
- optional trailing semicolon is handled
- recursive traversal preserves file order
- `._*` junk rows are ignored
- seed file inspection is used when the source path exists
- path-only fallback works when the source path does not exist
- tier 1 ISRC match
- tier 2 exact normalized artist/title match
- tier 3 context-assisted match
- missing row emitted when no candidate exists
- ambiguous row emitted when multiple plausible candidates remain
- M3U preserves seed traversal order
- CSV outputs contain required columns
- no writes happen outside output dir
- no pool files are modified

Use fixture temp trees and small synthetic `tree_rbx.js` samples only.

## Implementation hints

- Keep parsing, inspection, matching, and reporting in separate pure helpers where possible
- Build pool indexes once, then reuse them across seed rows
- Reuse the repo’s existing Mutagen/`ffprobe` inspection style rather than inventing a new stack
- Keep the script standalone
- Do not merge with `tagslut dj validate`
- Do not widen scope into DB-backed playlist/admission creation yet

## Constraints

- no new Python dependencies unless absolutely necessary and documented
- no DB writes
- no filesystem mutations outside the output directory
- no full test suite
- keep implementation narrow and operator-focused

## Deliverables

Return:
1. exact files changed
2. tests run and results
3. output file formats
4. match tier definitions as implemented
5. remaining manual-review edge cases
