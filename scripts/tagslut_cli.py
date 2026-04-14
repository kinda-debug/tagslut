#!/opt/homebrew/bin/python3
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    venv_site = (
        repo_root
        / ".venv"
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )

    sys.path.insert(0, str(venv_site))
    sys.path.insert(0, str(repo_root))

    from tagslut.cli.main import cli

    return int(cli())


if __name__ == "__main__":
    raise SystemExit(main())
