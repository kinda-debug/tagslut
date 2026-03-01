from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from tagslut.policy.models import (
    ALLOWED_ACTIONS,
    ALLOWED_COLLISION_POLICIES,
    ALLOWED_MATCH_KINDS,
    DurationRules,
    ExecutionRules,
    MatchRules,
    PolicyProfile,
)


def _sample_profile() -> PolicyProfile:
    return PolicyProfile(
        name="sample_policy",
        version="2026-02-09.sample.v1",
        description="Sample policy for tests",
        lane="library",
        match_rules=MatchRules(
            allow_match_by=("beatport_id", "isrc"),
            duplicate_action="skip",
            unmatched_action="keep",
            duration_margin_ms=4000,
        ),
        duration_rules=DurationRules(
            require_ok_for_dj_promotion=False,
            ok_statuses=("ok", "warn"),
            non_ok_action="review",
        ),
        execution_rules=ExecutionRules(collision_policy="skip"),
        source_path="/tmp/sample.yaml",
        source_hash="abc123",
    )


def test_policy_profile_to_dict_round_trip_like_shape() -> None:
    profile = _sample_profile()
    payload = profile.to_dict()

    rebuilt = PolicyProfile(
        name=str(payload["name"]),
        version=str(payload["version"]),
        description=str(payload["description"]),
        lane=str(payload["lane"]),
        match_rules=MatchRules(
            allow_match_by=tuple(payload["rules"]["match"]["allow_match_by"]),
            duplicate_action=str(payload["rules"]["match"]["duplicate_action"]),
            unmatched_action=str(payload["rules"]["match"]["unmatched_action"]),
            duration_margin_ms=int(payload["rules"]["match"]["duration_margin_ms"]),
        ),
        duration_rules=DurationRules(
            require_ok_for_dj_promotion=bool(
                payload["rules"]["duration"]["require_ok_for_dj_promotion"]
            ),
            ok_statuses=tuple(payload["rules"]["duration"]["ok_statuses"]),
            non_ok_action=str(payload["rules"]["duration"]["non_ok_action"]),
        ),
        execution_rules=ExecutionRules(
            collision_policy=str(payload["rules"]["execution"]["collision_policy"])
        ),
        source_path=str(payload["source_path"]),
        source_hash=str(payload["source_hash"]),
    )

    assert rebuilt == profile
    assert rebuilt.to_dict() == payload


def test_policy_profile_policy_id_is_deterministic() -> None:
    one = _sample_profile()
    two = PolicyProfile(
        name="sample_policy",
        version="2026-02-09.sample.v1",
        description="Different description",
        lane="dj",
        match_rules=one.match_rules,
        duration_rules=one.duration_rules,
        execution_rules=one.execution_rules,
        source_path="/other/path.yaml",
        source_hash="different",
    )

    assert one.policy_id == "sample_policy:2026-02-09.sample.v1"
    assert one.policy_id == two.policy_id


def test_policy_profile_is_frozen() -> None:
    profile = _sample_profile()
    with pytest.raises(FrozenInstanceError):
        profile.name = "new_name"  # type: ignore[misc]


def test_match_rules_is_frozen() -> None:
    rules = _sample_profile().match_rules
    with pytest.raises(FrozenInstanceError):
        rules.duration_margin_ms = 1000  # type: ignore[misc]


def test_duration_rules_is_frozen() -> None:
    rules = _sample_profile().duration_rules
    with pytest.raises(FrozenInstanceError):
        rules.non_ok_action = "keep"  # type: ignore[misc]


def test_execution_rules_is_frozen() -> None:
    rules = _sample_profile().execution_rules
    with pytest.raises(FrozenInstanceError):
        rules.collision_policy = "abort"  # type: ignore[misc]


def test_allowed_actions_contains_expected_values() -> None:
    assert {
        "archive",
        "keep",
        "promote",
        "quarantine",
        "replace",
        "review",
        "skip",
        "stash",
    } <= ALLOWED_ACTIONS


def test_allowed_collision_policies_contains_expected_values() -> None:
    assert {"abort", "replace", "skip"} <= ALLOWED_COLLISION_POLICIES


def test_allowed_match_kinds_contains_expected_values() -> None:
    assert {"artist_title_duration", "beatport_id", "isrc"} <= ALLOWED_MATCH_KINDS
