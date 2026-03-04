# tagslut Architecture (v3)

## System Overview

The system manages a large canonical FLAC archive and produces deterministic downstream artifacts for DJ workflows.
The architecture separates source data, identity modeling, curation, and output generation.

```
        MASTER AUDIO LIBRARY
        (canonical source)
               |
               |
               v
      +---------------------+
      |  FLAC Library       |
      |  (filesystem)       |
      +---------------------+
               |
               | intake / indexing
               v
      +---------------------+
      |  v3 Identity Index  |
      |  music_v3.db        |
      |                     |
      |  track_identity     |
      |  asset_file         |
      |  preferred_asset    |
      |  identity_status    |
      +---------------------+
               |
               |
               | read-only export
               v
      +---------------------+
      |  DJ Candidates      |
      |  export layer       |
      +---------------------+
               |
               | operator curation
               v
      +---------------------+
      |  DJ Profile Layer   |
      |  dj_track_profile   |
      |                     |
      |  rating             |
      |  energy             |
      |  set_role           |
      |  tags               |
      +---------------------+
               |
               | filtered export
               v
      +---------------------+
      |  DJ Ready Export    |
      |                     |
      | curated identities  |
      +---------------------+
               |
               | deterministic build
               v
      +---------------------+
      |  DJ Pool Builder    |
      |  build_pool_v3.py   |
      |                     |
      | plan -> execute     |
      +---------------------+
               |
               |
               v
      +---------------------+
      |  DJ Pool            |
      |                     |
      | MP3 / AIFF files    |
      | stable filenames    |
      +---------------------+
               |
               v
      +---------------------+
      |  DJ Software        |
      |                     |
      | Rekordbox           |
      | Lexicon             |
      +---------------------+
```

## Layer Responsibilities

### 1. FLAC Library

The FLAC library is the canonical audio source.

Properties:
- lossless
- never modified by DJ workflows
- filesystem-based

All derived artifacts originate from this layer.

### 2. Identity Index (v3 database)

File:
- `music_v3.db`

This layer creates a stable identity graph for tracks.

Key tables:
- `track_identity`
- `asset_file`
- `preferred_asset`
- `identity_status`

Responsibilities:
- deduplicate tracks
- track multiple assets per identity
- select preferred assets
- manage identity lifecycle

This layer is the core metadata model.

### 3. DJ Candidates Export

Read-only export from the identity index.

Purpose:
- expose potential DJ tracks
- filter by BPM, duration, genre, etc.

Output example:
- `dj_candidates.csv`

No modification of source data occurs.

### 4. DJ Profile Layer (B1)

Table:
- `dj_track_profile`

Adds human curation signals to identities.

Typical fields:
- `rating`
- `energy`
- `set_role`
- `tags`
- `last_played_at`
- `notes`

This layer represents DJ taste and context, not raw metadata.

### 5. DJ Ready Export

Filtered export based on:
- DJ profile
- preferred assets
- identity status

Output is a curated track list suitable for building a DJ pool.

### 6. DJ Pool Builder (B2)

Implementation:
- `scripts/dj/build_pool_v3.py`

Responsibilities:
- resolve preferred assets
- build deterministic filenames
- create pool directory layout
- generate build manifest
- copy or transcode audio assets

Execution model:
- plan (default)
- execute (explicit)

Example:

```
python build_pool_v3.py --db music_v3.db --out-dir DJ_POOL
```

### 7. DJ Pool

Example output structure:

```
DJ_POOL/
    by_role/
    by_genre/
    flat/
```

Files use stable identity-anchored filenames:

`Artist - Title (Mix) [identity_id].mp3`

Benefits:
- deterministic builds
- stable Rekordbox track identity
- cue points survive rebuilds

### 8. DJ Software

Consumers of the DJ pool:
- Rekordbox
- Lexicon

These tools manage:
- cue points
- beat grids
- playlists

They must never become the canonical source of metadata.

## Key Design Principles

### Determinism

Given the same inputs, the system produces the same outputs.

### Source-of-Truth Separation

The FLAC library remains authoritative.
Derived layers must never overwrite source data.

### Plan-First Execution

Destructive actions are never implicit.

`plan -> execute`

### Identity Stability

Track identities remain stable across rebuilds.

## Identity Lifecycle State Machine

### Purpose

The identity lifecycle defines how tracks progress from ingestion into the FLAC archive to active use in DJ workflows.

It ensures:
- deterministic library management
- auditable promotion decisions
- safe archival of unused tracks
- stable DJ pools

This lifecycle operates at the identity level, not the file level.

### Identity States

Each track identity belongs to one lifecycle state.

- candidate
- curated
- active
- archived

These states represent DJ usefulness, not file validity.

### State Definitions

#### Candidate

Newly indexed track identities.

Typical characteristics:
- created during intake or indexing
- may lack full metadata
- may lack DJ evaluation

Candidate identities are not included in DJ pools by default.

#### Curated

Tracks reviewed by the operator.

Signals:
- DJ profile exists
- tags or rating assigned
- metadata validated

Curated tracks are eligible for DJ exports.

#### Active

Tracks actively used in DJ sets.

Typical signals:
- high rating
- recent play history
- assigned set roles

Active tracks represent the core DJ rotation.

#### Archived

Tracks retained in the library but removed from active DJ use.

Examples:
- outdated genres
- duplicate stylistic tracks
- historical content

Archived tracks remain searchable but are excluded from DJ exports.

### Lifecycle Flow

```
candidate
    |
    v
curated
    |
    v
active
    |
    v
archived
```

Transitions can also move backward if needed (for example: active -> curated).

### State Transitions

#### Candidate -> Curated

Triggered by:
- DJ profile creation
- metadata cleanup
- tagging or rating

#### Curated -> Active

Triggered by:
- high rating
- set role assignment
- repeated DJ usage

#### Active -> Archived

Triggered by:
- long-term inactivity
- stylistic retirement
- explicit operator decision

### Example Query Logic

Exclude archived tracks when exporting DJ candidates.

Example rule:
- identity_status != archived

DJ pool builder should typically filter:
- identity_status IN (curated, active)

### Integration With Existing Tables

Relevant tables:
- track_identity
- asset_file
- preferred_asset
- identity_status
- dj_track_profile

Lifecycle state should be stored in:
- identity_status

Example values:
- candidate
- curated
- active
- archived

### DJ Workflow Integration

The lifecycle gates DJ exports.

```
candidate
    |
    v
curated
    |
    v
active
```

Only curated or active tracks are exported to the DJ-ready layer.

The DJ pool builder typically operates on:
- active

With optional inclusion of curated tracks.

### Benefits

This lifecycle provides:
- deterministic library curation
- safe long-term archival
- stable DJ pool generation
- scalable management for very large libraries

It also enables automated audits such as:
- inactive track detection
- rotation analysis
- playlist health checks

### Future Extensions

Possible future additions:
- review
- quarantined
- deprecated

Optional metrics:
- play frequency
- recency scoring
- automated rotation ranking

These are optional and should only be introduced if needed.

## Why This Architecture Works

This design turns a DJ library into a reproducible build artifact.
Instead of manually curating folders, the workflow becomes:

`metadata -> curation -> deterministic build`

This enables:
- large-scale libraries (20k+ tracks)
- reproducible DJ environments
- automated audits and recovery
