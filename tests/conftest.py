"""Module description placeholder."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


FIXTURE_DIR = ROOT / "tests" / "data"
HEALTHY_FLAC_B64 = (
    "ZkxhQwAAACIQABAAAAALAAALAfQAcAAAAIBQrUjBixKWAtMFoSiyRdNEhAAAKCAAAAByZWZlcmVu"
    "Y2UgbGliRkxBQyAxLjQuMyAyMDIzMDYyMwAAAAD/+GQCAH8eAQO52w=="
)


def _ensure_fixture_files() -> None:
    FIXTURE_DIR.mkdir(exist_ok=True)

    healthy = FIXTURE_DIR / "healthy.flac"
    if not healthy.exists():
        healthy.write_bytes(base64.b64decode(HEALTHY_FLAC_B64))

    corrupt = FIXTURE_DIR / "corrupt.flac"
    if not corrupt.exists():
        corrupt.write_bytes(b"NOTFLAC")


def pytest_configure() -> None:
    _ensure_fixture_files()
