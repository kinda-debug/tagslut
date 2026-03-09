from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from mutagen.id3 import APIC, ID3, SYLT, TXXX, USLT

from tagslut.exec.transcoder import (
    _apply_cover_art,
    _apply_dj_tag_policy,
    _clear_dj_managed_frames,
    sync_dj_mp3_from_flac,
)


class _Picture:
    def __init__(self, data: bytes, mime: str, picture_type: int) -> None:
        self.data = data
        self.mime = mime
        self.type = picture_type


class _FakeFlac:
    def __init__(self, pictures: list[_Picture]) -> None:
        self.pictures = pictures


class _FakeTaggedFlac(dict):
    def __init__(self, data: dict[str, list[str]], pictures: list[_Picture]) -> None:
        super().__init__(data)
        self.pictures = pictures


def test_apply_cover_art_replaces_existing_apic() -> None:
    tags = ID3()
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="old", data=b"old"))

    flac = _FakeFlac([
        _Picture(data=b"front", mime="image/png", picture_type=3),
        _Picture(data=b"other", mime="image/jpeg", picture_type=0),
    ])

    _apply_cover_art(tags, flac)  # type: ignore[arg-type]

    apics = tags.getall("APIC")
    assert len(apics) == 1
    assert apics[0].data == b"front"
    assert apics[0].mime == "image/png"


def test_dj_mp3_policy_keeps_cover_but_strips_lyrics_frames() -> None:
    tags = ID3()
    tags.add(USLT(encoding=3, lang="eng", desc="", text="lyrics"))
    tags.add(SYLT(encoding=3, lang="eng", format=2, type=1, desc="", text=[("line", 1000)]))

    tags.delall("USLT")
    tags.delall("SYLT")

    assert tags.getall("USLT") == []
    assert tags.getall("SYLT") == []


def test_dj_mp3_policy_keeps_only_useful_dj_tags() -> None:
    tags = ID3()
    tags.add(USLT(encoding=3, lang="eng", desc="", text="lyrics"))
    tags.add(SYLT(encoding=3, lang="eng", format=2, type=1, desc="", text=[("line", 1000)]))
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="old", data=b"old"))
    tags.add(TXXX(encoding=3, desc="KEEPME", text="persist"))

    flac = _FakeTaggedFlac(
        {
            "title": ["Title"],
            "artist": ["Artist"],
            "album": ["Album"],
            "date": ["2024"],
            "genre": ["House"],
            "bpm": ["122"],
            "initialkey": ["Am"],
            "label": ["Label"],
            "energy": ["7"],
            "isrc": ["ISRC123"],
        },
        pictures=[_Picture(data=b"front", mime="image/png", picture_type=3)],
    )

    def first(key: str) -> str | None:
        vals = flac.get(key)
        return vals[0] if vals else None

    _clear_dj_managed_frames(tags)
    _apply_dj_tag_policy(tags, flac, first)  # type: ignore[arg-type]

    assert tags["TIT2"].text[0] == "Title"
    assert tags["TPE1"].text[0] == "Artist"
    assert tags["TALB"].text[0] == "Album"
    assert str(tags["TDRC"].text[0]) == "2024"
    assert tags["TCON"].text[0] == "House"
    assert tags["TBPM"].text[0] == "122"
    assert tags["TKEY"].text[0] == "Am"
    assert tags["TXXX:INITIALKEY"].text[0] == "Am"
    assert tags["TXXX:LABEL"].text[0] == "Label"
    assert tags["TXXX:ENERGY"].text[0] == "7"
    assert tags["TSRC"].text[0] == "ISRC123"
    assert tags.getall("USLT") == []
    assert tags.getall("SYLT") == []
    assert tags.getall("APIC")[0].data == b"front"
    assert tags["TXXX:KEEPME"].text[0] == "persist"


def test_clear_dj_managed_frames_preserves_custom_txxx() -> None:
    tags = ID3()
    tags.add(TXXX(encoding=3, desc="KEEPME", text="persist"))
    tags.add(TXXX(encoding=3, desc="INITIALKEY", text="Cm"))
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="old", data=b"old"))

    _clear_dj_managed_frames(tags)

    assert tags.getall("APIC") == []
    assert "TXXX:INITIALKEY" not in tags
    assert tags["TXXX:KEEPME"].text[0] == "persist"


def test_sync_dj_mp3_from_flac_refreshes_dj_tags_preserves_custom(
    tmp_path: Path,
) -> None:
    """sync_dj_mp3_from_flac refreshes DJ-managed frames from FLAC
    while preserving non-DJ TXXX frames already on the MP3."""
    mp3_path = tmp_path / "test.mp3"
    # Minimal valid MP3 frame so mutagen can save/load ID3 tags
    mp3_path.write_bytes(b"\xff\xe3\x18\x00" + b"\x00" * 417)
    tags = ID3()
    tags.add(TXXX(encoding=3, desc="KEEPME", text="custom_value"))
    tags.add(TXXX(encoding=3, desc="INITIALKEY", text="Cm"))  # stale DJ tag
    tags.save(mp3_path)

    flac = _FakeTaggedFlac(
        {
            "title": ["New Title"],
            "artist": ["New Artist"],
            "initialkey": ["Am"],
            "bpm": ["128"],
        },
        pictures=[_Picture(data=b"art", mime="image/jpeg", picture_type=3)],
    )

    with patch("tagslut.exec.transcoder.FLAC", return_value=flac):
        sync_dj_mp3_from_flac(mp3_path, tmp_path / "fake.flac")

    result = ID3(mp3_path)
    # DJ-managed frames refreshed from FLAC source
    assert result["TIT2"].text[0] == "New Title"
    assert result["TPE1"].text[0] == "New Artist"
    assert result["TXXX:INITIALKEY"].text[0] == "Am"
    assert result["TBPM"].text[0] == "128"
    # Non-DJ custom frame survives
    assert result["TXXX:KEEPME"].text[0] == "custom_value"
