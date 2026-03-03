from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
import sys


def _load_snapshot_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "capture_post_release_snapshot.py"
    spec = importlib.util.spec_from_file_location("capture_post_release_snapshot", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_snapshot_script_writes_env_and_test_report(tmp_path: Path, monkeypatch) -> None:
    module = _load_snapshot_module()
    output_dir = tmp_path / "artifacts" / "v3.0.0"
    monkeypatch.setattr(module, "OUTPUT_DIR", output_dir)

    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture_output, text, check
        calls.append(args)
        if args[:4] == ["poetry", "run", "pytest", "tests"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="471 passed\n", stderr="")
        if args[:2] == ["python", "--version"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="Python 3.12.2\n", stderr="")
        if args[:2] == ["poetry", "--version"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="Poetry 2.1.0\n", stderr="")
        if args[:3] == ["poetry", "show", "tagslut"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="tagslut 3.0.0\n", stderr="")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.capture_post_release_snapshot(
        output_dir=module.OUTPUT_DIR,
        runner=module.subprocess.run,
    )

    assert result.env_snapshot_path.exists()
    assert result.test_report_path.exists()
    assert "Post-Release Environment Snapshot" in result.env_snapshot_path.read_text(encoding="utf-8")
    assert "471 passed" in result.test_report_path.read_text(encoding="utf-8")
    assert ["poetry", "run", "pytest", "tests", "-q"] in calls
