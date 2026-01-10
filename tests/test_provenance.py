from pathlib import Path
from dedupe.core.metadata import extract_metadata

def test_checksum_provenance_streaminfo(tmp_path: Path) -> None:
    # This requires a real FLAC file to test STREAMINFO.
    # For unit test purposes, we'll mock the internal dependencies if needed,
    # but since extract_metadata is what we want to test, let's see if we can use a small real flac from tests/data.
    flac_path = Path("tests/data/healthy.flac")
    if not flac_path.exists():
        # Fallback if running from a different context
        flac_path = Path(__file__).parent.parent / "tests" / "data" / "healthy.flac"

    # Test Phase 1 (Streaminfo only)
    audio_file = extract_metadata(flac_path, scan_hash=False)
    assert audio_file.checksum.startswith("streaminfo:")
    assert audio_file.checksum_type == "STREAMINFO_MD5"

def test_checksum_provenance_sha256(tmp_path: Path) -> None:
    flac_path = Path("tests/data/healthy.flac")
    if not flac_path.exists():
        flac_path = Path(__file__).parent.parent / "tests" / "data" / "healthy.flac"

    # Test Phase 3 (Full Hash)
    audio_file = extract_metadata(flac_path, scan_hash=True)
    # Even if streaminfo is present, scan_hash=True should promote it to SHA256_FULL
    assert audio_file.checksum_type == "SHA256_FULL"
    assert len(audio_file.checksum) == 64  # SHA256 hex length
