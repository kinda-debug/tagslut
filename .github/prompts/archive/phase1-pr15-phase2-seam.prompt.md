You are an expert Python/SQLite engineer working in the tagslut repository.

Goal:
Implement Phase 1 PR 15 (Phase 2 seam): a routing function that assigns the
correct ingestion track (Track A or Track B) to a file entering the v3 identity
pipeline, and enforces the correct ingestion_method and ingestion_confidence
based on that track.

Read first (in order):
1. AGENT.md
2. .codex/CODEX_AGENT.md
3. docs/PROJECT_DIRECTIVES.md
4. docs/PHASE1_STATUS.md
5. docs/INGESTION_PROVENANCE.md
6. docs/MULTI_PROVIDER_ID_POLICY.md
7. tagslut/storage/v3/dual_write.py (focus: dual_write_registered_file and
   upsert_track_identity)
8. tagslut/storage/v3/identity_service.py

Verify before editing:
- Run: poetry run pytest tests/storage/v3/test_identity_service.py -v
- Run: poetry run pytest tests/storage/v3/test_transaction_boundaries.py -v
- Capture results. Both must pass before and after your changes.

Constraints:
- Smallest reversible patch only.
- Do not modify DB files directly.
- No new dependencies.
- Targeted pytest only.

---

## Background

Two ingestion tracks exist (defined in docs/MULTI_PROVIDER_ID_POLICY.md):

**Track A — clean-slate** (new files from Beatport/TIDAL via provider API):
- `ingestion_method = 'provider_api'`
- `ingestion_confidence = 'verified'` (both providers agree on ISRC)
  OR `'high'` (single provider)

**Track B — legacy** (older files with accumulated cross-provider IDs):
- `ingestion_method = 'multi_provider_reconcile'`
- `ingestion_confidence = 'corroborated'` (all IDs agree on ISRC)
  OR `'uncertain'` (any conflict)
  OR `'high'` (single provider ID present)

Currently, `dual_write_registered_file()` always assigns `ingestion_method='provider_api'`
and sets confidence based only on whether an ISRC is present. This is wrong for
Track B files. There is no routing logic that selects the correct track.

---

## Implementation scope

### 1. Add `classify_ingestion_track()` to `tagslut/storage/v3/dual_write.py`

```python
def classify_ingestion_track(
    *,
    isrc: str | None,
    beatport_id: str | None,
    tidal_id: str | None,
    spotify_id: str | None,
    qobuz_id: str | None,
    download_source: str | None,
) -> tuple[str, str]:
    """
    Classify a file into ingestion Track A or B and return
    (ingestion_method, ingestion_confidence).

    Track A: file entered via a provider API download (download_source is
    a known provider). Returns ('provider_api', confidence) where confidence
    is 'high' for single-provider or 'verified' when cross-provider ISRC
    agreement is confirmed (not implemented here — caller must upgrade).

    Track B: file has accumulated cross-provider IDs but was not a direct
    API download. Returns ('multi_provider_reconcile', confidence) where
    confidence depends on ID agreement:
      - 'corroborated': multiple non-null IDs present, all consistent
      - 'uncertain': any ID present without ISRC, or ISRC missing
      - 'high': single provider ID + ISRC present

    Falls back to 'migration' / 'legacy' when source is unknown.
    """
```

Track A signals: `download_source` in `{'tidal', 'bpdl', 'beatport', 'deezer',
'qobuz', 'traxsource'}`.

Track B signals: `download_source` not in the above set, OR `download_source` is
`None`, AND at least one provider ID is present.

Confidence rules for Track B:
- `corroborated`: ISRC is not None AND at least two of
  [beatport_id, tidal_id, spotify_id, qobuz_id] are not None
- `high`: ISRC is not None AND exactly one provider ID is not None
- `uncertain`: ISRC is None, OR any provider IDs present without ISRC

### 2. Wire `classify_ingestion_track()` into `dual_write_registered_file()`

Replace the current hardcoded:
```python
ingestion_method="provider_api",
ingestion_confidence="high" if identity_hints["isrc"] else "uncertain",
```
with a call to `classify_ingestion_track()` using the hints from the metadata
dict and the `download_source` argument.

### 3. Write tests in `tests/storage/v3/test_phase2_seam.py`

Required tests:
- `test_track_a_provider_api_single_isrc` — tidal source + ISRC → `provider_api`, `high`
- `test_track_a_provider_api_no_isrc` — tidal source, no ISRC → `provider_api`, `uncertain`
- `test_track_b_corroborated` — unknown source, ISRC + beatport_id + tidal_id → `multi_provider_reconcile`, `corroborated`
- `test_track_b_high_single_provider` — unknown source, ISRC + one provider ID → `multi_provider_reconcile`, `high`
- `test_track_b_uncertain_no_isrc` — unknown source, provider IDs but no ISRC → `multi_provider_reconcile`, `uncertain`
- `test_fallback_to_migration` — no source, no IDs, no ISRC → `migration`, `legacy`
- `test_dual_write_uses_classify` — integration: call `dual_write_registered_file()` with
  tidal source + ISRC and assert the written `track_identity` row has
  `ingestion_method='provider_api'` and `ingestion_confidence='high'`

All tests must use in-memory SQLite with `create_schema_v3()`. No fixtures.

Required verification after edits:
- poetry run pytest tests/storage/v3/test_phase2_seam.py -v
- poetry run pytest tests/storage/v3/test_identity_service.py -v
- poetry run pytest tests/storage/v3/test_transaction_boundaries.py -v

Done when:
- `classify_ingestion_track()` exists and is exported from `tagslut/storage/v3/__init__.py`
- `dual_write_registered_file()` uses it instead of the hardcoded values
- All 7 tests pass
- No regressions in identity_service or transaction_boundary tests
- Conventional commit: `feat(seam): add Phase 2 ingestion track classifier and wire into dual_write`
