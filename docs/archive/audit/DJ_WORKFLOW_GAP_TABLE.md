<!-- Status: Gap analysis. Facts vs. promises. -->

# DJ Workflow Gap Table

Complete table of expected vs. actual behavior across all workflow stages.

| **Stage** | **Workflow Step** | **Expected Behavior** | **Actual Behavior** | **Evidence** | **Root Cause** | **Priority** |
|-----------|-------------------|----------------------|--------------------|----------|------|----------|
| **Entry** | `--dj` flag exists | Single, deterministic workflow | Two divergent runtime paths (precheck vs. promote branch) | tools/get-intake L920–L930 | Legacy wrapper with conditional logic based on file existence | CRITICAL |
| **2A** | MP3 build | FFmpeg errors are caught and reported | FFmpeg failures are silent; exit codes not checked | tagslut/mp3/transcode.py (no stderr capture) | No error handling in transcoder | CRITICAL |
| **2A** | MP3 build | Output validation (file size, duration, ID3) | No output validation; assume success | tests mock ffmpeg; no real ffmpeg tests | Missing post-transcode validation step | CRITICAL |
| **2A** | MP3 build | Pre-flight file check before transcode starts | Files checked during transcode; mid-transcode failures leave state inconsistent | test_e2e1_mp3_build_skips_missing_flac shows skip-on-discovery | No pre-flight validation | HIGH |
| **2B** | MP3 reconcile | Clear feedback on false positives and ambiguous matches | Title+artist matches silently create associations for remixes/compilations | Mock data in tests; no real ISRC collision tests | No confidence scoring for title+artist fallback | HIGH |
| **2B** | MP3 reconcile | ISRC matching is reliable | Duplicate ISRCs cause wrong track registration | No test for duplicate ISRC scenario | Rare but possible in Beatport; no handling | MEDIUM |
| **2B** | MP3 reconcile | All MP3 files are registered or marked as "needs review" | Some MP3s with status='suspect' remain orphaned; no clear path to admit them | reconcile_log exists but no operator workflow to action suspect rows | Missing "manual review + admit" workflow | MEDIUM |
| **Enrich** | Lexicon backfill | Flagged as mandatory for DJ workflow | Documented as optional and repeatable | docs/DJ_WORKFLOW.md says "Safe to run repeatedly — overwrites only lexicon_* prefixed keys" | Lexicon backfill not integrated into canonical 4-stage pipeline | CRITICAL |
| **Enrich** | Enrichment completeness | All tracks have required DJ fields before admission | DJ library admits tracks with incomplete metadata (no energy, danceability) | No validation in dj_backfill; no test for enrichment status | No enrichment contract enforced before DJ admission | CRITICAL |
| **3A** | DJ backfill | MP3 file must exist before admission | Admission happens even if MP3 deleted or missing | test_e2e3_backfill_then_validate_passes shows no pre-admission file check | No file validation in admission logic | CRITICAL |
| **3A** | DJ backfill | Admission is idempotent and safe to re-run | Re-running admission after file deletion creates orphaned DB rows | test_e2e3_backfill_idempotent tests DB idempotence, not file state | No enforcement of file existence before admission | HIGH |
| **3B** | DJ validate | Validates all admission pre-conditions | Validates only file existence and basic metadata; no enrichment check | exec/dj_validate.py checks file exists but not canonical_payload_json fields | Missing enrichment validation in validate step | CRITICAL |
| **3B** | DJ validate | Blocks export if validation fails | Validate is optional; export can run without it | test_e2e3_backfill_then_validate_passes shows validate runs but doesn't block subsequent emit | No prerequisite enforcement between validate and emit | HIGH |
| **3B** | DJ validate | Updates state to mark track as "ready" | Validate runs but doesn't update dj_admission state; emit doesn't check validate status | Validate outputs report only; no DB state change | No readiness state machine in dj_admission | HIGH |
| **4A** | XML emit | Pre-flight check that all files exist and metadata is complete | No pre-flight checks; can export with missing files and incomplete metadata | exec/dj_xml.py starts XML generation without validation; --skip-validation flag bypasses all checks | No pre-emission validation | CRITICAL |
| **4A** | XML emit | Enrichment is mandatory and validated | Enrichment is optional; XML exports without energy, danceability if not backfilled | No validation of canonical_payload_json required fields in exec/dj_xml.py | No enrichment contract before export | CRITICAL |
| **4B** | XML patch | Prior export manifest hash is verified to prevent tampering | Manifest hash is verified and blocks patching | tests/storage/v3/test_dj_exports.py::test_patch_rejects_tampered_manifest | Correctly implemented ✓ | N/A |
| **4B** | XML patch | TrackIDs are stable across patch cycles | TrackIDs are preserved via dj_track_id_map | test_e2e5_patch_track_ids_stable_across_cycles | Correctly implemented ✓ | N/A |
| **Entry** | Canonical CLI vs. wrapper | Only one entry point; operator confusion reduced | Three entry points (tools/get --dj, tools/get-intake --dj, canonical 4-stage CLI) | All three codepaths exist; docs recommend canonical but wrappers still active | Legacy wrappers not removed | HIGH |
| **Legacy** | `tools/get --dj` | [DEPRECATED] Operator uses canonical 4-stage CLI | Operator still uses legacy wrapper thinking it's safe | Deprecation warnings added but wrapper still functional | No removal deadline; no migration path | HIGH |
| **Legacy** | `tools/get-intake --dj` | [DEPRECATED] Operator uses canonical 4-stage CLI | Operator still uses legacy wrapper as alternative to tools/get --dj | Deprecation warnings added but wrapper still functional | No removal deadline; no migration path | HIGH |

