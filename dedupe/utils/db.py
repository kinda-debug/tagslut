import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dedupe.utils.config import get_config, Config

logger = logging.getLogger("dedupe")


class DbResolutionError(ValueError):
    """Raised when database path resolution fails."""


class DbReadOnlyError(PermissionError):
    """Raised when a database path is not writable for a write operation."""


@dataclass(frozen=True)
class DbResolution:
    path: Path
    source: str
    candidates: list[tuple[str, Optional[str]]]
    exists: bool
    purpose: str
    allow_create: bool
    allow_repo_db: bool
    repo_root: Optional[Path]


def _normalize_db_value(value: str | Path) -> Path:
    path = Path(value).expanduser()
    try:
        return path.resolve(strict=False)
    except TypeError:
        # Python <3.9 doesn't support strict arg; fallback to default resolve.
        return path.resolve()


def _default_repo_root() -> Optional[Path]:
    try:
        return Path(__file__).resolve().parents[2]
    except (IndexError, RuntimeError):
        return None


def _ensure_parent_directory(path: Path) -> None:
    parent = path.expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)


def _db_is_repo_local(db_path: Path, repo_root: Path) -> bool:
    try:
        db_path.relative_to(repo_root)
        return True
    except ValueError:
        return False


def _check_writable_db_path(
    db_path: Path,
    *,
    exists: bool,
    allow_create: bool,
) -> None:
    issues: list[str] = []

    if exists:
        if not os.access(db_path, os.W_OK):
            issues.append(f"DB file is not writable: {db_path}")
        parent = db_path.parent
        if not os.access(parent, os.W_OK):
            issues.append(
                f"DB directory is not writable (WAL/SHM cannot be created): {parent}"
            )
        for suffix in ("-wal", "-shm"):
            sidecar = db_path.with_name(db_path.name + suffix)
            if sidecar.exists() and not os.access(sidecar, os.W_OK):
                issues.append(f"SQLite sidecar is not writable: {sidecar}")
    else:
        if not allow_create:
            issues.append(
                f"DB does not exist and --create-db was not supplied: {db_path}"
            )
        else:
            parent = db_path.parent
            if not os.access(parent, os.W_OK):
                issues.append(f"DB directory is not writable: {parent}")

    if issues:
        remediation = (
            "Fix permissions or choose a writable location. "
            "Ensure the DB file and its parent directory are writable, "
            "and that any -wal/-shm sidecars are writable or removed while the DB is closed. "
            "If the volume is mounted read-only, remount it as writable."
        )
        raise DbReadOnlyError("\n".join(issues + [remediation]))


def resolve_db_path(
    cli_db: Optional[str | Path],
    *,
    config: Optional[Config] = None,
    require: bool = True,
    allow_repo_db: bool = False,
    repo_root: Optional[Path] = None,
    purpose: str = "write",
    allow_create: bool = False,
    source_label: str = "cli",
) -> DbResolution:
    """Resolve the SQLite DB path based on CLI/env/config precedence."""
    config = config or get_config()
    env_db = os.getenv("DEDUPE_DB")
    config_db = config.get("db.path") if config else None
    repo_root = repo_root or _default_repo_root()

    candidates: list[tuple[str, Optional[str]]] = [
        (source_label, str(cli_db) if cli_db else None),
        ("env", env_db),
        ("config", config_db),
    ]

    resolved_value: Optional[str] = None
    source = ""
    for candidate_source, value in candidates:
        if value:
            resolved_value = value
            source = candidate_source
            break

    if not resolved_value:
        if require:
            raise DbResolutionError(
                "No database path provided. Use --db, set DEDUPE_DB, or configure db.path."
            )
        raise DbResolutionError("No database path provided.")

    db_path = _normalize_db_value(resolved_value)
    if db_path.exists() and db_path.is_dir():
        raise DbResolutionError(f"Database path points to a directory: {db_path}")

    if purpose not in ("read", "write"):
        raise DbResolutionError(f"Unknown purpose '{purpose}'. Expected 'read' or 'write'.")

    exists = db_path.exists()
    if purpose == "read" and not exists:
        raise DbResolutionError(f"Database does not exist: {db_path}")
    if purpose == "write" and not exists and not allow_create:
        raise DbResolutionError(
            f"Database does not exist and --create-db was not supplied: {db_path}"
        )

    if purpose == "write" and repo_root and _db_is_repo_local(db_path, repo_root):
        if not allow_repo_db:
            raise DbResolutionError(
                f"Refusing to write to repo-local DB: {db_path}. "
                f"Provide --allow-repo-db or choose a path outside {repo_root}."
            )

    logger.info("Resolved DB path: %s (source=%s)", db_path, source)
    return DbResolution(
        path=db_path,
        source=source,
        candidates=candidates,
        exists=exists,
        purpose=purpose,
        allow_create=allow_create,
        allow_repo_db=allow_repo_db,
        repo_root=repo_root,
    )


def _sqlite_uri(path: Path, mode: str) -> str:
    escaped = path.as_posix()
    return f"file:{escaped}?mode={mode}"


def print_db_provenance(resolution: DbResolution) -> None:
    exists = "yes" if resolution.exists else "no"
    print(
        "DB provenance: "
        f"path={resolution.path} source={resolution.source} "
        f"exists={exists} purpose={resolution.purpose}"
    )


def open_db(
    resolution: DbResolution,
    *,
    row_factory: bool = True,
    wal: bool = True,
    busy_timeout: int | None = 5000,
) -> sqlite3.Connection:
    """Open a SQLite connection using a resolved path with safety guards."""
    if resolution.purpose == "write":
        print_db_provenance(resolution)
        _check_writable_db_path(
            resolution.path,
            exists=resolution.exists,
            allow_create=resolution.allow_create,
        )
        if not resolution.exists and resolution.allow_create:
            _ensure_parent_directory(resolution.path)

    if resolution.path.as_posix() == ":memory:":
        conn = sqlite3.connect(":memory:")
    elif resolution.purpose == "read":
        conn = sqlite3.connect(
            _sqlite_uri(resolution.path, "ro") + "&immutable=1",
            uri=True,
        )
    else:
        mode = "rwc" if resolution.allow_create else "rw"
        conn = sqlite3.connect(_sqlite_uri(resolution.path, mode), uri=True)

    if row_factory:
        conn.row_factory = sqlite3.Row
    if resolution.purpose == "write":
        with conn:
            if wal:
                conn.execute("PRAGMA journal_mode=WAL")
            if busy_timeout is not None:
                conn.execute(f"PRAGMA busy_timeout={int(busy_timeout)}")
    return conn
