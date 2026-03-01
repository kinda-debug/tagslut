from __future__ import annotations

from pathlib import Path

import pytest

from tagslut.policy.loader import (
    PolicyValidationError,
    list_policy_profiles,
    load_builtin_policies,
    load_policy_profile,
)

CONFIG_POLICIES = Path(__file__).resolve().parents[2] / "config" / "policies"


def test_load_policy_profile_with_real_yaml() -> None:
    profile = load_policy_profile("library_balanced", policy_dir=CONFIG_POLICIES)

    assert profile.name == "library_balanced"
    assert profile.lane == "library"
    assert profile.match_rules.duplicate_action == "skip"
    assert Path(profile.source_path).name == "library_balanced.yaml"
    assert len(profile.source_hash) == 64


def test_load_policy_profile_invalid_yaml_raises_policy_validation_error(
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(PolicyValidationError, match="Policy payload must be a mapping"):
        load_policy_profile(str(invalid))


def test_load_policy_profile_missing_rules_raises_policy_validation_error(
    tmp_path: Path,
) -> None:
    missing_rules = tmp_path / "missing_rules.yaml"
    missing_rules.write_text(
        """
name: invalid
version: 1
lane: library
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(PolicyValidationError, match="Policy rules block missing"):
        load_policy_profile(str(missing_rules))


def test_list_policy_profiles_returns_known_builtins() -> None:
    profiles = list_policy_profiles(policy_dir=CONFIG_POLICIES)

    assert profiles == sorted(profiles)
    assert {"bulk_recovery", "dj_strict", "library_balanced"} <= set(profiles)


def test_list_policy_profiles_missing_directory_returns_empty(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    assert not missing.exists()

    assert list_policy_profiles(policy_dir=missing) == []


def test_load_builtin_policies_loads_all_without_error() -> None:
    profile_names = list_policy_profiles(policy_dir=CONFIG_POLICIES)
    loaded = load_builtin_policies(policy_dir=CONFIG_POLICIES)

    assert len(loaded) == len(profile_names)
    assert [profile.name for profile in loaded] == profile_names


def test_load_policy_profile_by_full_file_path() -> None:
    profile_path = CONFIG_POLICIES / "dj_strict.yaml"

    profile = load_policy_profile(str(profile_path), policy_dir=CONFIG_POLICIES)
    assert profile.name == "dj_strict"
    assert profile.execution_rules.collision_policy == "skip"
