# Quarantine and garbage directory playbook

Use this checklist to merge healthier copies from `/Volumes/dotad/Quarantine`
and `/Volumes/dotad/Garbage` back into the main library.

The commands below use the streamlined quarantine sub-commands introduced to
replace the sprawling legacy scripts. Historical aliases (`analyse`, `scan`,
`length`) continue to work if you have existing automation.

1. **Confirm configuration**
   - Ensure `config.toml` lists the three directories under `[paths]`:
     `/Volumes/dotad/MUSIC`, `/Volumes/dotad/Quarantine`, and
     `/Volumes/dotad/Garbage`.
   - All commands below traverse each directory recursively, so nested
     subfolders do not require additional flags.

2. **Audit quarantine inventory**
   - Capture a lightweight summary of the quarantine tree:
     ```bash
     python3 -m dedupe.cli quarantine inventory /Volumes/dotad/Quarantine --output quarantine_scan.csv
     ```
   - Deep-inspect suspicious files when needed:
     ```bash
     python3 -m dedupe.cli quarantine inspect /Volumes/dotad/Quarantine --limit 200 --output quarantine_analysis.csv
     ```
   - Spot truncated or overlong audio by comparing container vs. decoded
     durations:
     ```bash
     python3 -m dedupe.cli quarantine duration /Volumes/dotad/Quarantine --output quarantine_length.csv
     ```

3. **Check playback health before reintegration**
   - Run an integrity sweep over each source to flag corrupted copies:
     ```bash
     python3 -m dedupe.cli health scan /Volumes/dotad/Quarantine --log quarantine_health.log
     python3 -m dedupe.cli health scan /Volumes/dotad/Garbage --log garbage_health.log
     ```
   - Review the logs for failures and repair or discard broken files before
     synchronising anything into the main library.

4. **Dry-run synchronisation against each source**
   - Preview how replacements from the quarantine tree would affect the library:
     ```bash
     python3 -m dedupe.cli sync --dedupe-root /Volumes/dotad/Quarantine --dry-run
     ```
   - Repeat for the archive of confirmed duplicates:
     ```bash
     python3 -m dedupe.cli sync --dedupe-root /Volumes/dotad/Garbage --dry-run
     ```
   - Investigate any proposed swaps where the quarantine or garbage copies win;
     confirm the healthier file really should replace the library version.

5. **Commit the healthiest replacements**
   - After auditing the dry-run output, rerun synchronisation without
     `--dry-run` for the directories you trust:
     ```bash
     python3 -m dedupe.cli sync --dedupe-root /Volumes/dotad/Quarantine
     python3 -m dedupe.cli sync --dedupe-root /Volumes/dotad/Garbage
     ```
   - Keep the generated console logs as an audit trail and rerun the health
     sweep on `/Volumes/dotad/MUSIC` if you want to verify playback across the
     entire library (`--verify-library`).

Following this procedure ensures both auxiliary directories contribute their
healthiest tracks back into `/Volumes/dotad/MUSIC` while preserving a repeatable
review process.

## Optional: progress bars with tqdm

For very large quarantines you can enable a progress bar to make long scans
easier to monitor. The project will use `tqdm` if it is available in your
environment; it's intentionally optional so the tool works without it.

To install `tqdm` in your active virtual environment:

```bash
python3 -m pip install tqdm
# or, if you prefer to install all project requirements:
python3 -m pip install -r requirements.txt
```

Once installed, run any quarantine command with `--verbose` to get a progress
bar during lengthy operations. Example:

```bash
python3 -m dedupe.cli quarantine inventory /Volumes/dotad/Quarantine \
  --output quarantine_scan.csv --limit 1000 --verbose
```

Notes:
- The progress bar appears only when `tqdm` is installed and `--verbose` is
  passed. Without `tqdm` the CLI will still print coarse progress updates.
- Prefer absolute paths for `--output` to avoid ambiguity about where the
  file will be written.

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
