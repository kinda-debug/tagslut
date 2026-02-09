"""Deterministic planning API for policy-evaluated actions."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from typing import Any, Iterable, Mapping

from dedupe.policy.models import ALLOWED_ACTIONS, PolicyProfile


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _norm_text(item)
            if text:
                return text
        return ""
    return str(value).strip()


def _norm_action(value: Any) -> str:
    action = _norm_text(value).lower()
    if action in ALLOWED_ACTIONS:
        return action
    return ""


def _norm_status(value: Any) -> str:
    status = _norm_text(value).lower()
    return status or "unknown"


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, os.PathLike):
        return str(value)
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value.keys(), key=lambda item: str(item)):
            normalized[str(key)] = _json_safe(value[key])
        return normalized
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


@dataclass(frozen=True)
class PlanCandidate:
    """Single candidate row evaluated by the deterministic planner."""

    path: str
    proposed_action: str | None = None
    proposed_reason: str | None = None
    match_reasons: tuple[str, ...] = ()
    is_dj_material: bool = False
    duration_status: str | None = None
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanRow:
    """Deterministic output row."""

    row_index: int
    path: str
    action: str
    reason: str
    match_reasons: tuple[str, ...]
    proposed_action: str | None
    proposed_reason: str | None
    is_dj_material: bool
    duration_status: str
    context: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "path": self.path,
            "action": self.action,
            "reason": self.reason,
            "match_reasons": list(self.match_reasons),
            "proposed_action": self.proposed_action,
            "proposed_reason": self.proposed_reason,
            "is_dj_material": self.is_dj_material,
            "duration_status": self.duration_status,
            "context": self.context,
        }


@dataclass(frozen=True)
class DeterministicPlan:
    """Policy-stamped deterministic plan artifact."""

    run_id: str
    policy_name: str
    policy_version: str
    policy_hash: str
    input_hash: str
    plan_hash: str
    rows: tuple[PlanRow, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_version": 1,
            "run_id": self.run_id,
            "input_hash": self.input_hash,
            "plan_hash": self.plan_hash,
            "policy": {
                "name": self.policy_name,
                "version": self.policy_version,
                "hash": self.policy_hash,
            },
            "rows": [row.to_dict() for row in self.rows],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"


def _normalized_candidate(candidate: PlanCandidate) -> dict[str, Any]:
    match_reasons = sorted(
        {
            _norm_text(value).lower()
            for value in candidate.match_reasons
            if _norm_text(value)
        }
    )
    context = _json_safe(dict(candidate.context))
    if not isinstance(context, dict):
        context = {"value": context}
    context_hash = _stable_hash(context)
    return {
        "path": _norm_text(candidate.path),
        "proposed_action": _norm_action(candidate.proposed_action),
        "proposed_reason": _norm_text(candidate.proposed_reason),
        "match_reasons": tuple(match_reasons),
        "is_dj_material": bool(candidate.is_dj_material),
        "duration_status": _norm_status(candidate.duration_status),
        "context": context,
        "context_hash": context_hash,
    }


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return (
        candidate["path"],
        candidate["proposed_action"],
        candidate["proposed_reason"],
        candidate["match_reasons"],
        candidate["is_dj_material"],
        candidate["duration_status"],
        candidate["context_hash"],
    )


def _evaluate_action(policy: PolicyProfile, candidate: dict[str, Any]) -> tuple[str, str]:
    allowed_match = set(policy.match_rules.allow_match_by)
    matched_reason = next(
        (reason for reason in candidate["match_reasons"] if reason in allowed_match),
        None,
    )
    if matched_reason:
        action = policy.match_rules.duplicate_action
        reason = f"duplicate_match:{matched_reason}"
    elif candidate["proposed_action"]:
        action = candidate["proposed_action"]
        reason = candidate["proposed_reason"] or "proposed_action"
    else:
        action = policy.match_rules.unmatched_action
        reason = "no_duplicate_match"

    if (
        candidate["is_dj_material"]
        and policy.duration_rules.require_ok_for_dj_promotion
        and action in {"keep", "promote"}
        and candidate["duration_status"] not in policy.duration_rules.ok_statuses
    ):
        action = policy.duration_rules.non_ok_action
        reason = f"duration_gate:{candidate['duration_status']}"

    return action, reason


def build_deterministic_plan(
    candidates: Iterable[PlanCandidate],
    policy: PolicyProfile,
    *,
    run_label: str = "decide",
) -> DeterministicPlan:
    normalized = [_normalized_candidate(candidate) for candidate in candidates]
    normalized.sort(key=_candidate_sort_key)

    input_payload = [
        {
            "path": item["path"],
            "proposed_action": item["proposed_action"],
            "proposed_reason": item["proposed_reason"],
            "match_reasons": list(item["match_reasons"]),
            "is_dj_material": item["is_dj_material"],
            "duration_status": item["duration_status"],
            "context": item["context"],
        }
        for item in normalized
    ]
    input_hash = _stable_hash(input_payload)

    rows: list[PlanRow] = []
    for index, candidate in enumerate(normalized, start=1):
        action, reason = _evaluate_action(policy, candidate)
        row = PlanRow(
            row_index=index,
            path=candidate["path"],
            action=action,
            reason=reason,
            match_reasons=tuple(candidate["match_reasons"]),
            proposed_action=candidate["proposed_action"] or None,
            proposed_reason=candidate["proposed_reason"] or None,
            is_dj_material=bool(candidate["is_dj_material"]),
            duration_status=candidate["duration_status"],
            context=dict(candidate["context"]),
        )
        rows.append(row)

    plan_payload = {
        "policy": {"name": policy.name, "version": policy.version, "hash": policy.source_hash},
        "rows": [row.to_dict() for row in rows],
    }
    plan_hash = _stable_hash(plan_payload)
    run_id = f"{run_label}-{policy.name}-{plan_hash[:12]}"

    return DeterministicPlan(
        run_id=run_id,
        policy_name=policy.name,
        policy_version=policy.version,
        policy_hash=policy.source_hash,
        input_hash=input_hash,
        plan_hash=plan_hash,
        rows=tuple(rows),
    )
