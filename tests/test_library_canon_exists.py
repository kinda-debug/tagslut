from __future__ import annotations

import json
from pathlib import Path


def test_library_canon_rules_exist_and_are_valid_json() -> None:
    rules_path = Path(__file__).resolve().parents[1] / "tools" / "rules" / "library_canon.json"
    assert rules_path.exists(), f"Missing canon rules: {rules_path}"
    payload = json.loads(rules_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    for key in [
        "fallbacks",
        "numbers",
        "year_only",
        "set_if_present",
        "unset_exact",
        "unset_prefixes",
        "unset_globs",
        "keep_exact",
        "aliases",
    ]:
        assert key in payload, f"Missing canon rules key: {key}"
