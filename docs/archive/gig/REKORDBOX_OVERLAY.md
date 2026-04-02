<!-- Status: Active document. -->

# Rekordbox Overlay

## What it does
`tagslut gig apply-rekordbox-overlay` reads an existing Rekordbox XML export, resolves playlist membership, and writes track-level `Rating` and `Colour` values on `COLLECTION/TRACK` nodes.

It does not edit:
- playlist names
- `Comments`
- the repo's canonical metadata model

This is an export-time live-use overlay for faster filtering and sorting during a gig.

## Why it exists
Comments already carry useful user data such as energy and mood tags. Overloading `Comments` or playlist names with live-state labels makes browsing harder, not easier.

Rekordbox `Rating` and `Colour` are better suited for fast in-booth decisions:
- `Rating`: set pressure / intensity
- `Colour`: role / lane

## Command
```bash
poetry run tagslut gig apply-rekordbox-overlay \
  --input-xml artifacts/tmp/pool.xml \
  --output-xml artifacts/tmp/pool.overlay.xml \
  --overlay-config config/gig_overlay_rules.yaml \
  --audit-csv artifacts/tmp/pool.overlay_audit.csv \
  --audit-json artifacts/tmp/pool.overlay_audit.json
```

## Config
Default config path: `config/gig_overlay_rules.yaml`

The config supports:
- `playlist_state_hints`: curated playlist-to-state mapping
- `state_defaults`: configurable state-to-rating and state-to-colour mapping
- `manual_overrides`: track-level forced decisions
- `recognition_*`, `never_peak_*`, `utility_only_titles`: curated exceptions
- `heuristics`: export-time safety settings

Manual override matching supports:
- `track_id`
- `location`
- `artist` + `title`
- `canonical_identity`

First matching override wins.

## Decision order
The overlay uses this order:
1. Manual override fields
2. `disable_auto`
3. Preserve existing overlay, if enabled
4. Curated exception lists
5. Strongest playlist hint by configured state priority
6. Heuristics from comment energy, BPM, genre, and title markers
7. Leave the track unchanged

Heuristics are intentionally conservative. A single weak field such as BPM or genre does not assign a state by itself.

## Review before live use
Always review the audit CSV before trusting a new ruleset.

The audit reports changed tracks with:
- old and new `Rating`
- old and new `Colour`
- matched playlists
- parsed comment energy
- BPM
- genre
- decision reason
- override source

## What not to use it for
Do not use this overlay to:
- rewrite playlist names
- encode live labels into `Comments`
- replace manual DJ judgment
- build a generalized ontology project

## Refining over time
Start with playlist hints and a small set of manual overrides.

After each gig:
1. Review the audit CSV and what felt wrong in Rekordbox.
2. Add or tighten manual overrides first.
3. Add curated exception lists second.
4. Adjust state mappings last.

That keeps the system human-led and predictable.
