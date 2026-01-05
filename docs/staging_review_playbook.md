# Staging review playbook

Use this checklist to compare staging copies in `/Volumes/COMMUNE/10_STAGING`
against the canonical library in `/Volumes/COMMUNE/20_ACCEPTED`.

The commands below use the streamlined staging sub-commands introduced to
replace the sprawling legacy scripts. Historical aliases (`analyse`, `scan`,
`length`) continue to work if you have existing automation.

1. **Confirm configuration**
   - Ensure `config.toml` lists the COMMUNE zones under `[library.zones]`,
     especially `10_STAGING` and `20_ACCEPTED`.
   - All commands below traverse each directory recursively, so nested
     subfolders do not require additional flags.

2. **Audit staging inventory**
   - Capture a lightweight summary of the staging tree:
     ```bash
     python3 -m dedupe.cli quarantine inventory /Volumes/COMMUNE/10_STAGING --output staging_scan.csv
     ```
   - Deep-inspect suspicious files when needed:
     ```bash
     python3 -m dedupe.cli quarantine inspect /Volumes/COMMUNE/10_STAGING --limit 200 --output staging_analysis.csv
     ```
   - Spot truncated or overlong audio by comparing container vs. decoded
     durations:
     ```bash
     python3 -m dedupe.cli quarantine duration /Volumes/COMMUNE/10_STAGING --output staging_length.csv
     ```

3. **Check playback health before reintegration**
   - Run an integrity sweep over staging to flag corrupted copies:
     ```bash
     python3 -m dedupe.cli health scan /Volumes/COMMUNE/10_STAGING --log staging_health.log
     ```
   - Review the logs for failures and repair or discard broken files before
     synchronising anything into the main library.

4. **Dry-run synchronisation**
   - Preview how replacements from staging would affect the library:
     ```bash
     python3 -m dedupe.cli sync --dedupe-root /Volumes/COMMUNE/10_STAGING --dry-run
     ```
   - Investigate any proposed swaps where the staging copies win;
     confirm the healthier file really should replace the library version.

5. **Commit the healthiest replacements**
   - After auditing the dry-run output, rerun synchronisation without
     `--dry-run` for the directories you trust:
     ```bash
     python3 -m dedupe.cli sync --dedupe-root /Volumes/COMMUNE/10_STAGING
     ```
   - Keep the generated console logs as an audit trail and rerun the health
     sweep on `/Volumes/COMMUNE/20_ACCEPTED` if you want to verify playback across the
     entire library (`--verify-library`).

Following this procedure ensures staging candidates enter `/Volumes/COMMUNE/20_ACCEPTED`
only after a repeatable, curator-led review process.

## Optional: progress bars with tqdm

For very large staging runs you can enable a progress bar to make long scans
easier to monitor. The project will use `tqdm` if it is available in your
environment; it's intentionally optional so the tool works without it.

To install `tqdm` in your active virtual environment:

```bash
python3 -m pip install tqdm
# or, if you prefer to install all project requirements:
python3 -m pip install -r requirements.txt
```

Once installed, run any staging command with `--verbose` to get a progress
bar during lengthy operations. Example:

```bash
python3 -m dedupe.cli quarantine inventory /Volumes/COMMUNE/10_STAGING \
  --output staging_scan.csv --limit 1000 --verbose
```

Notes:
- The progress bar appears only when `tqdm` is installed and `--verbose` is
  passed. Without `tqdm` the CLI will still print coarse progress updates.
- Prefer absolute paths for `--output` to avoid ambiguity about where the
  file will be written.
