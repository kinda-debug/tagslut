"""
Environment-aware path resolution for tagslut.

All paths should come from environment variables or this module,
never hardcoded in scripts.

Usage:
    from tagslut.utils.env_paths import get_db_path, get_volume

    db = get_db_path()
    library = get_volume("library")
"""
import os
import warnings
from pathlib import Path
from typing import Optional

_DOTENV_LOADED = False

_CANONICAL_VOLUME_ENV_VARS: dict[str, tuple[str, ...]] = {
    "library": ("LIBRARY_ROOT", "MASTER_LIBRARY", "VOLUME_LIBRARY"),
    "staging": ("STAGING_ROOT", "VOLUME_STAGING"),
    "quarantine": ("QUARANTINE_ROOT", "VOLUME_QUARANTINE"),
    "work": ("WORK_ROOT", "VOLUME_WORK"),
}

_LEGACY_ENV_NAMES: dict[str, tuple[str, ...]] = {
    "VOLUME_LIBRARY": ("LIBRARY_ROOT", "MASTER_LIBRARY"),
    "VOLUME_QUARANTINE": ("QUARANTINE_ROOT",),
    "VOLUME_WORK": ("WORK_ROOT",),
}


class PathNotConfiguredError(Exception):
    """Raised when a required path is not configured"""
    pass


def _load_dotenv_once() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True

    dotenv_path = None
    repo_root = Path(__file__).resolve().parents[2]
    try:
        from dotenv import find_dotenv, load_dotenv
        dotenv_path = find_dotenv(usecwd=True)
        if not dotenv_path:
            candidate = repo_root / ".env"
            if candidate.exists():
                dotenv_path = str(candidate)
        if dotenv_path:
            load_dotenv(dotenv_path=dotenv_path, override=False)
        return
    except Exception:
        pass

    candidate = repo_root / ".env"
    if not candidate.exists():
        return
    _load_simple_dotenv(candidate)


def _load_simple_dotenv(dotenv_path: Path) -> None:
    """Minimal .env loader for environments without python-dotenv."""
    try:
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = os.path.expandvars(os.path.expanduser(value))


