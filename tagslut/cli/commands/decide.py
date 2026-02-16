from __future__ import annotations

from pathlib import Path

import click


def register_decide_group(cli: click.Group) -> None:
    @cli.group()
    def decide():
        """Canonical deterministic planning commands."""

    @decide.command("profiles")
    def decide_profiles():
        """List available policy profiles."""
        from tagslut.policy import list_policy_profiles, load_policy_profile

        names = list_policy_profiles()
        if not names:
            click.echo("No policy profiles found.")
            return
        click.echo("Policy profiles:")
        for name in names:
            profile = load_policy_profile(name)
            click.echo(f"  - {profile.name} ({profile.version}) lane={profile.lane}")

    @decide.command("plan")
    @click.option("--policy", default="library_balanced", show_default=True, help="Policy profile name")
    @click.option("--input", "input_path", type=click.Path(exists=True), required=True, help="Input JSON candidates file")
    @click.option("--output", "output_path", type=click.Path(), help="Output JSON plan path")
    @click.option("--run-label", default="decide", show_default=True, help="Run label prefix")
    def decide_plan(policy, input_path, output_path, run_label):
        """Build deterministic policy-stamped plan from candidate JSON."""
        import json

        from tagslut.decide import PlanCandidate, build_deterministic_plan
        from tagslut.policy import load_policy_profile

        payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            raw_candidates = payload.get("candidates", [])
        elif isinstance(payload, list):
            raw_candidates = payload
        else:
            raise click.ClickException("Input JSON must be a list or {'candidates': [...]} object")

        if not isinstance(raw_candidates, list):
            raise click.ClickException("Input candidates must be a JSON list")

        candidates: list[PlanCandidate] = []
        for idx, item in enumerate(raw_candidates, start=1):
            if not isinstance(item, dict):
                raise click.ClickException(f"Candidate #{idx} must be a JSON object")
            path = str(item.get("path", "")).strip()
            if not path:
                raise click.ClickException(f"Candidate #{idx} missing required 'path'")
            match_reasons = item.get("match_reasons", ())
            if isinstance(match_reasons, str):
                match_reasons = [match_reasons]
            if not isinstance(match_reasons, list):
                match_reasons = []
            candidates.append(
                PlanCandidate(
                    path=path,
                    proposed_action=item.get("proposed_action"),
                    proposed_reason=item.get("proposed_reason"),
                    match_reasons=tuple(str(v) for v in match_reasons),
                    is_dj_material=bool(item.get("is_dj_material", False)),
                    duration_status=item.get("duration_status"),
                    context=item.get("context", {}) if isinstance(item.get("context"), dict) else {},
                )
            )

        policy_profile = load_policy_profile(policy)
        plan = build_deterministic_plan(candidates, policy_profile, run_label=run_label)
        serialized = plan.to_json(indent=2)
        if output_path:
            output_file = Path(output_path).expanduser().resolve()
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(serialized, encoding="utf-8")
            click.echo(f"Wrote plan: {output_file}")
        else:
            click.echo(serialized.rstrip())
        click.echo(f"Plan hash: {plan.plan_hash}")
        click.echo(f"Run id: {plan.run_id}")
