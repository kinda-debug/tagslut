from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DjTagSnapshot:
    artist: str | None
    title: str | None
    album: str | None
    genre: str | None
    label: str | None
    year: int | None
    isrc: str | None
    bpm: str | None
    musical_key: str | None
    energy_1_10: int | None
    bpm_source: str | None
    key_source: str | None
    energy_source: str | None
    identity_id: int | None
    preferred_asset_id: int | None
    preferred_path: str | None

    def as_dict(self) -> dict[str, object | None]:
        return asdict(self)
