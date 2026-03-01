from pathlib import Path

from tagslut.utils.validators import PreFlightValidator


def test_validate_fails_when_plan_file_missing(tmp_path: Path) -> None:
    validator = PreFlightValidator(
        quarantine_root=tmp_path / "quarantine",
        plan_path=tmp_path / "missing.plan.jsonl",
        db_path=None,
        execute=False,
    )

    ok = validator.validate()

    assert ok is False
    assert any("Plan file not found" in err for err in validator.get_errors())


def test_validate_execute_true_checks_quarantine_parent_exists(tmp_path: Path) -> None:
    plan = tmp_path / "plan.jsonl"
    plan.write_text("{}", encoding="utf-8")
    missing_parent = tmp_path / "missing" / "subdir" / "quarantine"

    validator = PreFlightValidator(
        quarantine_root=missing_parent,
        plan_path=plan,
        db_path=None,
        execute=True,
    )

    ok = validator.validate()

    assert ok is False
    assert any("parent directory does not exist" in err for err in validator.get_errors())


def test_validate_happy_path_for_execute_mode(tmp_path: Path) -> None:
    plan = tmp_path / "plan.jsonl"
    plan.write_text("{}", encoding="utf-8")
    quarantine_root = tmp_path / "quarantine"
    quarantine_root.mkdir()

    validator = PreFlightValidator(
        quarantine_root=quarantine_root,
        plan_path=plan,
        db_path=str(tmp_path / "db.sqlite"),
        execute=True,
    )

    ok = validator.validate()

    assert ok is True
    assert validator.get_errors() == []
