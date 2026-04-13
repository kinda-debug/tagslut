You are an expert Python engineer working in the tagslut repository.

Goal:
Implement the Week 1 critical-path missing tests from docs/audit/MISSING_TESTS.md.
This prompt covers the tests NOT included in dj-ffmpeg-validation.prompt.md and
dj-validate-gate.prompt.md. Specifically:

- MISSING_TESTS.md §3  — Enrichment validation before XML export
- MISSING_TESTS.md §5  — MP3 reconcile with mixed ISRC/ID3 coverage
- MISSING_TESTS.md §8  — MP3 output validation helper (unit)
- MISSING_TESTS.md §9  — Rekordbox XML structural validation
- MISSING_TESTS.md §12 — Pre-flight validation (already covered by validate-gate prompt, skip)
- MISSING_TESTS.md §15 — Enrichment backfill idempotence

Total: 5 new test files, ~20 tests, ~10 hours.

Read first (in order):
1. AGENT.md
2. .codex/CODEX_AGENT.md
3. docs/PROJECT_DIRECTIVES.md
4. docs/audit/MISSING_TESTS.md        (full file — this is your spec)
5. tagslut/dj/admission.py            (validate_dj_library, DjValidationReport)
6. tagslut/dj/xml_emit.py             (emit_rekordbox_xml, _build_export_scope)
7. tagslut/exec/transcoder.py         (_validate_mp3_output if it exists — see ffmpeg prompt)
8. tests/dj/test_dj_pipeline_e2e.py   (pattern reference for in-memory DB setup)

Verify before editing:
- poetry run pytest tests/dj/test_dj_pipeline_e2e.py -v --tb=short 2>&1 | tail -10

Constraints:
- No I/O against mounted volumes (MASTER_LIBRARY, DJ_LIBRARY, etc).
- No real ffmpeg calls. Use mock/patch for all subprocess.
- All tests use in-memory SQLite or tmp_path.
- Targeted pytest only.
- Do not modify existing test files.

---

## File 1: `tests/exec/test_dj_xml_enrichment_required.py`

Maps to MISSING_TESTS.md §3.

The audit identified that XML can be emitted without required DJ fields
(energy, danceability, BPM). These tests verify what happens when metadata
is incomplete and document the expected behavior.

Note: the current codebase does NOT enforce enrichment requirements at emit time.
Write the tests to document the CURRENT behavior (permissive) with a TODO comment
marking them as regression anchors for when enforcement is added.

Required tests:
1. `test_emit_with_complete_metadata_succeeds`
   Admitted track has bpm, key, title, artist all set. Emit succeeds.

2. `test_emit_with_missing_bpm_currently_succeeds`
   Admitted track has no BPM. Emit should succeed (no enforcement yet).
   Add a `# TODO: change to assert raises once enrichment gate is implemented` comment.

3. `test_emit_with_missing_artist_title_blocked_by_validate`
   Admitted track with empty artist/title. validate_dj_library() should flag
   MISSING_METADATA. emit_rekordbox_xml() with skip_validation=False should
   fail at the validation step (either inline or via the gate from validate-gate prompt).

4. `test_validate_report_identifies_missing_metadata`
   Directly call validate_dj_library() on a DB with one admission that has empty
   artist_norm. Assert the returned report has a MISSING_METADATA issue.

---

## File 2: `tests/exec/test_mp3_reconcile_matching_fallbacks.py`

Maps to MISSING_TESTS.md §5.

Find the MP3 reconcile module. Look for it in one of:
  - `tagslut/exec/mp3_reconcile.py`
  - `tagslut/dj/mp3_reconcile.py`
  - `tagslut/exec/mp3_build.py`
  - `tagslut/cli/commands/mp3.py`

Run: `grep -r "def reconcile" tagslut/ --include="*.py" -l`

Read the module before writing tests. Write tests that match the actual API.

Required tests (adjust to actual API):
1. `test_isrc_match_produces_high_confidence`
   MP3 file with ISRC in ID3 tags that matches a track_identity row.
   Assert confidence level is 'high' or 'verified'.

2. `test_missing_isrc_title_artist_fallback`
   MP3 without ISRC but with matching title+artist.
   Assert match is found but confidence is lower than ISRC match.

3. `test_no_match_produces_suspect_status`
   MP3 with no ISRC and no matching title/artist in DB.
   Assert mp3_asset row gets status='suspect' or is not registered.

4. `test_duplicate_isrc_handled_without_silent_skip`
   Two mp3_asset rows with the same ISRC.
   Assert that reconcile either picks one deterministically or logs both
   without silently ignoring either.

