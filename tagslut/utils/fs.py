from __future__ import annotations

import unicodedata
from pathlib import Path


def normalize_path(p: str | Path) -> Path:
    """Normalize a filesystem path for reliable access across Unicode forms.

    Prefer NFC; if a differing NFD form exists on disk, use it instead.
    """
    raw = str(p)
    nfc = unicodedata.normalize("NFC", raw)
    if nfc == raw:
        return Path(nfc)

    nfd = unicodedata.normalize("NFD", raw)
    if nfd == raw:
        return Path(nfc)

    nfc_path = Path(nfc)
    if nfc_path.exists():
        return nfc_path

    nfd_path = Path(nfd)
    if nfd_path.exists():
        return nfd_path

    return nfc_path
