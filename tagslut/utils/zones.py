"""Deprecated: use tagslut.zones (canonical) instead of tagslut.zones."""

from __future__ import annotations

import warnings

warnings.warn(
    "tagslut.zones is deprecated; import from tagslut.zones instead.",
    DeprecationWarning,
    stacklevel=2,
)

from tagslut.zones import *  # noqa: F401,F403
from tagslut.zones import __all__  # type: ignore  # noqa: F401
