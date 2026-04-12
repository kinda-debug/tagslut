#!/usr/bin/env python3
"""
fix_blocklist.py

Remove false positives from DJ blocklists using a keep list.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import yaml


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"\b(feat|featuring|ft)\b.*", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _resolve_blocklist_path(policy_path: Path, override: str | None) -> Path:
    if override:
        return Path(override)
    data = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    rules = data.get("rules", {}) if isinstance(data, dict) else {}
    path = rules.get("artist_blocklist_path", "config/blocklists/non_dj_artists.txt")
    return Path(path)


def _load_keep_list(values: list[str], keep_from: str | None) -> list[str]:
    items: list[str] = []
    for raw in values:
        for part in re.split(r"[,\n]+", raw):
            part = part.strip()
            if part:
                items.append(part)
    if keep_from:
        for line in Path(keep_from).read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            items.append(line)
    return items


def _prune_blocklist(path: Path, keep: list[str], dry_run: bool) -> list[str]:
    if not path.exists():
        raise SystemExit(f"Blocklist not found: {path}")
    raw_keep = " ".join(keep).strip()
    if not raw_keep:
        return []
    targets = {
        _normalize_text(part)
        for part in re.split(r"[,\n]+", raw_keep)
        if part.strip()
    }
    haystack = _normalize_text(raw_keep)

    removed: list[str] = []
    kept_lines: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            kept_lines.append(line)
            continue
        key = _normalize_text(line)
        if key in targets or (haystack and key in haystack):
            removed.append(line)
            continue
        kept_lines.append(line)
    if removed and not dry_run:
        path.write_text("\n".join(kept_lines).rstrip() + "\n", encoding="utf-8")
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Prune false positives from DJ blocklists.")
    parser.add_argument(
        "--policy",
        default="config/dj/dj_curation_usb.yaml",
        help="Policy YAML used to resolve blocklist path.",
    )
    parser.add_argument("--blocklist", help="Override blocklist path.")
    parser.add_argument(
        "--keep",
        action="append",
        default=[],
        help="Artist name to keep (remove from blocklist). Repeatable or comma-separated.",
    )
    parser.add_argument("--keep-from", help="File containing artists to keep, one per line.")
    parser.add_argument("--dry-run", action="store_true", help="Preview removals.")
    args = parser.parse_args()

    policy_path = Path(args.policy)
    if not policy_path.exists():
        raise SystemExit(f"Policy not found: {policy_path}")

    blocklist_path = _resolve_blocklist_path(policy_path, args.blocklist)
    keep = _load_keep_list(args.keep, args.keep_from)
    if not keep:
        print(f"No keep list provided. Blocklist path: {blocklist_path}")
        return

    removed = _prune_blocklist(blocklist_path, keep, dry_run=args.dry_run)
    mode = "DRY-RUN" if args.dry_run else "UPDATED"
    print(f"{mode}: removed {len(removed)} artist(s) from {blocklist_path}")
    if removed:
        for artist in removed:
            print(f"- {artist}")


if __name__ == "__main__":
    main()
