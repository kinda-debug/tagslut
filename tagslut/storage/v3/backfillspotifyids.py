"""Backward-compatible alias for `tagslut.storage.v3.backfill_spotify_ids`.

Some older code referenced `tagslut.storage.v3.backfillspotifyids` (no underscores).
This module re-exports the current implementation and keeps the CLI entrypoint.
"""

from __future__ import annotations

from . import backfill_spotify_ids as _impl

# Re-export everything (including underscore-prefixed helpers) for maximum compatibility.
for _name, _value in _impl.__dict__.items():
    if _name in {"__builtins__", "__cached__", "__loader__", "__spec__"}:
        continue
    if _name.startswith("__") and _name not in {"__doc__", "__package__"}:
        continue
    globals()[_name] = _value

__all__ = tuple(name for name in _impl.__dict__.keys() if name not in {"__builtins__"})


def __getattr__(name: str):
    return getattr(_impl, name)


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(dir(_impl)))


if __name__ == "__main__":
    raise SystemExit(_impl.main())
