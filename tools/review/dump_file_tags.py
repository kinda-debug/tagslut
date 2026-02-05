#!/usr/bin/env python3
"""
dump_file_tags.py

Dump embedded tags for explicit file paths (JSONL), without walking directories.
Useful when you want to preserve tag differences before quarantining a small set
of duplicates.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

try:
    import mutagen  # type: ignore
except Exception:
    print("ERROR: mutagen is required. Install with: pip install mutagen", file=sys.stderr)
    raise


def _safe_str(x: Any, max_len: int) -> str:
    if x is None:
        return ""
    if hasattr(x, "text"):
        try:
            t = getattr(x, "text")
            if isinstance(t, (list, tuple)):
                s = " / ".join(str(v) for v in t)
            else:
                s = str(t)
            return s[:max_len]
        except Exception:
            pass
    if isinstance(x, (bytes, bytearray)):
        # Avoid dumping large binary blobs (pictures).
        return f"<bytes:{len(x)}>"
    if isinstance(x, (list, tuple)):
        parts = []
        for v in x:
            parts.append(_safe_str(v, max_len))
        s = " / ".join(p for p in parts if p != "")
        return s[:max_len]
    try:
        return str(x)[:max_len]
    except Exception:
        return repr(x)[:max_len]


def _normalize_key(k: Any) -> str:
    if k is None:
        return ""
    if isinstance(k, (bytes, bytearray)):
        try:
            return k.decode("utf-8", "ignore")
        except Exception:
            return repr(k)
    return str(k)


def extract_tags(path: Path, max_value_len: int) -> Dict[str, List[str]]:
    audio = mutagen.File(str(path), easy=False)
    if audio is None or getattr(audio, "tags", None) is None:
        return {}

    tags = audio.tags
    try:
        items = tags.items()  # type: ignore[attr-defined]
    except Exception:
        try:
            items = ((k, tags[k]) for k in tags.keys())  # type: ignore
        except Exception:
            return {}

    out: Dict[str, List[str]] = {}
    for k, v in items:
        key = _normalize_key(k).strip()
        if not key:
            continue

        vals: List[str] = []
        if isinstance(v, (list, tuple)):
            for one in v:
                s = _safe_str(one, max_value_len).strip()
                if s:
                    vals.append(s)
        else:
            s = _safe_str(v, max_value_len).strip()
            if s:
                vals.append(s)

        if vals:
            # Preserve order, drop exact duplicates
            seen = set()
            uniq = []
            for s in vals:
                if s not in seen:
                    uniq.append(s)
                    seen.add(s)
            out[key] = uniq
    return out


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Dump embedded tags for explicit file paths (JSONL)")
    ap.add_argument("paths", nargs="*", type=Path, help="Audio file paths")
    ap.add_argument("--paths-file", type=Path, help="File containing paths (one per line)")
    ap.add_argument("--out", type=Path, default=Path("artifacts/file_tags.jsonl"), help="Output JSONL path")
    ap.add_argument("--max-value-len", type=int, default=2000, help="Truncate tag values to this length")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    out_path = args.out.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    paths: List[Path] = []
    if args.paths_file:
        pf = args.paths_file.expanduser().resolve()
        for line in pf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            paths.append(Path(line))
    paths.extend(args.paths or [])
    if not paths:
        print("No paths provided (use positional paths or --paths-file).")
        return 2

    wrote = 0
    with out_path.open("w", encoding="utf-8") as f:
        for p in paths:
            p = p.expanduser().resolve()
            if not p.exists():
                continue
            tags = extract_tags(p, args.max_value_len)
            f.write(json.dumps({"path": str(p), "tags": tags}, ensure_ascii=False) + "\n")
            wrote += 1

    print(f"Wrote {wrote} rows -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
