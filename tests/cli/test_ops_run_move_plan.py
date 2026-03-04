from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tagslut.cli.main import cli
from tagslut.cli.commands import ops as ops_commands


def _doctor_counts() -> dict[str, int]:
    return {
        "asset_file_total": 1,
        "asset_link_total": 1,
        "track_identity_total": 1,
        "integrity_done": 1,
        "sha256_done": 1,
        "enriched_done": 1,
    }


def _write_plan(path: Path, *, headers: str = "action,path,dest_path") -> Path:
    source = path.parent / "source.flac"
    source.write_bytes(b"test")
    dest = path.parent / "dest.flac"
    path.write_text(
        f"{headers}\nMOVE,{source},{dest}\n",
        encoding="utf-8",
    )
    return path


def test_ops_run_move_plan_requires_db_when_cli_and_env_missing(tmp_path, monkeypatch) -> None:
    plan = _write_plan(tmp_path / "plan.csv")
    monkeypatch.delenv("TAGSLUT_DB", raising=False)

    runner = CliRunner()
    result = runner.invoke(cli, ["ops", "run-move-plan", str(plan)])

    assert result.exit_code != 0
    assert "No database path provided" in result.output


def test_ops_run_move_plan_refuses_when_preflight_fails(tmp_path, monkeypatch) -> None:
    plan = _write_plan(tmp_path / "plan.csv")
    db_path = tmp_path / "music_v3.db"
    db_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("TAGSLUT_DB", str(db_path))

    def fake_doctor(_db_path: Path, *, strict: bool) -> ops_commands.DoctorRunResult:
        return ops_commands.DoctorRunResult(
            exit_code=1,
            stdout="doctor failure",
            stderr="",
            counts=_doctor_counts(),
        )

    called = {"executor": 0}

    def fake_executor(*, plan_path: Path, db_path: Path, dry_run: bool) -> ops_commands.ExecutorRunResult:
        called["executor"] += 1
        return ops_commands.ExecutorRunResult(
            exit_code=0,
            stdout="",
            stderr="",
            receipts=None,
            dry_run_supported=True,
        )

    monkeypatch.setattr(ops_commands, "_run_doctor", fake_doctor)
    monkeypatch.setattr(ops_commands, "_run_executor", fake_executor)

    runner = CliRunner()
    result = runner.invoke(cli, ["ops", "run-move-plan", str(plan)])

    assert result.exit_code != 0
    assert "preflight failed; refusing to execute moves" in result.output
    assert called["executor"] == 0


def test_ops_run_move_plan_validates_csv_headers(tmp_path, monkeypatch) -> None:
    plan = tmp_path / "bad_plan.csv"
    plan.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    db_path = tmp_path / "music_v3.db"
    db_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("TAGSLUT_DB", str(db_path))

    def fake_doctor(_db_path: Path, *, strict: bool) -> ops_commands.DoctorRunResult:
        return ops_commands.DoctorRunResult(
            exit_code=0,
            stdout="doctor ok",
            stderr="",
            counts=_doctor_counts(),
        )

    called = {"executor": 0}

    def fake_executor(*, plan_path: Path, db_path: Path, dry_run: bool) -> ops_commands.ExecutorRunResult:
        called["executor"] += 1
        return ops_commands.ExecutorRunResult(
            exit_code=0,
            stdout="",
            stderr="",
            receipts=None,
            dry_run_supported=True,
        )

    monkeypatch.setattr(ops_commands, "_run_doctor", fake_doctor)
    monkeypatch.setattr(ops_commands, "_run_executor", fake_executor)

    runner = CliRunner()
    result = runner.invoke(cli, ["ops", "run-move-plan", str(plan)])

    assert result.exit_code != 0
    assert "Plan CSV must include either headers" in result.output
    assert called["executor"] == 0


def test_ops_run_move_plan_runs_postflight_when_executor_fails(tmp_path, monkeypatch) -> None:
    plan = _write_plan(tmp_path / "plan.csv")
    db_path = tmp_path / "music_v3.db"
    db_path.write_text("", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    archive_dir = tmp_path / "archive"
    monkeypatch.setenv("TAGSLUT_DB", str(db_path))

    doctor_calls: list[int] = []

    def fake_doctor(_db_path: Path, *, strict: bool) -> ops_commands.DoctorRunResult:
        doctor_calls.append(1)
        return ops_commands.DoctorRunResult(
            exit_code=0,
            stdout="doctor ok",
            stderr="",
            counts=_doctor_counts(),
        )

    def fake_executor(*, plan_path: Path, db_path: Path, dry_run: bool) -> ops_commands.ExecutorRunResult:
        return ops_commands.ExecutorRunResult(
            exit_code=7,
            stdout="executor stdout",
            stderr="executor stderr",
            receipts=None,
            dry_run_supported=True,
        )

    monkeypatch.setattr(ops_commands, "_run_doctor", fake_doctor)
    monkeypatch.setattr(ops_commands, "_run_executor", fake_executor)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "ops",
            "run-move-plan",
            str(plan),
            "--receipt-out",
            str(receipt),
            "--plan-archive-dir",
            str(archive_dir),
        ],
    )

    assert result.exit_code != 0
    assert "move-plan execution failed" in result.output
    assert len(doctor_calls) == 2


def test_ops_run_move_plan_writes_receipt_with_expected_keys(tmp_path, monkeypatch) -> None:
    plan = _write_plan(tmp_path / "plan.csv")
    db_path = tmp_path / "music_v3.db"
    db_path.write_text("", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    archive_dir = tmp_path / "archive"
    monkeypatch.setenv("TAGSLUT_DB", str(db_path))

    doctor_calls = {"count": 0}

    def fake_doctor(_db_path: Path, *, strict: bool) -> ops_commands.DoctorRunResult:
        doctor_calls["count"] += 1
        counts = _doctor_counts()
        counts["asset_file_total"] = doctor_calls["count"]
        return ops_commands.DoctorRunResult(
            exit_code=0,
            stdout="doctor ok",
            stderr="",
            counts=counts,
        )

    def fake_executor(*, plan_path: Path, db_path: Path, dry_run: bool) -> ops_commands.ExecutorRunResult:
        return ops_commands.ExecutorRunResult(
            exit_code=0,
            stdout="executor ok",
            stderr="",
            receipts=None,
            dry_run_supported=True,
        )

    monkeypatch.setattr(ops_commands, "_run_doctor", fake_doctor)
    monkeypatch.setattr(ops_commands, "_run_executor", fake_executor)
    monkeypatch.setattr(ops_commands, "_git_commit_hash", lambda: "deadbeef")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "ops",
            "run-move-plan",
            str(plan),
            "--receipt-out",
            str(receipt),
            "--plan-archive-dir",
            str(archive_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert receipt.exists()

    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["plan_row_count"] == 1
    assert payload["executor_exit_code"] == 0
    assert payload["db_path"] == str(db_path)
    assert payload["plan_csv_path"] == str(plan.resolve())
    assert payload["doctor_pre_counts"]
    assert payload["doctor_post_counts"]
    assert payload["sample_moves"]
    assert payload["git_commit_hash"] == "deadbeef"

