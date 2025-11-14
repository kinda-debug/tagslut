# Process flow

The rebuilt toolkit centres on a four-stage workflow that turns raw library
scans and R-Studio exports into an actionable recovery manifest. Each stage is
exposed via a dedicated CLI sub-command.

## 1. Scan the reference library

```
dedupe scan-library --root <music_root> --out library.db [--fingerprints]
```

1. Walk the target directory recursively, filtering for supported audio files.
2. Capture filesystem metadata, ffprobe-derived stream details, and optional
   Chromaprint fingerprints.
3. Store the results inside the `library_files` table of the specified SQLite
   database.

## 2. Parse recovery exports

```
dedupe parse-rstudio --input Recognized.txt --out recovered.db
```

1. Read an R-Studio "Recognized Files" export, automatically detecting CSV or
   TSV dialects.
2. Normalise the recorded paths and persist key attributes in the
   `recovered_files` table.
3. Re-run this step whenever fresh exports arrive to keep the database current.

## 3. Match recovered candidates

```
dedupe match --library library.db --recovered recovered.db --out matches.csv
```

1. Load both databases and compute filename similarity plus size deltas for each
   potential pairing.
2. Produce ranked matches that highlight likely duplicates, truncated copies, or
   potential upgrades.
3. Emit a CSV report for human triage and downstream automation.

## 4. Generate a recovery manifest

```
dedupe generate-manifest --matches matches.csv --out manifest.csv
```

1. Classify each match by severity and confidence to determine recovery
   priority.
2. Annotate rows with operator notes describing why a candidate warrants
   attention.
3. Produce a manifest that can be used in selective recovery or manual review
   pipelines.

## Legacy workflows

Earlier quarantine and synchronisation flows are preserved inside
[`dedupe/ARCHIVE/`](../dedupe/ARCHIVE/). Those documents and scripts remain
available for historical reference but are superseded by the streamlined
four-step process outlined above.
