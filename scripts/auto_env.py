#!/usr/bin/env python3
"""Populate `.env` by mirroring `.env.example` with dynamic overrides."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def discover_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def parse_env_lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


def epoch_date_from_name(name: str) -> datetime | None:
    if not name.startswith("EPOCH_"):
        return None
    payload = name[len("EPOCH_"):].replace("-", "")
    if not re.fullmatch(r"\d{8}", payload):
        return None
    try:
        return datetime.strptime(payload, "%Y%m%d")
    except ValueError:
        return None


def find_latest_epoch(base_dir: Path) -> Path | None:
    epochs = []
    for entry in base_dir.iterdir():
        if not entry.is_dir():
            continue
        date = epoch_date_from_name(entry.name)
        if date:
            epochs.append((date, entry))
    if not epochs:
        return None
    return max(epochs, key=lambda pair: pair[0])[1]


def build_updates(root: Path, lines: list[str]) -> dict[str, str]:
    updates: dict[str, str] = {}
    sample_db_path: Path | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("DEDUPE_DB="):
            sample_db_path = Path(stripped.split("=", 1)[1].strip())
            break

    if sample_db_path:
        if len(sample_db_path.parents) >= 2:
            base_dir = sample_db_path.parents[1]
            latest_epoch = find_latest_epoch(base_dir)
            if latest_epoch:
                new_db = latest_epoch / "music.db"
                new_db.parent.mkdir(parents=True, exist_ok=True)
                updates["DEDUPE_DB"] = str(new_db)
                print(f"Set DEDUPE_DB → {new_db}")
            else:
                print("Warning: no EPOCH_* directories found for DEDUPE_DB")
        else:
            print("Warning: DEDUPE_DB sample path does not have epoch parent")
    else:
        print("Warning: DEDUPE_DB definition missing in .env.example")

    artifacts_dir = root / "artifacts"
    updates.setdefault("DEDUPE_ARTIFACTS", str(artifacts_dir))
    reports_dir = artifacts_dir / "M" / "03_reports"
    updates.setdefault("DEDUPE_REPORTS", str(reports_dir))
    return updates


def materialize_env(env_example: Path, env_file: Path, updates: dict[str, str]) -> None:
    content: list[str] = []
    for line in parse_env_lines(env_example):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            content.append(line)
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        new_value = updates.get(key)
        rendered_value = new_value if new_value is not None else value.strip()
        content.append(f"{key}={rendered_value}")
    env_file.write_text("\n".join(content) + "\n")
    print(f"Refreshed {env_file.relative_to(env_example.parent)}")


def main() -> None:
    root = discover_repo_root()
    env_example = root / ".env.example"
    env_file = root / ".env"

    if not env_example.exists():
        raise SystemExit(".env.example is missing")

    lines = parse_env_lines(env_example)
    updates = build_updates(root, lines)
    materialize_env(env_example, env_file, updates)


if __name__ == "__main__":
    main()
