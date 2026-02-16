from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def _run_mypy() -> str:
    proc = subprocess.run(
        ["poetry", "run", "mypy", ".", "--hide-error-context", "--no-color-output", "--show-error-codes"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return output.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check mypy output against a baseline.")
    parser.add_argument(
        "--baseline",
        default="tools/baselines/mypy.txt",
        help="Baseline file path",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Overwrite baseline with current mypy output",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)

    output = _run_mypy()
    if args.update:
        baseline_path.write_text(output + "\n", encoding="utf-8")
        print(f"Updated mypy baseline: {baseline_path}")
        return 0

    if not baseline_path.exists():
        print(f"Missing mypy baseline: {baseline_path}")
        print("Run: python scripts/mypy_baseline_check.py --update")
        return 1

    baseline = baseline_path.read_text(encoding="utf-8").strip()
    if output.strip() != baseline:
        print("Mypy output differs from baseline.\n")
        print("Baseline:")
        print(baseline or "(empty)")
        print("\nCurrent:")
        print(output or "(empty)")
        print("\nIf this is expected, update with:")
        print("  python scripts/mypy_baseline_check.py --update")
        return 1

    print("Mypy matches baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
