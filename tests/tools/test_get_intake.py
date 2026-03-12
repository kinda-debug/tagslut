from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GET_INTAKE = PROJECT_ROOT / "tools" / "get-intake"


def _write_shell_library(tmp_path: Path) -> Path:
    text = GET_INTAKE.read_text(encoding="utf-8")
    prefix, marker, _rest = text.partition("\nwhile [[ $# -gt 0 ]]; do\n")
    assert marker, "Could not isolate get-intake function library"
    library_path = tmp_path / "get-intake-lib.sh"
    library_path.write_text(prefix + "\n", encoding="utf-8")
    return library_path


def _write_fake_bpdl(tmp_path: Path) -> Path:
    fake_bpdl = tmp_path / "fake-bpdl"
    fake_bpdl.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "pwd >\"${PWD_CAPTURE:?}\"\n"
        "printf '%s\\n' \"$@\" >\"${ARGS_CAPTURE:?}\"\n"
        "printf '%s\\n' \"${BPDL_STDOUT:-fake stdout}\"\n",
        encoding="utf-8",
    )
    fake_bpdl.chmod(0o755)
    return fake_bpdl


def _run_bpdl_batch(
    tmp_path: Path,
    *,
    assume_q: int,
    env_overrides: dict[str, str],
) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path, Path]:
    library_path = _write_shell_library(tmp_path)
    fake_bpdl = _write_fake_bpdl(tmp_path)
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "beatportdl-config.yml"
    cfg_path.write_text("username: demo\n", encoding="utf-8")

    log_file = tmp_path / "run.log"
    pwd_capture = tmp_path / "pwd.txt"
    args_capture = tmp_path / "args.txt"
    harness = tmp_path / "run-bpdl-batch.sh"
    harness.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"source {shlex.quote(str(library_path))}",
                f"REPO_ROOT={shlex.quote(str(PROJECT_ROOT))}",
                f"SCRIPT_DIR={shlex.quote(str(PROJECT_ROOT / 'tools'))}",
                f"BPDL_BIN={shlex.quote(str(fake_bpdl))}",
                f"BPDL_CONFIG={shlex.quote(str(cfg_path))}",
                f"BPDL_ASSUME_Q={assume_q}",
                f"run_bpdl_batch urls.txt {shlex.quote(str(log_file))} --alpha beta",
                "",
            ]
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)

    env = os.environ.copy()
    for key in ("STAGING_ROOT", "VOLUME_STAGING", "ROOT_BP", "LOCAL_STAGING"):
        env.pop(key, None)
    env["PWD_CAPTURE"] = str(pwd_capture)
    env["ARGS_CAPTURE"] = str(args_capture)
    env["BPDL_STDOUT"] = "compat stdout" if assume_q == 0 else "fake stdout"
    env.update(env_overrides)

    proc = subprocess.run(
        ["bash", str(harness)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc, cfg_path, pwd_capture, args_capture, log_file


def _read_lines(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_run_bpdl_batch_quit_mode_uses_config_workdir(tmp_path: Path) -> None:
    staging_root = tmp_path / "staging"

    proc, cfg_path, pwd_capture, args_capture, log_file = _run_bpdl_batch(
        tmp_path,
        assume_q=1,
        env_overrides={"STAGING_ROOT": str(staging_root)},
    )

    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert Path(pwd_capture.read_text(encoding="utf-8").strip()).resolve() == cfg_path.parent.resolve()
    assert _read_lines(args_capture) == ["-q", "--alpha", "beta", "urls.txt"]
    assert not log_file.exists()
    assert "bash -lc" not in proc.stdout
    assert "deprecated" not in proc.stderr
    assert f"downloads_directory: {staging_root / 'bpdl'}" in cfg_path.read_text(encoding="utf-8")


def test_run_bpdl_batch_compat_mode_logs_and_warns_for_legacy_staging_env(tmp_path: Path) -> None:
    legacy_staging = tmp_path / "legacy-staging"

    proc, cfg_path, pwd_capture, args_capture, log_file = _run_bpdl_batch(
        tmp_path,
        assume_q=0,
        env_overrides={"VOLUME_STAGING": str(legacy_staging)},
    )

    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert Path(pwd_capture.read_text(encoding="utf-8").strip()).resolve() == cfg_path.parent.resolve()
    assert _read_lines(args_capture) == ["--alpha", "beta", "urls.txt"]
    assert "bpdl compatibility mode: running without '-q' probe." in proc.stdout
    assert "compat stdout" in log_file.read_text(encoding="utf-8")
    assert "bash -lc" not in proc.stdout
    warning = "VOLUME_STAGING is deprecated; use STAGING_ROOT instead."
    assert warning in proc.stderr
    assert proc.stderr.count(warning) == 1
    assert f"downloads_directory: {legacy_staging / 'bpdl'}" in cfg_path.read_text(encoding="utf-8")
