from pathlib import Path

from click.testing import CliRunner

from tagslut.cli.main import cli


def test_scan_help_shows_commands():
    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "--help"])
    assert result.exit_code == 0
    assert "enqueue" in result.output
    assert "run" in result.output
    assert "status" in result.output
    assert "issues" in result.output
    assert "report" in result.output


def test_enqueue_rejects_nonexistent_root():
    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "enqueue", "--root", "/definitely/missing/path"])
    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_enqueue_accepts_root_and_default_priority(monkeypatch):
    captured = {}

    def fake_enqueue(root: Path, priority: int) -> int:
        captured["root"] = root
        captured["priority"] = priority
        return 42

    monkeypatch.setattr("tagslut.cli.scan.enqueue_scan", fake_enqueue)

    runner = CliRunner()
    with runner.isolated_filesystem():
        root = Path("library")
        root.mkdir()
        result = runner.invoke(cli, ["scan", "enqueue", "--root", str(root)])

    assert result.exit_code == 0
    assert captured["priority"] == 5
    assert "Enqueued scan run 42" in result.output


def test_run_supports_optional_run_id_and_prints_progress(monkeypatch):
    def fake_run(run_id):
        assert run_id == 99
        return ["Starting", "Progress: 50%", "Progress: 100%", "Done"]

    monkeypatch.setattr("tagslut.cli.scan.run_scan_job", fake_run)

    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "run", "--run-id", "99"])
    assert result.exit_code == 0
    assert "Progress: 50%" in result.output
    assert "Progress: 100%" in result.output


def test_status_prints_summary_table(monkeypatch):
    def fake_status_rows():
        return [
            {
                "run_id": 7,
                "status": "RUNNING",
                "queued": 10,
                "done": 8,
                "failed": 1,
                "started_at": "2026-02-28T00:00:00",
            }
        ]

    monkeypatch.setattr("tagslut.cli.scan.get_status_rows", fake_status_rows)

    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "status"])
    assert result.exit_code == 0
    assert "run_id | status | queued | done | failed | started_at" in result.output
    assert "7 | RUNNING | 10 | 8 | 1" in result.output


def test_issues_and_report_output(monkeypatch):
    def fake_issues(run_id: int, severity):
        assert run_id == 5
        assert severity == "WARN"
        return [
            {"severity": "INFO", "issue_code": "ISRC_MISSING", "count": 3},
            {"severity": "ERROR", "issue_code": "CORRUPT_DECODE", "count": 2},
            {"severity": "WARN", "issue_code": "DURATION_MISMATCH", "count": 4},
        ]

    def fake_report(run_id: int):
        assert run_id == 5
        return (
            [
                {"issue_code": "CORRUPT_DECODE", "count": 2},
                {"issue_code": "ISRC_MISSING", "count": 3},
            ],
            9,
        )

    monkeypatch.setattr("tagslut.cli.scan.get_issue_rows", fake_issues)
    monkeypatch.setattr("tagslut.cli.scan.get_report_rows", fake_report)

    runner = CliRunner()
    issues_result = runner.invoke(cli, ["scan", "issues", "--run-id", "5", "--severity", "WARN"])
    assert issues_result.exit_code == 0
    lines = [line for line in issues_result.output.splitlines() if "|" in line]
    assert "severity | issue_code | count" in lines[0]
    assert lines[1].startswith("ERROR")

    report_result = runner.invoke(cli, ["scan", "report", "--run-id", "5"])
    assert report_result.exit_code == 0
    assert "CORRUPT_DECODE | 2" in report_result.output
    assert "FORMAT_DUPLICATE | 9" in report_result.output
