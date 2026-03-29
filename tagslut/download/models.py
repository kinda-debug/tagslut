from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DownloadResult:
    file_path: Path
    provider: str
    provider_track_id: str
    format: str
    download_source: str

