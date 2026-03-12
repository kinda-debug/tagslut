<!-- Status: Active document. Synced 2026-03-12 after DJ role/profile documentation refresh. Historical or superseded material belongs in docs/archive/. -->

# DJ Pool Contract (v3)

## Purpose

The DJ pool is a derived output generated from `MASTER_LIBRARY` and the v3 identity database.

It provides a deterministic set of tracks suitable for DJ environments (Rekordbox, Lexicon, etc.) without modifying the master library.

The DJ pool is downstream-only and must never become a source of truth.

## Design Principles

1. Read-only upstream
- `MASTER_LIBRARY` and the v3 database are never modified by DJ pool operations.
2. Deterministic builds
- The same inputs must produce the same pool.
3. Plan-first execution
- Pool creation always supports a planning phase before execution.
4. Preferred asset priority
- When multiple assets exist for an identity, the preferred asset is used.
5. Auditable output
- Pool builds must produce manifests and receipts.

## Operator Workflow

Typical DJ workflow:

```
MASTER_LIBRARY
      |
      v
v3 identity index
      |
      v
DJ candidate export
      |
      v
DJ profile curation
      |
      v
DJ-ready export
      |
      v
DJ pool builder
      |
      v
DJ software (Rekordbox / Lexicon)
```

## Input Sources

The DJ pool builder consumes:

### v3 database

`music_v3.db`

Provides:
- track identities
- preferred asset mapping
- metadata fields
- DJ profile data (if present)

### Preferred asset table

Tracks selected for the DJ pool must resolve to a preferred asset.

## Pool Builder (B2)

Primary operator entrypoint:

`poetry run tagslut dj pool-wizard`

Live workflow implementation:

`tagslut/exec/dj_pool_wizard.py`

Lower-level builder:

`scripts/dj/build_pool_v3.py`

Responsibilities:
- resolve preferred assets
- apply optional DJ profile filters
- generate pool layout
- produce build manifest
- optionally copy or transcode assets

## Execution Model

### Plan Mode (default)

Produces:

`manifest.csv`

Describes:
- source path
- destination path
- identity_id
- preferred_asset_id
- planned action

No files are modified.

Example:

```bash
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_LIBRARY" \
  --out-root /tmp/dj_pool_runs \
  --non-interactive \
  --profile /path/to/profile.json
```

### Execute Mode

Copies or transcodes files into the pool.

Execution must be explicit.

Example:

```bash
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_LIBRARY" \
  --out-root /tmp/dj_pool_runs \
  --execute \
  --non-interactive \
  --profile /path/to/profile.json
```

Make targets may wrap this behavior.

## Pool Profile Reference

The JSON passed via `--profile /path/to/profile.json` is part of the operator-facing pool contract.

For the export-layer profile in `tagslut/dj/export.py`, `pool_profile_from_dict()` honors the fields below. Higher-level workflows such as `tagslut dj pool-wizard` may carry additional workflow keys, but those are outside this `PoolProfile` subset.

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `pool_name` | string | `""` | Optional label carried on `PoolProfile`. `tagslut dj pool-wizard` expects this in non-interactive profiles. |
| `layout` | string | `"flat"` | Supported values: `flat`, `by_role`. `by_role` writes into role subdirectories and routes missing or invalid `dj_set_role` values to `_unassigned/`. |
| `filename_template` | string | `"{artist} - {title}.mp3"` | Format string with `{artist}` and `{title}` placeholders. If rendering fails or produces an empty name, export falls back to the normal output filename. |
| `bpm_min` | integer or `null` | `null` | Optional minimum BPM filter applied before export. |
| `bpm_max` | integer or `null` | `null` | Optional maximum BPM filter applied before export. |
| `only_roles` | array of strings or `null` | `null` | Optional allowlist of `files.dj_set_role` values: `groove`, `prime`, `bridge`, `club`. Tracks outside the set are excluded before output paths are assigned. |
| `create_playlist` | boolean | `false` | When `true` and `layout` is `by_role`, write per-role M3U files at the pool root such as `10_GROOVE.m3u` and `20_PRIME.m3u`. |
| `pool_overwrite_policy` | string | `"always"` | Supported values: `always`, `skip`. Other values fail validation. |

Reference JSON:

```json
{
  "pool_name": "gig_2026_03_13",
  "layout": "by_role",
  "filename_template": "{artist} - {title}.mp3",
  "bpm_min": 98,
  "bpm_max": 128,
  "only_roles": ["groove", "prime", "bridge", "club"],
  "create_playlist": true,
  "pool_overwrite_policy": "always"
}
```

## Upstream Tag Preparation

Two upstream paths can feed DJ MP3 creation:

1. `tools/get --dj` / `tools/get-intake --dj` for wrapper-driven downstream output after promote
2. `tagslut intake process-root --phases dj` for staged-root DJ preparation

The staged-root DJ phase can enrich FLAC BPM/key from v3 identity data and use Essentia as fallback before MP3 transcode. Use `--phases dj --dry-run` to preview that work.

## Output Layout

Pool output directory example:

```
DJ_POOL/
    by_role/
    by_genre/
    flat/
```

Actual layout depends on builder configuration.

Each output file must be uniquely identifiable and deterministic.

Recommended suffix:

`<artist> - <title> [identity_id].mp3`

## Safety Rules

1. The DJ pool builder must never modify `MASTER_LIBRARY`.
2. Pool outputs must live outside the `MASTER_LIBRARY` path.
3. Execution must be explicit.
4. Missing preferred assets must cause a failure unless explicitly overridden.

## Non-Goals

The DJ pool builder does not:
- curate music taste
- modify metadata
- replace DJ profile editing
- replace Rekordbox/Lexicon library management

It only produces a deterministic file set.

## Related Documentation

Primary workflow references:
- `docs/DJ_WORKFLOW.md`
- `docs/OPERATIONS.md`
- `AGENT.md`
- `.claude/AGENT.md`
