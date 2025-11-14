# Quarantine and garbage playbook (archived)

> **Status:** Archived. The quarantine-focused workflows documented in earlier
> versions of this repository have been superseded by the streamlined recovery
> pipeline built around `dedupe scan-library`, `parse-rstudio`, `match`, and
> `generate-manifest`. The information below summarises how the legacy commands
> operated and where to find their implementations for historical reference.

## Modern recovery pipeline

1. **Scan the canonical library** – run `dedupe scan-library` to capture
   metadata and optional fingerprints into `library.db`.
2. **Parse R-Studio exports** – ingest recognised files using
   `dedupe parse-rstudio` and store them in `recovered.db`.
3. **Match candidates** – execute `dedupe match` to correlate recovered files
   against the library, generating `matches.csv` with classifications such as
   `exact`, `truncated`, or `potential_upgrade`.
4. **Generate a manifest** – call `dedupe generate-manifest` to produce a
   prioritised CSV that guides selective recovery.

These steps replace the former quarantine commands by providing a single source
of truth for both the canonical library and recovery fragments. Refer to
[`USAGE.md`](../USAGE.md) for detailed examples and recommended command
arguments.

## Legacy command reference

The following commands were part of the prior quarantine toolkit and now reside
in [`dedupe/ARCHIVE/`](../dedupe/ARCHIVE/). They remain available for auditing
historical decisions or replaying legacy investigations:

- `dedupe.cli quarantine inventory`
- `dedupe.cli quarantine inspect`
- `dedupe.cli quarantine duration`
- `dedupe.cli health scan`

Each script retains its original help text inside the archive. When migrating a
legacy report into the new system, compare the CSV outputs with the matcher and
manifest artefacts produced by the modern workflow.

## When to consult the archive

- Reviewing historical anomalies or audits that relied on the quarantine
  commands.
- Recreating diagnostics from an old incident report or playbook.
- Porting bespoke analysis into the modern modules (for example, adding new
  match heuristics).

If you do revive an archived command, document the reason in `CHANGELOG.md` and
consider upstreaming reusable logic into the maintained modules so future work
continues to benefit from the unified architecture.