def _get_env(var: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Get environment variable with validation"""
    _load_dotenv_once()
    value = os.getenv(var, default)

    if value is None and required:
        raise PathNotConfiguredError(
            f"Required environment variable {var} not set.\n"
            f"Copy .env.example to .env and configure your paths."
        )

    return value


def _warn_legacy_env(legacy: str, preferred: tuple[str, ...]) -> None:
    preferred_text = " or ".join(preferred)
    warnings.warn(
        f"{legacy} is deprecated; use {preferred_text} instead.",
        DeprecationWarning,
        stacklevel=3,
    )


def _expand_path(value: Optional[str]) -> Optional[Path]:
    """Expand environment variables and user home directory in path"""
    if value is None:
        return None

    expanded = os.path.expanduser(os.path.expandvars(value))
    return Path(expanded)


def _env_flag(name: str, default: str = "true") -> bool:
    value = _get_env(name, default=default)
    return (value or default).lower() in ("true", "1", "yes")


# ============================================================================
# DATABASE
# ============================================================================

def get_db_path() -> Optional[Path]:
    """Get database path from environment."""
    path = _get_env("TAGSLUT_DB", required=False)
    return _expand_path(path)


# ============================================================================
# VOLUMES
# ============================================================================

def get_volume(name: str, required: bool = False) -> Optional[Path]:
    """
    Get volume path by name.

    Args:
        name: Volume name (library, staging, vault, recovery, quarantine)
        required: Raise error if not configured

    Returns:
        Path to volume or None if not configured
    """
    aliases = _CANONICAL_VOLUME_ENV_VARS.get(name, (f"VOLUME_{name.upper()}",))
    value: Optional[str] = None

    for env_var in aliases:
        candidate = _get_env(env_var, required=False)
        if candidate is None:
            continue
        if env_var in _LEGACY_ENV_NAMES:
            _warn_legacy_env(env_var, _LEGACY_ENV_NAMES[env_var])
        value = candidate
        break

    if value is None and required:
        raise PathNotConfiguredError(
            f"Required environment variable for volume '{name}' not set.\n"
            f"Tried: {', '.join(aliases)}"
        )

    return _expand_path(value)


def get_library_volume() -> Path:
    """Get primary library volume (required)"""
    volume = get_volume("library", required=True)
    if volume is None:
        raise PathNotConfiguredError("Required environment variable for volume 'library' not set.")
    return volume


def get_staging_volume() -> Optional[Path]:
    """Get staging volume (optional)"""
    return get_volume("staging")


def get_vault_volume() -> Optional[Path]:
    """Get vault volume (optional)"""
    return get_volume("vault")


def get_recovery_volume() -> Optional[Path]:
    """Get recovery volume (optional)"""
    return get_volume("recovery")


def get_quarantine_volume() -> Optional[Path]:
    """Get quarantine volume (optional)"""
    return get_volume("quarantine")


# ============================================================================
# ARTIFACTS & REPORTS
# ============================================================================

def get_artifacts_dir() -> Path:
    """Get artifacts directory"""
    path = _get_env("TAGSLUT_ARTIFACTS", default="./artifacts")
    expanded = _expand_path(path)
    if expanded is None:
        raise PathNotConfiguredError("TAGSLUT_ARTIFACTS resolved to an empty path.")
    return expanded


def get_reports_dir() -> Path:
    """Get reports directory"""
    default = str(get_artifacts_dir() / "M" / "03_reports")
    path = _get_env("TAGSLUT_REPORTS", default=default)
    expanded = _expand_path(path)
    if expanded is None:
        raise PathNotConfiguredError("TAGSLUT_REPORTS resolved to an empty path.")
    return expanded


def get_log_path(name: str) -> Path:
    """Get path for a named log file"""
    return get_reports_dir() / name


# ============================================================================
# SCAN SETTINGS
# ============================================================================

def get_scan_workers() -> int:
    """Get number of scan workers"""
    return int(_get_env("SCAN_WORKERS", default="8") or "8")


def get_scan_progress_interval() -> int:
    """Get scan progress reporting interval"""
    return int(_get_env("SCAN_PROGRESS_INTERVAL", default="100") or "100")


def get_scan_check_integrity() -> bool:
    """Check if integrity validation is enabled"""
    return _env_flag("SCAN_CHECK_INTEGRITY")


def get_scan_check_hash() -> bool:
    """Check if hash calculation is enabled"""
    return _env_flag("SCAN_CHECK_HASH")


def get_scan_incremental() -> bool:
    """Check if incremental scanning is enabled"""
    return _env_flag("SCAN_INCREMENTAL")


# ============================================================================
# DECISION SETTINGS
# ============================================================================

def get_auto_approve_threshold() -> float:
    """Get auto-approval confidence threshold"""
    return float(_get_env("AUTO_APPROVE_THRESHOLD", default="0.95") or "0.95")


def get_quarantine_retention_days() -> int:
    """Get quarantine retention period in days"""
    return int(_get_env("QUARANTINE_RETENTION_DAYS", default="30") or "30")


def get_prefer_high_bitrate() -> bool:
    """Check if high bitrate is preferred"""
    return _env_flag("PREFER_HIGH_BITRATE")


def get_prefer_high_sample_rate() -> bool:
    """Check if high sample rate is preferred"""
    return _env_flag("PREFER_HIGH_SAMPLE_RATE")


def get_prefer_valid_integrity() -> bool:
    """Check if valid integrity is preferred"""
    return _env_flag("PREFER_VALID_INTEGRITY")


# ============================================================================
# VALIDATION
# ============================================================================

def validate_paths() -> list[str]:
    """
    Validate all configured paths exist.

    Returns:
        List of error messages (empty if all valid)
    """
    errors = []

    # Check required paths
    try:
        db_path = get_db_path()
        if db_path and not db_path.parent.exists():
            errors.append(f"Database directory does not exist: {db_path.parent}")
    except PathNotConfiguredError as e:
        errors.append(str(e))

    # Check optional volume paths
    for vol_name in ["library", "staging", "vault", "recovery", "quarantine"]:
        vol_path = get_volume(vol_name)
        if vol_path and not vol_path.exists():
            errors.append(f"Volume '{vol_name}' does not exist: {vol_path}")

    return errors


def print_config() -> None:
    """Print current configuration (for debugging)"""
    print("=== Dedupe Configuration ===")
    print(f"Database:    {get_db_path()}")
    print(f"Artifacts:   {get_artifacts_dir()}")
    print(f"Reports:     {get_reports_dir()}")
    print()
    print("Volumes:")
    for vol in ["library", "staging", "vault", "recovery", "quarantine"]:
        path = get_volume(vol)
        status = "✓" if path and path.exists() else "✗" if path else "-"
        print(f"  {status} {vol:12} {path or '(not configured)'}")
    print()
    print("Scan Settings:")
    print(f"  Workers:     {get_scan_workers()}")
    print(f"  Integrity:   {get_scan_check_integrity()}")
    print(f"  Hash:        {get_scan_check_hash()}")
    print(f"  Incremental: {get_scan_incremental()}")


if __name__ == "__main__":
    # Test configuration
    print_config()

    errors = validate_paths()
    if errors:
        print("\n⚠️  Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("\n✓ Configuration valid")
