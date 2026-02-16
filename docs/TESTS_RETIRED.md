# Retired Tests

These tests were previously disabled and are now formally retired because their target modules no longer exist or rely on deprecated legacy code paths. Reintroduce only after the referenced subsystems are restored.

- `tests/test_manifest.py.disabled`
  Rationale: `tagslut.manifest` module no longer exists.

- `tests/test_metadata.py.disabled`
  Rationale: `tagslut.metadata.probe_audio` and `metadata.which` are no longer present; metadata package is now provider-focused.

- `tests/test_picard_reconcile.py.disabled`
  Rationale: `tagslut.external.picard` and Picard reconcile workflow were removed from the active codebase.

- `tests/tools/test_apply_removals.py.disabled`
  Rationale: Depends on `legacy.tools.review.apply_removals`, which is no longer part of the active toolchain.

- `tests/legacy/test_db_compatibility.py.disabled`
  Rationale: Targets `dedupe_v2` compatibility checks that are not shipped in this repo.
