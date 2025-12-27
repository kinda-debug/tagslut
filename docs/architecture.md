# Architecture overview

```
+---------------------------+
|        dedupe.cli         |
|  argparse entry point     |
|  sync / quarantine cmds   |
+-------------+-------------+
              |
     +--------v--------+
     |   dedupe.sync   |<-----------------+
     | synchronisation |                  |
     | helpers         |                  |
     +--------+--------+                  |
              |                           |
     +--------v--------+         +--------v--------+
     |  dedupe.health  |         | dedupe.quarantine|
     | command / null  |         | ffprobe/fpcalc   |
     | health checks   |         | analytics        |
     +-----------------+         +------------------+
```

## Key principles

- **Single source of truth** – core logic lives inside `src/dedupe/` and is
  shared across CLI entry points and unit tests.
- **Composition** – the sync workflow delegates health checks to
  `dedupe.health`, while quarantine commands share ffprobe/fingerprint helpers.
- **Compatibility** – legacy scripts under `scripts/` import and expose the new
  modules so existing automation does not break.

## Module summary

- `dedupe.cli` – command routing and output formatting.
- `dedupe.sync` – synchronisation data classes, helpers, and orchestration.
- `dedupe.health` – `HealthChecker` protocol plus command-backed implementations.
- `dedupe.quarantine` – ffprobe/fpcalc orchestration, CSV helpers, and
  high-level quarantine workflows.
