# Configuration reference

The modern CLI intentionally avoids hidden configuration so each command is
self-contained. Paths to libraries, exports, and output artefacts are supplied
explicitly via command arguments.

## Recommended environment variables

You may still wish to define environment variables for frequently used paths:

```bash
export DEDUPE_LIBRARY_ROOT="/Volumes/dotad/MUSIC"
export DEDUPE_RECOVERED_EXPORT="/Volumes/dotad/Recognized.txt"
export DEDUPE_ARTIFACT_DIR="$(pwd)/artifacts"
```

These variables make it easier to compose shell aliases or wrapper scripts while
keeping secrets (such as API tokens) in the environment, consistent with prior
security practices.

## Legacy configuration files

Historical workflows referenced `config.toml` and similar files to coordinate
quarantine, garbage, and repair operations. Those flows are now archived and no
longer consume the configuration file directly. The file remains in the
repository so past experiments stay reproducible. When building new automation,
prefer explicit CLI arguments and document any optional helpers in `README.md`
or `USAGE.md`.

If you resurrect a legacy workflow, verify whether its configuration keys still
apply and capture any deviations in `CHANGELOG.md` to keep the team informed.
