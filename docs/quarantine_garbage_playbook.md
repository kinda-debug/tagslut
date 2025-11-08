# Quarantine and garbage directory playbook

Use this checklist to merge healthier copies from `/Volumes/dotad/Quarantine`
and `/Volumes/dotad/Garbage` back into the main library.

1. **Confirm configuration**
   - Ensure `config.toml` lists the three directories under `[paths]`:
     `/Volumes/dotad/MUSIC`, `/Volumes/dotad/Quarantine`, and
     `/Volumes/dotad/Garbage`.
   - All commands below traverse each directory recursively, so nested
     subfolders do not require additional flags.

2. **Audit quarantine inventory**
   - Capture a lightweight summary of the quarantine tree:
     ```bash
     python -m dedupe.cli quarantine scan /Volumes/dotad/Quarantine --output quarantine_scan.csv
     ```
   - Deep-inspect suspicious files when needed:
     ```bash
     python -m dedupe.cli quarantine analyse /Volumes/dotad/Quarantine --limit 200 --output quarantine_analysis.csv
     ```
   - Spot truncated or overlong audio by comparing container vs. decoded
     durations:
     ```bash
     python -m dedupe.cli quarantine length /Volumes/dotad/Quarantine --output quarantine_length.csv
     ```

3. **Check playback health before reintegration**
   - Run an integrity sweep over each source to flag corrupted copies:
     ```bash
     python -m dedupe.cli health scan /Volumes/dotad/Quarantine --log quarantine_health.log
     python -m dedupe.cli health scan /Volumes/dotad/Garbage --log garbage_health.log
     ```
   - Review the logs for failures and repair or discard broken files before
     synchronising anything into the main library.

4. **Dry-run synchronisation against each source**
   - Preview how replacements from the quarantine tree would affect the library:
     ```bash
     python -m dedupe.cli sync --dedupe-root /Volumes/dotad/Quarantine --dry-run
     ```
   - Repeat for the archive of confirmed duplicates:
     ```bash
     python -m dedupe.cli sync --dedupe-root /Volumes/dotad/Garbage --dry-run
     ```
   - Investigate any proposed swaps where the quarantine or garbage copies win;
     confirm the healthier file really should replace the library version.

5. **Commit the healthiest replacements**
   - After auditing the dry-run output, rerun synchronisation without
     `--dry-run` for the directories you trust:
     ```bash
     python -m dedupe.cli sync --dedupe-root /Volumes/dotad/Quarantine
     python -m dedupe.cli sync --dedupe-root /Volumes/dotad/Garbage
     ```
   - Keep the generated console logs as an audit trail and rerun the health
     sweep on `/Volumes/dotad/MUSIC` if you want to verify playback across the
     entire library (`--verify-library`).

Following this procedure ensures both auxiliary directories contribute their
healthiest tracks back into `/Volumes/dotad/MUSIC` while preserving a repeatable
review process.
