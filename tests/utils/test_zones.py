from __future__ import annotations

from pathlib import Path

from tagslut.utils.zones import (
    Zone,
    ZoneManager,
    coerce_zone,
    load_zone_manager,
    zone_priority,
)


def _write_yaml(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_zone_manager_loads_from_yaml_config(tmp_path: Path) -> None:
    config_path = _write_yaml(
        tmp_path / "zones.yml",
        """
defaults:
  zone: suspect
zones:
  accepted:
    paths:
      - library
    priority: 10
  staging:
    paths:
      - staging
    priority: 30
  quarantine:
    paths:
      - quarantine
    priority: 50
""".strip()
        + "\n",
    )
    manager = load_zone_manager(config_path=config_path)

    assert manager.default_zone == Zone.SUSPECT
    assert {zc.zone for zc in manager.zones()} == {Zone.ACCEPTED, Zone.STAGING, Zone.QUARANTINE}


def test_get_zone_for_path_covers_known_and_unknown_paths(tmp_path: Path) -> None:
    config_path = _write_yaml(
        tmp_path / "zones.yml",
        (
            f"""
roots:
  base: {tmp_path}
zones:
  accepted:
    paths: [library]
  staging:
    paths: [staging]
  quarantine:
    paths: [quarantine]
""".strip()
            + "\n"
        ),
    )
    manager = load_zone_manager(config_path=config_path)

    assert manager.get_zone_for_path(tmp_path / "library" / "a.flac").zone == Zone.ACCEPTED
    assert manager.get_zone_for_path(tmp_path / "staging" / "b.flac").zone == Zone.STAGING
    assert manager.get_zone_for_path(tmp_path / "quarantine" / "c.flac").zone == Zone.QUARANTINE
    assert manager.get_zone_for_path(tmp_path / "elsewhere" / "d.flac").zone == Zone.SUSPECT


def test_zone_priority_ordering_library_staging_quarantine() -> None:
    assert zone_priority(Zone.ACCEPTED) < zone_priority(Zone.STAGING)
    assert zone_priority(Zone.STAGING) < zone_priority(Zone.QUARANTINE)


def test_coerce_zone_valid_invalid_and_none() -> None:
    assert coerce_zone("accepted") == Zone.ACCEPTED
    assert coerce_zone("ACCEPTED") == Zone.ACCEPTED
    assert coerce_zone(Zone.STAGING) == Zone.STAGING
    assert coerce_zone("not-a-zone") is None
    assert coerce_zone(None) is None


def test_override_priorities_returns_new_order(tmp_path: Path) -> None:
    manager = ZoneManager(
        zone_configs=(
            # Initial values reflect default ordering.
            # We override to make quarantine first.
            load_zone_manager(
                config_path=_write_yaml(
                    tmp_path / "zones.yml",
                    """
zones:
  accepted: {paths: [library], priority: 10}
  staging: {paths: [staging], priority: 30}
  quarantine: {paths: [quarantine], priority: 50}
""".strip()
                    + "\n",
                )
            ).zones()
        ),
        source="test",
    )

    overridden = manager.override_priorities(["quarantine", "accepted", "staging"])
    assert overridden.zone_priority("quarantine") == 1
    assert overridden.zone_priority("accepted") == 2
    assert overridden.zone_priority("staging") == 3
    assert manager.zone_priority("quarantine") == 50


def test_has_library_zones_true_and_false(tmp_path: Path) -> None:
    with_library = load_zone_manager(
        config_path=_write_yaml(
            tmp_path / "zones_with_library.yml",
            "zones:\n  accepted: {paths: [library]}\n",
        )
    )
    without_library = load_zone_manager(
        config_path=_write_yaml(
            tmp_path / "zones_without_library.yml",
            "zones:\n  staging: {paths: [staging]}\n",
        )
    )

    assert with_library.has_library_zones() is True
    assert without_library.has_library_zones() is False


def test_empty_config_falls_back_to_env_default(tmp_path: Path) -> None:
    manager = load_zone_manager(config_path=_write_yaml(tmp_path / "empty.yml", "{}\n"))
    assert manager.default_zone == Zone.SUSPECT
    assert manager.get_zone_for_path(tmp_path / "no-match.flac").zone == Zone.SUSPECT


def test_overlapping_paths_choose_longest_prefix(tmp_path: Path) -> None:
    config_path = _write_yaml(
        tmp_path / "zones.yml",
        (
            f"""
roots:
  base: {tmp_path}
zones:
  staging:
    paths:
      - media
  quarantine:
    paths:
      - media/bad
""".strip()
            + "\n"
        ),
    )
    manager = load_zone_manager(config_path=config_path)

    assert manager.get_zone_for_path(tmp_path / "media" / "ok" / "x.flac").zone == Zone.STAGING
    assert manager.get_zone_for_path(tmp_path / "media" / "bad" / "x.flac").zone == Zone.QUARANTINE
