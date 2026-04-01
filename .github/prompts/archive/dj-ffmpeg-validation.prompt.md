You are an expert Python engineer working in the tagslut repository.

Goal:
Add FFmpeg output validation after every MP3 transcode in the DJ pool wizard.
Currently `_run_ffmpeg_transcode()` checks the exit code but does not verify the
output file. A zero-exit ffmpeg can still produce a truncated, silent, or
tag-corrupted MP3. This change adds a validation step immediately after every
transcode and surfaces failures as explicit `TranscodeError` so the wizard's
`failures` list is populated correctly.

Read first (in order):
1. AGENT.md
2. .codex/CODEX_AGENT.md
3. docs/PROJECT_DIRECTIVES.md
4. tagslut/exec/transcoder.py          (full file — this is where the fix lives)
5. tagslut/exec/dj_pool_wizard.py      (caller of transcode_to_mp3_from_snapshot)
6. docs/audit/MISSING_TESTS.md        (§ "FFmpeg Output Validation", §8)

Verify before editing:
- poetry run pytest tests/exec/ -v -k "transcode or mp3" 2>&1 | tail -20

Constraints:
- Smallest reversible patch. Transcode API is public — do not change signatures.
- `_run_ffmpeg_transcode()` must remain the sole subprocess caller.
- No new runtime dependencies. mutagen is already available.
- No writes to mounted volumes.
- Targeted pytest only.

---

## Fix 1 — Add `_validate_mp3_output()` to `tagslut/exec/transcoder.py`

Add this function immediately after `_run_ffmpeg_transcode()`:

```python
def _validate_mp3_output(path: Path, *, min_size_bytes: int = 4096) -> None:
    """Validate that a transcoded MP3 is playable and has readable ID3 tags.

    Raises TranscodeError on any validation failure so callers can treat the
    file as failed rather than silently accepting a corrupt output.

    Checks:
    1. File exists and is not empty.
    2. File size >= min_size_bytes (default 4KB — filters truncated writes).
    3. mutagen can parse the file as an MP3 (catches codec/container errors).
    4. Parsed duration > 1.0 seconds (filters silent/near-empty transcodes).
    """
    if not path.exists():
        raise TranscodeError(f"transcode output missing: {path}")
    size = path.stat().st_size
    if size < min_size_bytes:
        raise TranscodeError(
            f"transcode output suspiciously small ({size} bytes): {path}"
        )
    try:
        from mutagen.mp3 import MP3
        audio = MP3(str(path))
        duration = audio.info.length if audio.info else 0.0
    except Exception as exc:
        raise TranscodeError(f"transcode output unreadable by mutagen: {path}: {exc}") from exc
    if duration < 1.0:
        raise TranscodeError(
            f"transcode output duration too short ({duration:.2f}s): {path}"
        )
```

Wire it into `_run_ffmpeg_transcode()` — call `_validate_mp3_output(dest_path)`
immediately after the `subprocess.run` block (after the `returncode != 0` check).
The dest_path must be passed as an argument. Update the signature:

```python
def _run_ffmpeg_transcode(
    source: Path,
    dest_path: Path,
    *,
    bitrate: int,
    ffmpeg_path: str | None,
    validate_output: bool = True,   # new kwarg, default True
) -> None:
```

Call `_validate_mp3_output(dest_path)` at end of function body when `validate_output=True`.

No callers need to change — default is True, existing call sites pass positional args
that do not include `validate_output`.

---

## Fix 2 — Handle `TranscodeError` from validation in `dj_pool_wizard.py`

In `execute_plan()`, the existing `except Exception as exc` block around the
`transcode_to_mp3_from_snapshot()` call already catches `TranscodeError`.
**No change needed here** — validation failures will propagate as `TranscodeError`
and be caught by the existing handler, appended to `failures`, and logged correctly.

Verify this by reading `execute_plan()` around line 580 and confirming the pattern:
```python
try:
    transcode_to_mp3_from_snapshot(...)
except Exception as exc:
    failures.append(_failure(row, "transcode_failed", str(exc)))
    continue
```
If the pattern exists (it does), document it in a comment above the except block:
```python
# TranscodeError from _validate_mp3_output() is caught here alongside
# ffmpeg exit-code failures. Both produce "transcode_failed" entries.
```

---

## Fix 3 — Add tests in `tests/exec/test_mp3_build_ffmpeg_errors.py`

Write these tests. Use `unittest.mock.patch` to simulate failures — do NOT
require ffmpeg or audio files.

Required tests:
1. `test_ffmpeg_missing_raises_ffmpeg_not_found_error`
   Mock `shutil.which` to return None. Call `transcode_to_mp3(Path("/fake/a.flac"), Path("/tmp"))`.
   Assert `FFmpegNotFoundError` is raised.

2. `test_ffmpeg_nonzero_exit_raises_transcode_error`
   Mock `subprocess.run` to return `CompletedProcess([], 1, stderr="codec error")`.
   Assert `TranscodeError` is raised with "ffmpeg failed" in message.

3. `test_output_file_missing_raises_transcode_error`
   Mock `subprocess.run` to succeed (returncode=0) but do not create the dest file.
   Assert `TranscodeError` with "transcode output missing" in message.

4. `test_output_file_too_small_raises_transcode_error`
   Mock `subprocess.run` to succeed and create a 100-byte file.
   Assert `TranscodeError` with "suspiciously small" in message.

5. `test_output_file_unreadable_by_mutagen_raises_transcode_error`
   Mock `subprocess.run` to succeed, create a file > 4KB filled with zeros.
   Assert `TranscodeError` with "unreadable by mutagen" in message.

6. `test_valid_output_does_not_raise`
   Mock `subprocess.run` to succeed. Mock `mutagen.mp3.MP3` to return an object
   with `info.length = 210.0`. Assert no exception is raised.

7. `test_transcode_error_surfaces_in_pool_wizard_failures`
   Create a minimal in-memory wizard scenario:
   - Call `execute_plan()` with one row where `cache_action = "transcode"`.
   - Patch `transcode_to_mp3_from_snapshot` to raise `TranscodeError("test")`.
   - Assert `failures` has one entry with `error_type = "transcode_failed"`.

All tests must use `tmp_path` (pytest fixture) for any real file creation.
No I/O against mounted volumes.

Required verification after edits:
- poetry run pytest tests/exec/test_mp3_build_ffmpeg_errors.py -v --tb=short
- poetry run pytest tests/exec/ -v -k "transcode or mp3" --tb=short 2>&1 | tail -20

Done when: 7 tests pass, no regressions in existing transcode tests.

Commit: `feat(transcoder): add MP3 output validation after every ffmpeg transcode`
