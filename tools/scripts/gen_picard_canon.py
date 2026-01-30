#!/usr/bin/env python3
import json
import sys
from fnmatch import fnmatch

def picard_if_set(field: str) -> str:
    # Picard vars are %field%
    return f"$if($ne(%{field}%,),$set({field},%{field}%))"

def main(path: str) -> int:
    rules = json.load(open(path, "r", encoding="utf-8"))

    out = []
    out.append("$noop(LIBRARY - CANONICAL ENFORCEMENT)")
    out.append("")

    # fallbacks
    for dst, chain in (rules.get("fallbacks") or {}).items():
        # $if2(%a%,%b%) style
        if not chain:
            continue
        expr = None
        for f in chain[::-1]:
            expr = f"%{f}%" if expr is None else f"$if2(%{f}%,{expr})"
        out.append(f"$set({dst},{expr})")
    out.append("")

    # numbers (only if present)
    for f, width in (rules.get("numbers") or {}).items():
        out.append(f"$if($ne(%{f}%,),$set({f},$num(%{f}%,{int(width)})))")
    out.append("")

    # year-only fields
    for f in rules.get("year_only", []):
        out.append(f"$if($ne(%{f}%,),$set({f},$left(%{f}%,4)))")
    out.append("")

    # set_if_present
    for f in rules.get("set_if_present", []):
        # skip ones covered by fallbacks/numbers to avoid duplicating
        if f in (rules.get("fallbacks") or {}) or f in (rules.get("numbers") or {}):
            continue
        out.append(picard_if_set(f))
    out.append("")

    # unsets
    for f in rules.get("unset_exact", []):
        out.append(f"$unset({f})")
    for p in rules.get("unset_prefixes", []):
        out.append(f"$unset({p}*)")
    for g in rules.get("unset_globs", []):
        if g == "_*":
            out.append("$unset(_*)")
        else:
            # Picard doesn't have a glob-unset; keep only common patterns
            out.append(f"$noop(UNSET GLOB NOT SUPPORTED: {g})")

    sys.stdout.write("\n".join(out).rstrip() + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "rules/library_canon.json"))
