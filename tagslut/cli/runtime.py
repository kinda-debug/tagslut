from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tagslut.utils.paths import list_files

INTERNAL_CLI_ENV = "TAGSLUT_CLI_INTERNAL_CALL"
PROJECT_ROOT = Path(__file__).parents[2]
WRAPPER_CONTEXT = dict(ignore_unknown_options=True, help_option_names=[])


def is_internal_cli_call() -> bool:
    return os.getenv(INTERNAL_CLI_ENV) == "1"


def run_subprocess(cmd: list[str], *, internal: bool = False) -> None:
    env = os.environ.copy()
    if internal:
        env[INTERNAL_CLI_ENV] = "1"
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def run_tagslut_wrapper(args: list[str]) -> None:
    run_subprocess([sys.executable, "-m", "tagslut", *args], internal=True)


def run_python_script(script_rel_path: str, args: tuple[str, ...]) -> None:
    script_path = (PROJECT_ROOT / script_rel_path).resolve()
    run_subprocess([sys.executable, str(script_path), *list(args)], internal=True)


def run_executable(script_rel_path: str, args: tuple[str, ...]) -> None:
    script_path = (PROJECT_ROOT / script_rel_path).resolve()
    run_subprocess([str(script_path), *list(args)], internal=True)


def collect_flac_paths(input_path: str) -> list[Path]:
    path = Path(input_path).expanduser().resolve()
    if path.is_dir():
        files = list(list_files(path, {".flac"}))
        return sorted(files, key=lambda p: str(p))
    if path.is_file():
        return [path]
    raise FileNotFoundError(f"Path not found: {input_path}")