5. `test_reconcile_is_idempotent`
   Run reconcile twice on same MP3. Assert the second run produces no new rows
   (no duplicates created).

If the reconcile module does not exist or is not yet implemented, write the tests
as a specification stub:
```python
@pytest.mark.skip(reason="mp3_reconcile not yet implemented — test is a spec stub")
def test_isrc_match_produces_high_confidence():
    ...
```

---

## File 3: `tests/unit/test_mp3_validation_helpers.py`

Maps to MISSING_TESTS.md §8.

If `_validate_mp3_output()` exists in `tagslut/exec/transcoder.py` (added by the
ffmpeg-validation prompt), import and test it directly. If not, write stubs.

Required tests:
1. `test_missing_file_raises`
   Pass a non-existent path. Assert `TranscodeError`.

2. `test_file_too_small_raises`
   Create a 100-byte file in tmp_path. Assert `TranscodeError` with "suspiciously small".

3. `test_garbage_bytes_raises`
   Create a 10KB file filled with zeros. Assert `TranscodeError` with "unreadable".

4. `test_valid_mock_mp3_passes`
   Mock `mutagen.mp3.MP3` to return duration=210.0. Create a real >4KB file.
   Assert no exception.

5. `test_duration_too_short_raises`
   Mock `mutagen.mp3.MP3` to return duration=0.1. Create a real >4KB file.
   Assert `TranscodeError` with "duration too short".

---

## File 4: `tests/storage/v3/test_dj_xml_validation.py`

Maps to MISSING_TESTS.md §9.

Tests that emitted XML is structurally valid as Rekordbox XML.

Required tests:
1. `test_xml_has_dj_playlists_root`
   Emit XML. Parse with `xml.etree.ElementTree`. Assert root tag is `DJ_PLAYLISTS`.

2. `test_xml_track_ids_are_unique`
   Emit XML with 3 admitted tracks. Parse. Assert all `TrackID` attributes are unique.

3. `test_xml_collection_entries_matches_track_count`
   Emit XML. Assert `COLLECTION[Entries]` attribute equals number of TRACK elements.

4. `test_xml_playlist_track_keys_resolve`
   Emit XML with one playlist containing 2 tracks. Parse. Assert all `TRACK[Key]`
   values in PLAYLISTS section exist as `TRACK[TrackID]` values in COLLECTION.

5. `test_xml_is_deterministic`
   Emit XML twice from identical DB state. Assert SHA-256 of both files is equal.

6. `test_xml_location_uses_file_uri`
   Emit XML. Assert `TRACK[Location]` starts with `file://localhost`.

All tests use in-memory SQLite + tmp_path. No real MP3 files needed — mock file
existence if validation requires it.

---

## File 5: `tests/exec/test_lexicon_backfill_idempotence.py`

Maps to MISSING_TESTS.md §15.

Find the Lexicon backfill module. Look in:
  - `tagslut/dj/lexicon.py`
  - `tagslut/exec/lexicon_backfill.py`

Run: `grep -r "def.*backfill\|def.*lexicon" tagslut/ --include="*.py" -l`

Read the module before writing tests. If the module does not exist yet, write
specification stubs (marked @pytest.mark.skip with reason).

Required tests:
1. `test_backfill_first_run_sets_canonical_payload`
   Run backfill once on a track with known Lexicon match.
   Assert `canonical_payload_json` contains expected lexicon fields.

2. `test_backfill_second_run_is_idempotent`
   Run backfill twice. Assert final DB state is identical to after the first run.
   No duplicate rows, no data accumulation.

3. `test_backfill_unmatched_track_not_modified`
   Track with no Lexicon match. Run backfill.
   Assert `canonical_payload_json` is unchanged (or null).

4. `test_backfill_partial_match_flag_set`
   Track where Lexicon has partial data only. Assert result has a confidence flag
   or partial-match indicator rather than silently accepting.

---

## Verification

After all 5 files are written:

```bash
poetry run pytest \
  tests/exec/test_dj_xml_enrichment_required.py \
  tests/exec/test_mp3_reconcile_matching_fallbacks.py \
  tests/unit/test_mp3_validation_helpers.py \
  tests/storage/v3/test_dj_xml_validation.py \
  tests/exec/test_lexicon_backfill_idempotence.py \
  -v --tb=short 2>&1 | tail -30
```

Then run the existing pipeline tests to confirm no regressions:
```bash
poetry run pytest tests/dj/test_dj_pipeline_e2e.py -v --tb=short 2>&1 | tail -10
```

Done when: all non-stub tests pass, no regressions.

Commit: `test(dj): add Week 1 critical-path missing tests for DJ pipeline`
