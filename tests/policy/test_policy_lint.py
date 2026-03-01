from __future__ import annotations

from tagslut.policy.lint import lint_policy_profile
from tagslut.policy.models import DurationRules, ExecutionRules, MatchRules, PolicyProfile


def _policy(
    *,
    name: str = "profile",
    lane: str = "library",
    allow_match_by: tuple[str, ...] = ("isrc",),
    require_ok_for_dj_promotion: bool = False,
    ok_statuses: tuple[str, ...] = ("ok",),
    non_ok_action: str = "review",
    collision_policy: str = "skip",
) -> PolicyProfile:
    return PolicyProfile(
        name=name,
        version="2026-02-09.test.v1",
        description="lint profile",
        lane=lane,
        match_rules=MatchRules(
            allow_match_by=allow_match_by,
            duplicate_action="skip",
            unmatched_action="keep",
            duration_margin_ms=4000,
        ),
        duration_rules=DurationRules(
            require_ok_for_dj_promotion=require_ok_for_dj_promotion,
            ok_statuses=ok_statuses,
            non_ok_action=non_ok_action,
        ),
        execution_rules=ExecutionRules(collision_policy=collision_policy),
        source_path="/tmp/test.yaml",
        source_hash="hash",
    )


def test_lint_valid_profile_returns_empty_list() -> None:
    profile = _policy(name="valid_library")
    assert lint_policy_profile(profile) == []


def test_lint_dj_requires_duration_gate_issue() -> None:
    profile = _policy(name="dj_missing_gate", lane="dj", require_ok_for_dj_promotion=False)

    issues = lint_policy_profile(profile)
    assert any("must require duration_status=ok" in issue for issue in issues)


def test_lint_dj_non_ok_keep_issues() -> None:
    profile = _policy(name="dj_keep_non_ok", lane="dj", non_ok_action="keep")

    issues = lint_policy_profile(profile)
    assert any("cannot keep/promote non-ok" in issue for issue in issues)


def test_lint_dj_non_ok_promote_issues() -> None:
    profile = _policy(name="dj_promote_non_ok", lane="dj", non_ok_action="promote")

    issues = lint_policy_profile(profile)
    assert any("cannot keep/promote non-ok" in issue for issue in issues)


def test_lint_gate_enabled_requires_ok_status() -> None:
    profile = _policy(
        name="missing_ok_status",
        lane="library",
        require_ok_for_dj_promotion=True,
        ok_statuses=("warn", "unknown"),
    )

    issues = lint_policy_profile(profile)
    assert any("ok_statuses must include 'ok'" in issue for issue in issues)


def test_lint_dj_replace_collision_policy_issue() -> None:
    profile = _policy(name="dj_replace_collision", lane="dj", collision_policy="replace")

    issues = lint_policy_profile(profile)
    assert any("collision_policy=replace is not allowed" in issue for issue in issues)


def test_lint_empty_allow_match_by_issue() -> None:
    profile = _policy(name="no_match_kinds", allow_match_by=())

    issues = lint_policy_profile(profile)
    assert any("allow_match_by cannot be empty" in issue for issue in issues)


def test_lint_multiple_issues_accumulate() -> None:
    profile = _policy(
        name="many_issues",
        lane="dj",
        allow_match_by=(),
        require_ok_for_dj_promotion=False,
        non_ok_action="promote",
        collision_policy="replace",
    )

    issues = lint_policy_profile(profile)
    assert len(issues) == 4
