# DO NOT recreate existing files. DO NOT modify DB or audio files directly.

# Allow TIDAL-sourced AAC m4a files through the intake codec gate

## Context

`tagslut/core/flac_scan_prep.py` currently blocks any file whose ffprobe codec
is in `LOSSY_CODECS` with `skip_reason="lossy_codec"`. AAC (codec name `aac`)
is in that set. TIDAL downloads files as AAC-LC at CD quality (44.1 kHz / 16-bit
AAC) when lossless is unavailable. These are legitimate source files and must be
accepted by intake, not blocked.

The fix is scoped entirely to `flac_scan_prep.py`. No other files should change.

## Precise behaviour required

When `codec_name == "aac"` AND `suffix == ".m4a"`:
- Do NOT return `skip_reason="lossy_codec"`.
- Proceed to the sample rate / bit depth guards as normal.
- Then convert to a temporary FLAC via `_convert_to_flac` (already implemented)
  and return the resulting `PreparedFlacInput` with `converted=True`.
- Set `codec_name` on the returned dataclass so callers can see it was AAC.

All other lossy codecs (mp3, aac in non-m4a containers, ogg, opus, etc.) remain
blocked as before. `.aac` bare extension files are NOT covered by this exception
— only `.m4a` containers.

## Implementation

In `prepare_flac_scan_input`, after the `suffix in LOSSY_EXTENSIONS` early-exit
block and after `_probe_audio_stream`, replace the unconditional lossy codec
block:

```python
if codec_name in LOSSY_CODECS:
    return PreparedFlacInput(...)   # blocked
```

with:

```python
is_tidal_aac = codec_name == "aac" and suffix == ".m4a"

if codec_name in LOSSY_CODECS and not is_tidal_aac:
    return PreparedFlacInput(
        source_path=source_path,
        scan_path=None,
        original_path=source_path,
        converted=False,
        codec_name=codec_name,
        sample_rate=sample_rate,
        bit_depth=bit_depth,
        skip_reason="lossy_codec",
        message=f"blocked lossy codec: {codec_name}",
    )
```

No other logic changes. The existing conversion path below handles the rest.

## Tests

File: `tests/core/test_flac_scan_prep.py`

Add the following cases (mock `_probe_audio_stream` and `_convert_to_flac`):

1. `.m4a` + codec `aac` + 44100 Hz + 16-bit → NOT blocked, `converted=True`,
   `scan_path` is not None.
2. `.m4a` + codec `aac` + 22050 Hz → blocked with
   `skip_reason="sample_rate_too_low"`.
3. `.m4a` + codec `alac` → passes through unchanged (existing ALAC path).
4. `.aac` (bare extension) → blocked by `LOSSY_EXTENSIONS` before codec probe
   is even reached (existing behaviour, regression guard).
5. `.mp3` → still blocked `lossy_extension` (regression guard).

Run: `poetry run pytest tests/core/test_flac_scan_prep.py -v`

## Commit

`fix(intake): allow TIDAL AAC m4a through codec gate`
