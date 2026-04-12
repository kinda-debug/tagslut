#!/usr/bin/env python3
"""Capture post-release environment and test snapshots for the current version."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_version() -> str:
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    with pyproject_path.open("rb") as handle:
        data = tomllib.load(handle)
    project = data.get("project", {})
    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("Unable to read project.version from pyproject.toml")
    return version.strip()


VERSION = _read_version()
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / f"v{VERSION}"
ENV_SNAPSHOT_PATH = OUTPUT_DIR / "ENV_SNAPSHOT.md"
TEST_REPORT_PATH = OUTPUT_DIR / f"test_report_v{VERSION}.txt"
DIST_ARTIFACTS = (
    PROJECT_ROOT / "dist" / f"tagslut-{VERSION}.tar.gz",
    PROJECT_ROOT / "dist" / f"tagslut-{VERSION}-py3-none-any.whl",
)


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class SnapshotResult:
    version: str
    output_dir: Path
    env_snapshot_path: Path
    test_report_path: Path
    missing_dist_artifacts: tuple[Path, ...]


def _run_command(runner: Runner, args: list[str]) -> subprocess.CompletedProcess[str]:
    return runner(
        args,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _format_command_output(command: str, proc: subprocess.CompletedProcess[str]) -> str:
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    lines = [
        f"### `{command}`",
        "",
        "```text",
    ]
    if stdout:
        lines.append(stdout.rstrip("\n"))
    if stderr:
        if stdout:
            lines.append("")
        lines.append(stderr.rstrip("\n"))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def capture_post_release_snapshot(
    *,
    output_dir: Path = OUTPUT_DIR,
    runner: Runner = subprocess.run,
) -> SnapshotResult:
    output_dir.mkdir(parents=True, exist_ok=True)

    python_proc = _run_command(runner, ["python", "--version"])
    poetry_proc = _run_command(runner, ["poetry", "--version"])
    poetry_show_proc = _run_command(runner, ["poetry", "show", "tagslut"])
    pytest_proc = _run_command(runner, ["poetry", "run", "pytest", "tests", "-q"])

    env_snapshot_path = output_dir / "ENV_SNAPSHOT.md"
    env_snapshot_lines = [
        f"# Post-Release Environment Snapshot (v{VERSION})",
        "",
        f"- Platform: `{platform.system()} {platform.release()} ({platform.version()})`",
        f"- Machine: `{platform.machine()}`",
        "",
        _format_command_output("python --version", python_proc),
        _format_command_output("poetry --version", poetry_proc),
        _format_command_output("poetry show tagslut", poetry_show_proc),
    ]
    env_snapshot_path.write_text("\n".join(env_snapshot_lines), encoding="utf-8")

    test_report_path = output_dir / f"test_report_v{VERSION}.txt"
    test_report = (pytest_proc.stdout or "") + (pytest_proc.stderr or "")
    test_report_path.write_text(test_report, encoding="utf-8")

    missing = tuple(path for path in DIST_ARTIFACTS if not path.exists())
    if missing:
        print("WARNING: missing expected release build artifacts:")
        for path in missing:
            print(f"  - {path}")
    else:
        print("Release build artifacts verified:")
        for path in DIST_ARTIFACTS:
            print(f"  - {path}")

    print(f"Environment snapshot: {env_snapshot_path}")
    print(f"Test report: {test_report_path}")

    return SnapshotResult(
        version=VERSION,
        output_dir=output_dir,
        env_snapshot_path=env_snapshot_path,
        test_report_path=test_report_path,
        missing_dist_artifacts=missing,
    )


def main() -> int:
    capture_post_release_snapshot()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
