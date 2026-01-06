import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dedupe.utils.config import get_config, Config

logger = logging.getLogger("dedupe")


@dataclass(frozen=True)
class DbResolution:
    path: Path
    source: str
    candidates: list[tuple[str, Optional[str]]]


def _normalize_db_value(value: str | Path) -> Path:
    path = Path(value).expanduser()
    try:
        return path.resolve(strict=False)
    except TypeError:
        # Python <3.9 doesn't support strict arg; fallback to default resolve.
        return path.resolve()


def resolve_db_path(
    cli_db: Optional[str | Path],
    *,
    config: Optional[Config] = None,
    require: bool = True,
    allow_repo_db: bool = False,
    repo_root: Optional[Path] = None,
    purpose: str = "write",
) -> DbResolution:
    """Resolve the SQLite DB path based on CLI/env/config precedence."""
    config = config or get_config()
    env_db = os.getenv("DEDUPE_DB")
    config_db = config.get("db.path") if config else None

    candidates: list[tuple[str, Optional[str]]] = [
        ("cli", str(cli_db) if cli_db else None),
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
            raise ValueError(
                "No database path provided. Use --db, set DEDUPE_DB, or configure db.path."
            )
        raise ValueError("No database path provided.")

    db_path = _normalize_db_value(resolved_value)
    if db_path.exists() and db_path.is_dir():
        raise ValueError(f"Database path points to a directory: {db_path}")

    if purpose == "write" and repo_root:
        try:
            db_path.relative_to(repo_root)
        except ValueError:
            # Not under repo_root.
            pass
        else:
            if not allow_repo_db:
                raise ValueError(
                    f"Refusing to write to repo-local DB: {db_path}. "
                    f"Provide --allow-repo-db or choose a path outside {repo_root}."
                )

    logger.info("Resolved DB path: %s (source=%s)", db_path, source)
    return DbResolution(path=db_path, source=source, candidates=candidates)
