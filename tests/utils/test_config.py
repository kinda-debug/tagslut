from pathlib import Path

from tagslut.utils.config import _clear_config_instance, get_config


def test_load_config_from_override_path(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        """
[db]
path = "/tmp/tagslut.db"
[integrity]
write_sanity_check = false
""".strip(),
        encoding="utf-8",
    )

    _clear_config_instance()
    cfg = get_config(config_path=cfg_path)

    assert cfg.get("db.path") == "/tmp/tagslut.db"
    assert cfg.get("integrity.write_sanity_check") is False


def test_missing_config_file_uses_defaults(tmp_path: Path) -> None:
    missing = tmp_path / "missing.toml"

    _clear_config_instance()
    cfg = get_config(config_path=missing)

    assert cfg.get("db.path") is None
    assert cfg.get("unknown.key", "fallback") == "fallback"


def test_load_config_from_env_path(monkeypatch: object, tmp_path: Path) -> None:
    cfg_path = tmp_path / "env_config.toml"
    cfg_path.write_text("[db]\npath = \"/tmp/env.db\"\n", encoding="utf-8")
    monkeypatch.setenv("TAGSLUT_CONFIG", str(cfg_path))  # type: ignore[attr-defined]

    _clear_config_instance()
    cfg = get_config()

    assert cfg.get("db.path") == "/tmp/env.db"


def test_validate_valid_config_has_no_issues(tmp_path: Path) -> None:
    cfg_path = tmp_path / "valid.toml"
    cfg_path.write_text(
        """
[db]
path = "/tmp/tagslut.db"
write_sanity_check = true
[integrity]
parallel_workers = 4
db_write_batch_size = 100
[library]
name = "COMMUNE"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _clear_config_instance()
    cfg = get_config(config_path=cfg_path)
    issues = cfg.validate()
    assert issues == []


def test_validate_warns_on_unknown_key(caplog, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    cfg_path = tmp_path / "unknown.toml"
    cfg_path.write_text(
        """
[db]
path = "/tmp/tagslut.db"
[typo]
pth = "bad"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _clear_config_instance()
    cfg = get_config(config_path=cfg_path)
    with caplog.at_level("WARNING"):
        issues = cfg.validate()
    assert any("Unknown config key: typo.pth" in issue for issue in issues)


def test_validate_warns_on_type_mismatch(caplog, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    cfg_path = tmp_path / "type.toml"
    cfg_path.write_text(
        """
[db]
path = "/tmp/tagslut.db"
[integrity]
db_write_batch_size = "five-hundred"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    _clear_config_instance()
    cfg = get_config(config_path=cfg_path)
    with caplog.at_level("WARNING"):
        issues = cfg.validate()
    assert any("Type mismatch for integrity.db_write_batch_size" in issue for issue in issues)


def test_validate_warns_on_missing_required_key(caplog, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    cfg_path = tmp_path / "missing_required.toml"
    cfg_path.write_text("[library]\nname = \"COMMUNE\"\n", encoding="utf-8")

    _clear_config_instance()
    cfg = get_config(config_path=cfg_path)
    with caplog.at_level("WARNING"):
        issues = cfg.validate()
    assert any("Missing required config key: db.path" in issue for issue in issues)
