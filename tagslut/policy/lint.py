"""Policy lint rules for Phase 2 profiles."""

from __future__ import annotations

from tagslut.policy.models import PolicyProfile


def lint_policy_profile(policy: PolicyProfile) -> list[str]:
    issues: list[str] = []

    if policy.lane == "dj" and not policy.duration_rules.require_ok_for_dj_promotion:
        issues.append(
            f"{policy.name}: DJ policies must require duration_status=ok for promotion"
        )

    if policy.lane == "dj" and policy.duration_rules.non_ok_action in {"keep", "promote"}:
        issues.append(
            f"{policy.name}: DJ policies cannot keep/promote non-ok duration rows"
        )

    if (
        policy.duration_rules.require_ok_for_dj_promotion
        and "ok" not in policy.duration_rules.ok_statuses
    ):
        issues.append(
            f"{policy.name}: ok_statuses must include 'ok' when duration gate is enabled"
        )

    if policy.lane == "dj" and policy.execution_rules.collision_policy == "replace":
        issues.append(
            f"{policy.name}: collision_policy=replace is not allowed for DJ lane"
        )

    if not policy.match_rules.allow_match_by:
        issues.append(f"{policy.name}: allow_match_by cannot be empty")

    return issues
