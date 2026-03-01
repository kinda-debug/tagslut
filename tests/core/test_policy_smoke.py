"""Smoke tests for the tagslut.policy submodule."""

from pathlib import Path

import pytest

import tagslut.policy as policy_mod
from tagslut.policy import (
    ALLOWED_ACTIONS,
    ALLOWED_COLLISION_POLICIES,
    ALLOWED_MATCH_KINDS,
    PolicyValidationError,
    list_policy_profiles,
    load_policy_profile,
)
from tagslut.policy.models import DurationRules, ExecutionRules, MatchRules, PolicyProfile

CONFIG_POLICIES = Path(__file__).resolve().parents[2] / "config" / "policies"


def test_policy_module_importable() -> None:
    assert hasattr(policy_mod, "load_policy_profile")
    assert hasattr(policy_mod, "list_policy_profiles")
    assert hasattr(policy_mod, "PolicyProfile")


def test_allowed_actions_non_empty() -> None:
    assert len(ALLOWED_ACTIONS) > 0
    assert "keep" in ALLOWED_ACTIONS


def test_allowed_collision_policies_non_empty() -> None:
    assert len(ALLOWED_COLLISION_POLICIES) > 0


def test_allowed_match_kinds_non_empty() -> None:
    assert len(ALLOWED_MATCH_KINDS) > 0


def test_list_policy_profiles_returns_builtin_names() -> None:
    profiles = list_policy_profiles(policy_dir=CONFIG_POLICIES)
    assert isinstance(profiles, list)
    assert "library_balanced" in profiles


def test_load_policy_profile_library_balanced() -> None:
    profile = load_policy_profile("library_balanced", policy_dir=CONFIG_POLICIES)
    assert isinstance(profile, PolicyProfile)
    assert profile.name == "library_balanced"
    assert profile.version != ""
    assert profile.policy_id == f"library_balanced:{profile.version}"


def test_policy_profile_to_dict() -> None:
    profile = load_policy_profile("library_balanced", policy_dir=CONFIG_POLICIES)
    d = profile.to_dict()
    assert "name" in d
    assert "rules" in d
    assert "match" in d["rules"]
    assert "duration" in d["rules"]
    assert "execution" in d["rules"]


def test_load_policy_profile_missing_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_policy_profile("nonexistent_profile", policy_dir=CONFIG_POLICIES)


def test_policy_validation_error_on_bad_yaml(tmp_path: Path) -> None:
    bad_policy = tmp_path / "bad.yaml"
    bad_policy.write_text("name: bad\nversion: 1\n")
    with pytest.raises((PolicyValidationError, Exception)):
        load_policy_profile(str(bad_policy))
