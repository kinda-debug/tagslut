#!/usr/bin/env python3
"""Validate configured paths in `config.toml`.

Reports which configured paths exist and which are missing. Does not create
anything by default — pass `--create` to create missing directories (safe
explicit action).

Usage:
    ./scripts/validate_config.py [--config CONFIG.toml] [--create]
"""
from __future__ import annotations

import argparse
# stdlib only
from pathlib import Path

try:
    import tomllib
except Exception:  # pragma: no cover - fallback for older pythons
    import tomli as tomllib  # type: ignore


def load_config(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--config",
        "-c",
        default="config.toml",
        help="Path to config.toml",
    )
    p.add_argument(
        "--create",
        action="store_true",
        help="Create missing directories",
    )
    args = p.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"Config file not found: {cfg_path}")
        return 2

    cfg = load_config(cfg_path)
    paths = cfg.get("paths", {})
    keys = [
        "root",
        "diagnostic_root",
        "quarantine",
        "garbage",
        "broken_playlist",
    ]

    missing_dirs = []
    print(f"Validating paths from: {cfg_path}\n")
    for key in keys:
        val = paths.get(key)
        if val is None:
            print(f"- {key}: <not set>")
            continue
        pval = Path(val)
        if key == "broken_playlist":
            parent = pval.parent
            exists = parent.exists()
            typ = "playlist (parent dir)"
            name = str(parent)
        else:
            exists = pval.exists()
            typ = "dir"
            name = str(pval)

        status = "OK" if exists else "MISSING"
        print(f"- {key}: {name} [{typ}] — {status}")
        if not exists and (key != "broken_playlist"):
            missing_dirs.append(pval)
        if not exists and key == "broken_playlist":
            missing_dirs.append(parent)

    if missing_dirs:
        print("\nMissing directories:")
        for d in missing_dirs:
            print(f"  - {d}")
        if args.create:
            for d in missing_dirs:
                try:
                    d.mkdir(parents=True, exist_ok=True)
                    print(f"Created: {d}")
                except Exception as exc:
                    print(f"Failed to create {d}: {exc}")
                    return 3
            print("\nAll requested directories created.")
        else:
            print("\nRun with --create to create missing directories.")
        return 1

    print("\nAll configured paths exist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
