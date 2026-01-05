# Architecture overview

```
+---------------------------+
|        dedupe.cli         |
|  argparse entry point     |
|  sync / staging cmds      |
+-------------+-------------+
              |
     +--------v--------+
     |   dedupe.sync   |<-----------------+
     | synchronisation |                  |
     | helpers         |                  |
     +--------+--------+                  |
              |                           |
     +--------v--------+         +--------v--------+
     |  dedupe.health  |         | dedupe.integrity |
     | command / null  |         | scanner helpers  |
     | health checks   |         | + metadata       |
     +-----------------+         +------------------+
```

## Key principles

- **Single source of truth** – core logic lives inside `src/dedupe/` and is
  shared across CLI entry points and unit tests.
- **Composition** – the sync workflow delegates health checks to
  `dedupe.health`, while staging scans share ffprobe/fingerprint helpers.
- **Compatibility** – legacy scripts under `scripts/` import and expose the new
  modules so existing automation does not break.

## Module summary

- `dedupe.cli` – command routing and output formatting.
- `dedupe.sync` – synchronisation data classes, helpers, and orchestration.
- `dedupe.health` – `HealthChecker` protocol plus command-backed implementations.
- `dedupe.integrity_scanner` – zone-aware scanning with integrity checks for
  COMMUNE staging/accepted zones.
