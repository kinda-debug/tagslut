#!/usr/bin/env python3
"""Populate `.env` by mirroring `.env.example` with dynamic overrides."""
from __future__ import annotations

import os
import re
import yaml
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


def extract_volumes_from_zones(zones_config_path: Path) -> dict[str, str]:
    """Extract volume paths from zones.yaml configuration."""
    if not zones_config_path.exists():
        return {}

    try:
        with open(zones_config_path) as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Warning: Could not parse zones config: {e}")
        return {}

    if not config or "zones" not in config:
        return {}

    volumes: dict[str, str] = {}
    zones = config.get("zones", {})

    # Extract paths from each zone and create VOLUME_* variables
    for zone_name, zone_data in zones.items():
        if not isinstance(zone_data, dict) or "paths" not in zone_data:
            continue
        paths = zone_data.get("paths", [])
        if paths and isinstance(paths, list):
            # Use the first path for this zone as the main volume
            volume_name = f"VOLUME_{zone_name.upper()}"
            volumes[volume_name] = paths[0]

    return volumes


def build_updates(root: Path, lines: list[str]) -> dict[str, str]:
    updates: dict[str, str] = {}
    sample_db_path: Path | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("DEDUPE_DB="):
            db_value = stripped.split("=", 1)[1].strip()
            # Handle both old hardcoded paths and new EPOCH_PLACEHOLDER
            if "EPOCH_PLACEHOLDER" in db_value:
                # Extract the template: /path/to/EPOCH_PLACEHOLDER/music.db
                sample_db_path = Path(db_value.replace("EPOCH_PLACEHOLDER", "EPOCH_TEMP"))
            else:
                sample_db_path = Path(db_value)
            break

    if sample_db_path:
        if len(sample_db_path.parents) >= 2:
            base_dir = sample_db_path.parents[1]
            latest_epoch = find_latest_epoch(base_dir)
            if latest_epoch:
                today = datetime.now().date()
                latest_date = epoch_date_from_name(latest_epoch.name)
                # If today's epoch doesn't exist yet, prefer creating it.
                if latest_date and latest_date.date() < today:
                    today_dir = base_dir / f"EPOCH_{today:%Y-%m-%d}"
                    new_db = today_dir / "music.db"
                else:
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

    # Extract volumes from zones.yaml if available
    zones_config = os.environ.get("DEDUPE_ZONES_CONFIG")
    if not zones_config:
        zones_config = Path.home() / ".config" / "dedupe" / "zones.yaml"
    else:
        zones_config = Path(zones_config).expanduser()

    zone_volumes = extract_volumes_from_zones(zones_config)
    updates.update(zone_volumes)
    if zone_volumes:
        print(f"Extracted {len(zone_volumes)} volume(s) from zones config")

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
        new_value = updates.get(key) if updates else None
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
