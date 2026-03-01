"""Apply canonical tag rules defined in library_canon.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, MutableMapping, Optional


@dataclass(frozen=True)
class CanonRules:
    fallbacks: dict[str, list[str]]
    numbers: dict[str, int]
    year_only: list[str]
    set_if_present: list[str]
    unset_exact: list[str]
    unset_prefixes: list[str]
    unset_globs: list[str]
    keep_exact: list[str]
    aliases: dict[str, list[str]]


def load_canon_rules(path: Path) -> CanonRules:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return CanonRules(
        fallbacks={k.lower(): [v.lower() for v in vals]
                   for k, vals in (data.get("fallbacks") or {}).items()},
        numbers={k.lower(): int(v) for k, v in (data.get("numbers") or {}).items()},
        year_only=[k.lower() for k in (data.get("year_only") or [])],
        set_if_present=[k.lower() for k in (data.get("set_if_present") or [])],
        unset_exact=[k.lower() for k in (data.get("unset_exact") or [])],
        unset_prefixes=[k.lower() for k in (data.get("unset_prefixes") or [])],
        unset_globs=[k.lower() for k in (data.get("unset_globs") or [])],
        keep_exact=[k.lower() for k in (data.get("keep_exact") or [])],
        aliases={k.lower(): [v.lower() for v in vals]
                 for k, vals in (data.get("aliases") or {}).items()},
    )


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple)):
        return all(_is_empty_value(v) for v in value)
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _normalize_value(value: Any) -> Any:
    return value


def _apply_number(value: Any, width: int) -> Any:
    if isinstance(value, (list, tuple)):
        return [_apply_number(v, width) for v in value]
    try:
        num = int(str(value))
    except (TypeError, ValueError):
        return value
    return str(num).zfill(width)


def _apply_year_only(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_apply_year_only(v) for v in value]
    if value is None:
        return value
    text = str(value)
    return text[:4] if text else text


def _alias_map(rules: CanonRules) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for canonical, aliases in rules.aliases.items():
        mapping[canonical] = canonical
        for alias in aliases:
            mapping[alias] = canonical
    return mapping


def apply_canon(tags: MutableMapping[str, Any], rules: CanonRules) -> MutableMapping[str, Any]:
    """
    Apply canon rules to a tag dictionary.

    Returns a new dict; does not mutate input.
    """
    alias_map = _alias_map(rules)

    # Build normalized view with original keys preserved
    groups: dict[str, dict[str, Any]] = {}
    for key, value in tags.items():
        norm = key.lower()
        norm = alias_map.get(norm, norm)
        entry = groups.setdefault(norm, {"keys": [], "value": value})
        entry["keys"].append(key)
        # Prefer first non-empty value
        if _is_empty_value(entry["value"]) and not _is_empty_value(value):
            entry["value"] = value

    # Helper to get/set normalized key
    def get_value(norm_key: str) -> Optional[Any]:
        entry = groups.get(norm_key)
        if not entry:
            return None
        return entry["value"]

    def set_value(norm_key: str, value: Any) -> None:
        entry = groups.get(norm_key)
        if entry:
            entry["value"] = value
        else:
            groups[norm_key] = {"keys": [norm_key], "value": value}

    def remove_key(norm_key: str) -> None:
        groups.pop(norm_key, None)

    # 1) Fallbacks
    for dst, chain in rules.fallbacks.items():
        current = get_value(dst)
        if current is not None and not _is_empty_value(current):
            continue
        for src in chain:
            val = get_value(src)
            if val is not None and not _is_empty_value(val):
                set_value(dst, _normalize_value(val))
                break

    # 2) Numbers
    for f, width in rules.numbers.items():
        val = get_value(f)
        if val is not None and not _is_empty_value(val):
            set_value(f, _apply_number(val, width))

    # 3) Year-only fields
    for f in rules.year_only:
        val = get_value(f)
        if val is not None and not _is_empty_value(val):
            set_value(f, _apply_year_only(val))

    # 4) set_if_present (no overwrite with empty)
    for f in rules.set_if_present:
        val = get_value(f)
        if val is None:
            continue
        if _is_empty_value(val):
            continue
        set_value(f, _normalize_value(val))

    # 5) Unset rules (keep wins)
    keep = set(rules.keep_exact)
    for norm_key in list(groups.keys()):
        if norm_key in keep:
            continue

        if norm_key in rules.unset_exact:
            remove_key(norm_key)
            continue

        if any(norm_key.startswith(prefix) for prefix in rules.unset_prefixes):
            remove_key(norm_key)
            continue

        if any(fnmatch(norm_key, pattern) for pattern in rules.unset_globs):
            remove_key(norm_key)
            continue

    # 6) Rebuild output preserving original keys if possible
    output: dict[str, Any] = {}
    for norm_key, entry in groups.items():
        value = entry["value"]
        keys = entry["keys"]
        if keys:
            for k in keys:
                output[k] = value
        else:
            output[norm_key] = value

    return output


def canon_diff(before: MutableMapping[str, Any], after: MutableMapping[str, Any]) -> str:
    import difflib
    before_lines = json.dumps(before, indent=2, sort_keys=True, ensure_ascii=False).splitlines()
    after_lines = json.dumps(after, indent=2, sort_keys=True, ensure_ascii=False).splitlines()
    diff = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile="before",
        tofile="after",
        lineterm="",
    )
    return "\n".join(diff)
