"""Compatibility shim exposing key helpers for archived tests.

The archived integration tests under ``archive/2025-10-27-cleanup`` still
import :mod:`dd_flac_dedupe_db`. The original monolithic script evolved into the
modular :mod:`flac_scan` and :mod:`flac_dedupe` modules that now host the helper
functions under test.  To keep the historic tests runnable without
re-introducing the monolith, we re-export the relevant helpers from their new
home.
"""

from flac_scan import compute_fingerprint, parse_fpcalc_output, sha1_hex

__all__ = [
    "compute_fingerprint",
    "parse_fpcalc_output",
    "sha1_hex",
]
