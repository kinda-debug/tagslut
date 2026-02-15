"""Policy profile loader and validator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from tagslut.policy.models import (
    ALLOWED_ACTIONS,
    ALLOWED_COLLISION_POLICIES,
    ALLOWED_MATCH_KINDS,
    DurationRules,
    ExecutionRules,
    MatchRules,
    PolicyProfile,
)


class PolicyValidationError(ValueError):
    """Raised when a policy profile is missing required fields or values."""


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        return text if text else default
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _as_text(item, "")
            if text:
                return text
        return default
    text = str(value).strip()
    return text if text else default


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = _as_text(value, "").lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _as_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_action(value: Any, *, field_name: str) -> str:
    action = _as_text(value, "").lower()
    if not action:
        raise PolicyValidationError(f"Missing action for '{field_name}'")
    if action not in ALLOWED_ACTIONS:
        allowed = ", ".join(sorted(ALLOWED_ACTIONS))
        raise PolicyValidationError(
            f"Invalid action '{action}' for '{field_name}'. Allowed: {allowed}"
        )
    return action


def _normalize_collision_policy(value: Any) -> str:
    policy = _as_text(value, "skip").lower()
    if policy not in ALLOWED_COLLISION_POLICIES:
        allowed = ", ".join(sorted(ALLOWED_COLLISION_POLICIES))
        raise PolicyValidationError(
            f"Invalid collision_policy '{policy}'. Allowed: {allowed}"
        )
    return policy


def _normalize_match_kinds(value: Any) -> tuple[str, ...]:
    values = value if isinstance(value, list) else []
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in values:
        kind = _as_text(raw, "").lower()
        if not kind:
            continue
        if kind not in ALLOWED_MATCH_KINDS:
            allowed = ", ".join(sorted(ALLOWED_MATCH_KINDS))
            raise PolicyValidationError(
                f"Invalid match kind '{kind}'. Allowed: {allowed}"
            )
        if kind not in seen:
            seen.add(kind)
            ordered.append(kind)
    if not ordered:
        raise PolicyValidationError("rules.match.allow_match_by must not be empty")
    return tuple(ordered)


def _resolve_policy_dir(policy_dir: Path | None) -> Path:
    if policy_dir is not None:
        return policy_dir.expanduser().resolve()
    return (Path(__file__).resolve().parents[2] / "config" / "policies").resolve()


def list_policy_profiles(policy_dir: Path | None = None) -> list[str]:
    root = _resolve_policy_dir(policy_dir)
    if not root.exists():
        return []

    names: set[str] = set()
    for pattern in ("*.yaml", "*.yml"):
        for candidate in root.glob(pattern):
            if candidate.is_file():
                names.add(candidate.stem)
    return sorted(names)


def _resolve_policy_path(profile: str, policy_dir: Path | None = None) -> Path:
    raw = profile.strip()
    if not raw:
        raise PolicyValidationError("Policy profile name cannot be empty")

    direct = Path(raw).expanduser()
    if direct.suffix.lower() in {".yaml", ".yml"} and direct.exists():
        return direct.resolve()

    root = _resolve_policy_dir(policy_dir)
    for suffix in (".yaml", ".yml"):
        candidate = root / f"{raw}{suffix}"
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(f"Policy profile not found: {raw} (search root: {root})")


def load_policy_profile(profile: str, policy_dir: Path | None = None) -> PolicyProfile:
    path = _resolve_policy_path(profile, policy_dir)
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    if not isinstance(payload, dict):
        raise PolicyValidationError(f"Policy payload must be a mapping: {path}")

    name = _as_text(payload.get("name"), path.stem)
    if not name:
        raise PolicyValidationError(f"Policy name missing in {path}")

    version = _as_text(payload.get("version"), "")
    if not version:
        raise PolicyValidationError(f"Policy version missing in {path}")

    description = _as_text(payload.get("description"), "")
    lane = _as_text(payload.get("lane"), "library").lower()

    rules = payload.get("rules")
    if not isinstance(rules, dict):
        raise PolicyValidationError(f"Policy rules block missing in {path}")

    match_block = rules.get("match")
    if not isinstance(match_block, dict):
        raise PolicyValidationError(f"Policy rules.match block missing in {path}")
    duration_block = rules.get("duration")
    if not isinstance(duration_block, dict):
        raise PolicyValidationError(f"Policy rules.duration block missing in {path}")
    execution_block = rules.get("execution")
    if not isinstance(execution_block, dict):
        raise PolicyValidationError(f"Policy rules.execution block missing in {path}")

    match_rules = MatchRules(
        allow_match_by=_normalize_match_kinds(match_block.get("allow_match_by")),
        duplicate_action=_normalize_action(
            match_block.get("duplicate_action"),
            field_name="rules.match.duplicate_action",
        ),
        unmatched_action=_normalize_action(
            match_block.get("unmatched_action"),
            field_name="rules.match.unmatched_action",
        ),
        duration_margin_ms=max(0, _as_int(match_block.get("duration_margin_ms"), 4000)),
    )

    ok_statuses_raw = duration_block.get("ok_statuses", ["ok"])
    if not isinstance(ok_statuses_raw, list):
        raise PolicyValidationError("rules.duration.ok_statuses must be a list")
    ok_statuses: list[str] = []
    for raw_status in ok_statuses_raw:
        status = _as_text(raw_status, "").lower()
        if status and status not in ok_statuses:
            ok_statuses.append(status)
    if not ok_statuses:
        raise PolicyValidationError("rules.duration.ok_statuses must include at least one status")

    duration_rules = DurationRules(
        require_ok_for_dj_promotion=_as_bool(
            duration_block.get("require_ok_for_dj_promotion"),
            False,
        ),
        ok_statuses=tuple(ok_statuses),
        non_ok_action=_normalize_action(
            duration_block.get("non_ok_action"),
            field_name="rules.duration.non_ok_action",
        ),
    )

    execution_rules = ExecutionRules(
        collision_policy=_normalize_collision_policy(execution_block.get("collision_policy")),
    )

    source_hash = _stable_hash(payload)
    return PolicyProfile(
        name=name,
        version=version,
        description=description,
        lane=lane,
        match_rules=match_rules,
        duration_rules=duration_rules,
        execution_rules=execution_rules,
        source_path=str(path),
        source_hash=source_hash,
    )


def load_builtin_policies(policy_dir: Path | None = None) -> list[PolicyProfile]:
    return [
        load_policy_profile(name, policy_dir=policy_dir)
        for name in list_policy_profiles(policy_dir)
    ]
