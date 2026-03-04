"""Deprecated recovery package stub.

This package has been archived under ``legacy/tagslut_recovery``.
Use canonical flows under ``tagslut verify`` and ``tagslut report``.
"""

from __future__ import annotations


class DeprecatedModule:
    """Proxy object that raises ImportError when accessed or called."""

    def __init__(self, symbol: str, migration: str) -> None:
        self._symbol = symbol
        self._migration = migration

    def _raise(self) -> None:
        raise ImportError(
            f"{self._symbol} is archived and no longer available from tagslut.recovery. "
            f"{self._migration}"
        )

    def __getattr__(self, _name: str):
        self._raise()

    def __call__(self, *args, **kwargs):
        self._raise()


_MIGRATION = (
    "Use canonical entrypoints: `tagslut verify recovery ...` and "
    "`tagslut report recovery ...`; archived implementation lives in "
    "`legacy/tagslut_recovery/`."
)

RecoveryScanner = DeprecatedModule("RecoveryScanner", _MIGRATION)
Repairer = DeprecatedModule("Repairer", _MIGRATION)
Verifier = DeprecatedModule("Verifier", _MIGRATION)
Reporter = DeprecatedModule("Reporter", _MIGRATION)

__all__ = ["RecoveryScanner", "Repairer", "Verifier", "Reporter"]


def __getattr__(name: str):
    raise ImportError(
        "tagslut.recovery is archived. "
        f"Attempted attribute: {name!r}. {_MIGRATION}"
    )
