from __future__ import annotations

from mutagen.id3 import APIC, ID3, SYLT, USLT

from tagslut.exec.transcoder import _apply_cover_art


class _Picture:
    def __init__(self, data: bytes, mime: str, picture_type: int) -> None:
        self.data = data
        self.mime = mime
        self.type = picture_type


class _FakeFlac:
    def __init__(self, pictures: list[_Picture]) -> None:
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
