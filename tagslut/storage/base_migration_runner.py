from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Protocol, TypeAlias, Union, runtime_checkable


@runtime_checkable
class MigrationRunner(Protocol):
    """
    Structural protocol for SQLite migration runners in tagslut.

    Both concrete implementations (root runner and v3 runner) satisfy
    this protocol via their module-level run_pending / run_pending_v3
    functions wrapped as callables — see RunnerCallable below.

    Concrete divergences (documented here for cross-runner awareness):
      - Idempotency: root uses filename; v3 uses (schema_name, version)
      - Python migration contract: root requires up(conn); v3 requires
        up(conn) AND a module-level VERSION: int
      - Post-apply verification: root has none; v3 runs PRAGMA checks
      - Connection: root always opens its own; v3 accepts a live conn
      - ADD COLUMN IF NOT EXISTS: root rewrites it; v3 does not handle it
      - Underscore-prefix exclusion: v3 skips "_"-prefixed files; root
        does not (important: never point root runner at v3/migrations/)
    """


RunnerCallable: TypeAlias = Union[
    # root runner signature
    Callable[[str | Path, Path | None], list[str]],
    # v3 runner signature
    Callable[[str | Path | sqlite3.Connection, Path | None], list[str]],
]
