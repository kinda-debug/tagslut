"""Phase 2 policy + deterministic planning coverage."""

from __future__ import annotations

from tagslut.decide import PlanCandidate, build_deterministic_plan
from tagslut.policy import lint_policy_profile, list_policy_profiles, load_policy_profile


def _sample_candidates() -> list[PlanCandidate]:
    return [
        PlanCandidate(
            path="/Volumes/MUSIC/INTAKE/03-c.flac",
            context={"origin": "batch_a", "rank": 3},
        ),
        PlanCandidate(
            path="/Volumes/MUSIC/INTAKE/01-a.flac",
            match_reasons=("isrc",),
            context={"origin": "batch_a", "rank": 1},
        ),
        PlanCandidate(
            path="/Volumes/MUSIC/INTAKE/02-b.flac",
            proposed_action="promote",
            proposed_reason="trusted_source",
            is_dj_material=True,
            duration_status="warn",
            context={"origin": "batch_a", "rank": 2},
        ),
    ]


def test_policy_profiles_list_includes_phase2_baseline() -> None:
    names = set(list_policy_profiles())
    assert {"dj_strict", "library_balanced", "bulk_recovery"} <= names


def test_builtin_policy_profiles_pass_lint() -> None:
    for profile_name in ("dj_strict", "library_balanced", "bulk_recovery"):
        policy = load_policy_profile(profile_name)
        issues = lint_policy_profile(policy)
        assert not issues, f"{profile_name} lint issues: {issues}"


def test_build_deterministic_plan_is_input_order_independent() -> None:
    policy = load_policy_profile("library_balanced")
    candidates = _sample_candidates()

    plan_a = build_deterministic_plan(candidates, policy, run_label="snapshot")
    plan_b = build_deterministic_plan(list(reversed(candidates)), policy, run_label="snapshot")

    assert plan_a.input_hash == plan_b.input_hash
    assert plan_a.plan_hash == plan_b.plan_hash
    assert plan_a.run_id == plan_b.run_id
    assert [row.path for row in plan_a.rows] == [row.path for row in plan_b.rows]
    assert [row.path for row in plan_a.rows] == sorted(row.path for row in plan_a.rows)


def test_dj_strict_duration_gate_blocks_non_ok_promote() -> None:
    policy = load_policy_profile("dj_strict")
    plan = build_deterministic_plan(
        [
            PlanCandidate(
                path="/Volumes/MUSIC/INTAKE/dj_warn.flac",
                proposed_action="promote",
                proposed_reason="manual_pick",
                is_dj_material=True,
                duration_status="warn",
            )
        ],
        policy,
        run_label="snapshot",
    )

    assert len(plan.rows) == 1
    assert plan.rows[0].action == "review"
    assert plan.rows[0].reason == "duration_gate:warn"
    assert plan.policy_version == policy.version
    assert plan.run_id.startswith("snapshot-dj_strict-")


def test_phase2_golden_plan_hashes() -> None:
    expected = {
        "dj_strict": {
            "actions": ["skip", "review", "keep"],
            "plan_hash": "8acc2a0185978d87d8a6d4bc3441f78e7a7904e5efef5efa8cec7f01b464ce59",
        },
        "library_balanced": {
            "actions": ["skip", "promote", "keep"],
            "plan_hash": "d08986c04d168fe3b241497129dd205711a5ebe453587164251cc2326736dc40",
        },
        "bulk_recovery": {
            "actions": ["review", "promote", "promote"],
            "plan_hash": "a703ca4e3019122eb17b99cf4712a6e7568f47bf2cf9e5ee3f186aec8365fcd2",
        },
    }

    for profile_name, spec in expected.items():
        policy = load_policy_profile(profile_name)
        plan = build_deterministic_plan(_sample_candidates(), policy, run_label="golden")
        assert [row.action for row in plan.rows] == spec["actions"]
        assert plan.policy_version == policy.version
        assert plan.run_id.startswith(f"golden-{profile_name}-")
        assert plan.plan_hash == spec["plan_hash"]
