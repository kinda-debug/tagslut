from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from tagslut.library.matcher import TrackQuery


@dataclass(frozen=True)
class RawResult:
    provider: str
    external_id: str | None
    query_text: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class FieldCandidate:
    field_name: str
    normalized_value: Any
    confidence: float
    rationale: dict[str, Any]


class MetadataProvider(Protocol):
    name: str

    def search(self, query: TrackQuery) -> list[RawResult]: ...

    def normalize(self, raw: RawResult) -> list[FieldCandidate]: ...
