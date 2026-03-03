"""Deprecated scan package stub.

This package has been archived under ``legacy/tagslut_scan``.
The operator-facing ``scan`` command is retired from the canonical CLI surface.
"""

from __future__ import annotations


class DeprecatedModule(ImportError):
    """Import-time error for archived module usage."""


raise DeprecatedModule(
    "tagslut.scan is archived and no longer available from the live package. "
    "Use canonical CLI groups (`intake/index/decide/execute/verify/report/auth`) "
    "and see archived implementation in `legacy/tagslut_scan/`."
)
