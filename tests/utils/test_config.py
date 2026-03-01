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
