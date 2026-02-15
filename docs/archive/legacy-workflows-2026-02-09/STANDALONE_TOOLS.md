# Standalone Tools

These commands use the same core logic as the full workflow, but are designed for targeted, single-purpose tasks.

## Zone Diagnostics

```
tagslut show-zone /path/to/file.flac
```

Optional:

```
tagslut show-zone /path/to/file.flac --zones-config ~/.config/tagslut/zones.yaml
```

## Keeper Explanation

Explain why a keeper was selected for a duplicate group (group id is the checksum):

```
tagslut explain-keeper --db /path/to/music.db --group-id <checksum>
```

Override priorities or enable metadata tiebreaker:

```
tagslut explain-keeper --db /path/to/music.db --group-id <checksum> \
  -p accepted -p staging -p suspect -p quarantine \
  --metadata-tiebreaker --metadata-fields artist,album,title
```

## Enrich a Single File

```
tagslut enrich-file --db /path/to/music.db --file /path/to/file.flac --providers itunes,tidal --execute
```

Dry-run (default):

```
tagslut enrich-file --db /path/to/music.db --file /path/to/file.flac
```

Standalone (no DB):

```
tagslut enrich-file --standalone --file /path/to/file.flac --providers itunes,tidal
```

## Enrich Without a DB

```
tagslut metadata enrich --standalone --path /path/to/flacs --providers beatport,spotify
```

## Scan Without a DB

```
tagslut scan --standalone /path/to/flacs
```

## Workflow-Compatible Commands

These are thin wrappers around existing tools, kept for compatibility:

- `tagslut scan ...`
- `tagslut recommend ...`
- `tagslut apply ...`
- `tagslut promote ...`
- `tagslut quarantine plan ...`
- `tagslut quarantine apply ...`
- `tagslut quarantine suspects ...`
- `tagslut metadata enrich ...`

All wrappers are **non-destructive** by default and respect the no-deletion rule.
