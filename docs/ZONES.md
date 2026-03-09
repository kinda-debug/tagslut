<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

# Zones

## Purpose

Zones describe asset placement and trust. They are not the same thing as v3 identity lifecycle status.

Use this distinction:

- `zone`: where a file lives and how move/promotion logic should treat it
- `identity_status`: whether a canonical identity is `active`, `orphan`, or `archived`

## Active Zone Vocabulary

The repo still uses these placement-oriented zones:

- `accepted`: canonical library content
- `archive`: retained long-term but not necessarily the primary playable copy
- `staging`: incoming or not-yet-promoted material
- `suspect`: lower-trust files, collisions, or files needing review
- `quarantine`: isolated risky content

Legacy compatibility values may still appear in old tables or scripts, but new guidance should use the active zone set above.

## Work Roots vs Zones

The operator work roots are related but not identical:

- `FIX_ROOT`: salvageable metadata/tag issues
- `QUARANTINE_ROOT`: risky files needing manual review
- `DISCARD_ROOT`: deterministic duplicates such as `dest_exists`

These are workflow buckets. When such files are written back into DB-facing move flows, they usually map to `suspect` or `quarantine` depending on the path and action.

## Core Rules

1. Zones are about asset placement, not canonical identity truth.
2. Promotion should move toward `accepted`, not away from it.
3. Quarantine should remain reversible and auditable.
4. Do not treat a zone label as a substitute for `preferred_asset` or `identity_status`.
5. Do not infer canonical identity from zone or path shape.

## Configuration

Zone resolution is configured through YAML or TOML inputs loaded by the zone manager.

Preferred pattern:

```bash
export TAGSLUT_ZONES_CONFIG=~/.config/tagslut/zones.yaml
```

Typical YAML keys:

- `defaults.zone`
- `roots.base`
- `zones`
- `path_priorities`

## Practical Interpretation

### Accepted

High-trust library content. This is where the canonical playable asset should end up after successful promotion.

### Staging

Incoming content that has not yet completed the required checks and promotion logic.

### Suspect

Files that should not silently re-enter the accepted library without review.

### Quarantine

Isolation area for risky content. Treat this as a review boundary, not an archive strategy.

### Archive

Retained storage that is intentionally outside the primary accepted-library path.

## Diagnostics

Helpful read-only commands:

- `tagslut show-zone --path /path/to/file` (hidden/policy-only helper)
- `tagslut explain-keeper --db <db> --group-id <id>` (hidden/policy-only helper)

Use them for debugging, not as the primary operator surface.
