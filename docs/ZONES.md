# Zones (V2)

Zones are first-class trust/lifecycle stages. They are **not** just labels. Zones drive keeper selection, safety rules, and the staged workflow. Zones are stored in the DB (`files.zone`) and are always auditable.

## Zone Definitions

- **accepted**: Canonical library content. Highest trust.
- **archive**: Long-term storage. High trust but not necessarily canonical.
- **staging**: Incoming/working area. Medium trust.
- **suspect**: Duplicates, corrupt, or unverified files. Low trust.
- **quarantine**: Duplicates copied into a safety net. Lowest trust.
- **inbox / rejected**: Optional legacy zones (supported for compatibility).

## Core Rules

- **No deletion**: Code never deletes source files. Quarantine is copy-only.
- **Reversible**: All actions must be auditable in DB/logs.
- **Zones remain central**: Keeper selection always considers zones unless no library zones exist.

## Zone Configuration

Zones are configured via YAML (preferred) or TOML (legacy). YAML allows explicit priorities and path-level overrides.

### YAML (preferred)

Set `DEDUPE_ZONES_CONFIG` to a YAML file:

```
export DEDUPE_ZONES_CONFIG=~/.config/dedupe/zones.yaml
```

The YAML structure uses these top-level keys:

- `defaults.zone`: fallback zone (usually `suspect`)
- `roots.base`: optional base for relative paths
- `zones`: mapping of zone → {paths, priority, description}
- `path_priorities`: optional path-level tie-breakers

See `config.example.yaml` for three scenarios.

### TOML (legacy)

The existing `config.toml` supports `library.root` and `library.zones`. When present, ZoneManager loads from TOML but uses default priorities.

## Scenarios

### Scenario A — Single main library

- One canonical `accepted` root.
- `staging`, `suspect`, and `quarantine` live under a work area.
- `path_priorities` can nudge tie-breaks within the accepted library.

### Scenario B — Multiple peer libraries (no single main)

- Multiple `accepted` roots with the **same base priority**.
- `path_priorities` break ties between peers if needed.
- Keeper selection still prefers accepted over staging/suspect/quarantine.

### Scenario C — No main library

- No `accepted` zone at all.
- Keeper selection ignores zone priority and ranks purely by quality, size, and hygiene.
- Best for transient/staging-only collections.

## Keeper Selection Order

1. **Zone priority** (from ZoneManager)
2. **Path priority** (within zone, if configured)
3. **Audio quality** (sample rate, bit depth, bitrate, integrity)
4. **File size** (larger tends to be more complete)
5. **Path hygiene** (shorter and cleaner paths win ties)

If **no accepted zone** exists, step 1 is skipped automatically.

## CLI Helpers

- `dedupe show-zone --path /path/to/file`
- `dedupe explain-keeper --db /path/to/music.db --group-id <checksum>`

Both commands are safe, read-only diagnostics.