---

## Gap Categories

### Critical (Blocks reliable DJ workflow)

1. **FFmpeg silent failures**: Broken MP3s enter DJ pool undetected
2. **Enrichment optional**: DJ XML exports incomplete
3. **No MP3 file validation**: Admission and export don't verify files exist
4. **Two legacy entry points**: Operator confusion about which path is safe

### High (Degrades reliability)

1. **Validate doesn't block export**: pre-conditions not enforced
2. **No readiness state**: operator doesn't know when DJ library is complete
3. **Title+artist false positives**: wrong tracks registered
4. **MP3 reconcile provides no manual review path**: suspect tracks orphaned

### Medium (Operational pain)

1. **Pre-flight check missing**: failures discovered mid-transcode
2. **Enrichment timing ambiguous**: operator doesn't know when backfill is required
3. **Three export code paths**: inconsistent behavior

---

## Fast Fixes Mapping

| Gap | Severity | Fix Approach | Effort | Files |
|-----|----------|--------------|--------|-------|
| FFmpeg failures silent | CRITICAL | Add output validation (file size, duration, ID3) | 1 hour | tagslut/mp3/transcode.py |
| Enrichment optional | CRITICAL | Add validation to emit; require energy/danceability | 1 hour | tagslut/dj/xml.py |
| No MP3 file validation | CRITICAL | Add file check in dj_admit; fail if missing | 30 min | tagslut/exec/dj_admit.py |
| Validate doesn't block | HIGH | Make validate mandatory pre-condition for emit | 1 hour | tagslut/exec/dj_xml.py |
| No readiness state | HIGH | Add mp3_asset.readiness + dj_admission.readiness | 8 hours | schema migrations + exec layer |
| Legacy wrappers still active | HIGH | Add deprecation deadline; set removal timeline | 30 min | tools/get, tools/get-intake |
| Title+artist false positives | HIGH | Add confidence scoring + operator review path | 4 hours | tagslut/mp3/reconcile.py + CLI |

---

## Outcome After Fixes

| Current State | After Critical Fixes | After Week 1 Hardening |
|---------------|---------------------|----------------------|
| FFmpeg errors: silent | → Detected, reported | → Blocks pipeline |
| Enrichment: optional | → Validated | → Mandatory |
| MP3 files: not validated | → Checked at admission | → Checked at admission + export |
| Validate: optional | → Recommended | → Mandatory |
| Readiness: implicit | → Explicit state | → State machine enforced |
| Retroactive MP3: manual | → Operator-friendly review | → Documented workflow |

---

## Evidence Trail

- **FFmpeg failures**: tagslut/mp3/transcode.py (line-by-line code review shows no stderr capture)
- **Enrichment optional**: docs/DJ_WORKFLOW.md L145+ describes Lexicon backfill as repeatable/optional
- **No file validation**: test_e2e3_backfill_then_validate_passes (validate runs but is not blocking)
- **Two legacy paths**: tools/get-intake L920–L2900 (DJ_MODE conditional logic)

---

## Test Cover Targets

| Gap | Missing Test | Estimated Impact |
|-----|--------------|------------------|
| FFmpeg failures | mp3 build with ffmpeg exit code > 0; truncated output | Prevents broken MP3s in pool |
| Enrichment optional | XML emit without energy/danceability field | Prevents incomplete DJ metadata |
| MP3 file deletion | File deleted post-admission, pre-export | Prevents orphaned DB state |
| ISRC collision | Two MP3s with same ISRC | Prevents wrong source association |
| Title+artist false positive | Remix with same title+artist as original | Prevents metadata mismatches |
| Retroactive MP3 admission | End-to-end admit of existing directory | Enables documented MP3 retrofit workflow |

