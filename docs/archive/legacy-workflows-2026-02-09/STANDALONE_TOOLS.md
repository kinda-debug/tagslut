# Standalone Tools

These commands use the same core logic as the full workflow, but are designed for targeted, single-purpose tasks.

## Zone Diagnostics

```
dedupe show-zone /path/to/file.flac
```

Optional:

```
dedupe show-zone /path/to/file.flac --zones-config ~/.config/dedupe/zones.yaml
```

## Keeper Explanation

Explain why a keeper was selected for a duplicate group (group id is the checksum):

```
dedupe explain-keeper --db /path/to/music.db --group-id <checksum>
```

Override priorities or enable metadata tiebreaker:

```
dedupe explain-keeper --db /path/to/music.db --group-id <checksum> \
  -p accepted -p staging -p suspect -p quarantine \
  --metadata-tiebreaker --metadata-fields artist,album,title
```

## Enrich a Single File

```
dedupe enrich-file --db /path/to/music.db --file /path/to/file.flac --providers itunes,tidal --execute
```

Dry-run (default):

```
dedupe enrich-file --db /path/to/music.db --file /path/to/file.flac
```

Standalone (no DB):

```
dedupe enrich-file --standalone --file /path/to/file.flac --providers itunes,tidal
```

## Enrich Without a DB

```
dedupe metadata enrich --standalone --path /path/to/flacs --providers beatport,spotify
```

## Scan Without a DB

```
dedupe scan --standalone /path/to/flacs
```

## Workflow-Compatible Commands

These are thin wrappers around existing tools, kept for compatibility:

- `dedupe scan ...`
- `dedupe recommend ...`
- `dedupe apply ...`
- `dedupe promote ...`
- `dedupe quarantine plan ...`
- `dedupe quarantine apply ...`
- `dedupe quarantine suspects ...`
- `dedupe metadata enrich ...`

All wrappers are **non-destructive** by default and respect the no-deletion rule.
