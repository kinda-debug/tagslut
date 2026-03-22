from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ANSI = {
    "reset": "\x1b[0m",
    "bold": "\x1b[1m",
    "dim": "\x1b[2m",
    "red": "\x1b[31m",
    "green": "\x1b[32m",
    "yellow": "\x1b[33m",
    "blue": "\x1b[34m",
    "cyan": "\x1b[36m",
}


def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _c(text: str, color: str) -> str:
    if not _use_color():
        return text
    return f"{ANSI[color]}{text}{ANSI['reset']}"


def _b(text: str) -> str:
    if not _use_color():
        return text
    return f"{ANSI['bold']}{text}{ANSI['reset']}"


def _table(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    left_w = max(len(k) for k, _ in rows)
    lines = []
    for key, value in rows:
        lines.append(f"  {key.ljust(left_w)}  {value}")
    return "\n".join(lines)


def _find_latest(dir_path: Path, pattern: str) -> Path | None:
    candidates = sorted(dir_path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


@dataclass(frozen=True)
class PrecheckSummary:
    total: int
    keep: int
    skip: int
    source_selection_attempted: int
    tidal_selected: int
    beatport_selected: int


def _parse_precheck(decisions_csv: Path) -> PrecheckSummary:
    keep = 0
    skip = 0
    total = 0
    attempted = 0
    tidal_selected = 0
    beatport_selected = 0

    with decisions_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            total += 1
            decision = (row.get("decision") or row.get("action") or "").strip().lower()
            if decision == "keep":
                keep += 1
            elif decision == "skip":
                skip += 1

            if (row.get("source_selection_attempted") or "").strip() == "1":
                attempted += 1
                winner = (row.get("source_selection_winner") or "").strip().lower()
                if winner == "tidal":
                    tidal_selected += 1
                elif winner == "beatport":
                    beatport_selected += 1

    return PrecheckSummary(
        total=total,
        keep=keep,
        skip=skip,
        source_selection_attempted=attempted,
        tidal_selected=tidal_selected,
        beatport_selected=beatport_selected,
    )


def _read_plan_summary(summary_json: Path) -> dict[str, Any]:
    try:
        return json.loads(summary_json.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="Pretty summary for tools/get-intake runs (reads artifacts).")
    ap.add_argument("--out-dir", default="artifacts/compare", help="Artifacts compare directory")
    ap.add_argument("--log", help="Path to captured tools/get-intake log (optional)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()
    if not out_dir.exists():
        print(f"Missing out-dir: {out_dir}")
        return 0

    decisions_csv = _find_latest(out_dir, "precheck_decisions_*.csv")
    plan_summary = _find_latest(out_dir, "plan_fpcalc_unique_final_summary_*.json")
    moves_log = _find_latest(Path("artifacts").expanduser().resolve(), "moves_*.jsonl")

    print(_b("Intake Summary"))
    print()

    if decisions_csv:
        s = _parse_precheck(decisions_csv)
        keep_color = "green" if s.keep > 0 else "yellow"
        rows: list[tuple[str, str]] = [
            ("Precheck CSV", str(decisions_csv)),
            ("Tracks", str(s.total)),
            ("Keep", _c(str(s.keep), keep_color)),
            ("Skip", _c(str(s.skip), "green" if s.skip == 0 else "yellow")),
        ]
        if s.source_selection_attempted > 0:
            rows.extend(
                [
                    ("Source select", str(s.source_selection_attempted)),
                    ("Winner: TIDAL", _c(str(s.tidal_selected), "green" if s.tidal_selected else "yellow")),
                    ("Winner: Beatport", str(s.beatport_selected)),
                ]
            )
        print(_table(rows))
        print()
    else:
        print(_c("No precheck_decisions_*.csv found.", "yellow"))
        print()

    if plan_summary:
        payload = _read_plan_summary(plan_summary)
        promote = str(payload.get("promote", payload.get("promote_move", payload.get("promote_count", ""))))
        stash = str(payload.get("stash", payload.get("stash_move", payload.get("stash_count", ""))))
        quarantine = str(payload.get("quarantine", payload.get("quarantine_move", payload.get("quarantine_count", ""))))
        if promote == "0":
            promote = _c("0", "yellow")
        else:
            promote = _c(promote, "green")
        print(_b("Move Plan"))
        print(_table([("Summary JSON", str(plan_summary)), ("Promote", promote), ("Stash", stash), ("Quarantine", quarantine)]))
        print()

    if args.log:
        log_path = Path(args.log).expanduser().resolve()
        if log_path.exists():
            print(_b("Log"))
            print(_table([("Captured log", str(log_path))]))
            print()

    if moves_log and moves_log.exists():
        print(_b("Moves Log"))
        print(_table([("Latest moves", str(moves_log))]))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

