#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Pair:
    isrc: str
    library_path: Path
    promoted_path: Path
    sr_library: int
    sr_promoted: int
    bd_library: int
    bd_promoted: int
    br_library: int
    br_promoted: int
    size_library: int
    size_promoted: int
    fp_equal: bool


def _as_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        s = str(value).strip()
        if s == "":
            return 0
        return int(float(s))
    except Exception:
        return 0


def _check_flac_ok(path: Path) -> bool:
    try:
        res = subprocess.run(
            ["flac", "-t", "--silent", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def _quality_key(sr: int, bd: int, br: int, size: int) -> tuple[int, int, int, int]:
    return (sr, bd, br, size)


def _relative_under_volume(path: Path) -> Path:
    parts = path.resolve().parts
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "Volumes":
        return Path(*parts[3:])  # after /Volumes/<VOLUME_NAME>/
    return Path(path.name)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Promote ISRC+fpcalc matches: move keeper to SAD, stash dupe on source volume")
    ap.add_argument(
        "--pairs-csv",
        type=Path,
        default=Path("artifacts/compare/library_vs_promoted_isrc_overlaps_enriched_fp.csv"),
        help="CSV produced by the ISRC overlap enrichment step",
    )
    ap.add_argument(
        "--dest-sad-root",
        type=Path,
        default=Path("/Volumes/SAD/_work/MUSIC/_work/staging/_promoted_isrc_fp"),
        help="Destination root on SAD for promoted keepers",
    )
    ap.add_argument(
        "--stash-folder-name",
        default="_healthy_dupes_isrc_fp",
        help="Folder name under each source volume for stashed dupes",
    )
    try:
        bool_action = argparse.BooleanOptionalAction  # py3.9+
        ap.add_argument(
            "--check-integrity",
            default=True,
            action=bool_action,
            help="Run `flac -t` on the 2 files in each pair and only act on pairs where both pass",
        )
    except AttributeError:
        ap.add_argument(
            "--check-integrity",
            dest="check_integrity",
            action="store_true",
            help="Run `flac -t` on the 2 files in each pair and only act on pairs where both pass",
        )
        ap.add_argument(
            "--no-check-integrity",
            dest="check_integrity",
            action="store_false",
            help="Skip `flac -t` checks",
        )
        ap.set_defaults(check_integrity=True)
    ap.add_argument(
        "--out-promote-plan",
        type=Path,
        default=Path("artifacts/compare/plan_promote_to_sad.csv"),
        help="Output CSV plan: MOVE rows that promote keepers to SAD",
    )
    ap.add_argument(
        "--out-stash-plan",
        type=Path,
        default=Path("artifacts/compare/plan_stash_healthy_dupes.csv"),
        help="Output CSV plan: MOVE rows that stash the non-keeper dupes",
    )
    ap.add_argument(
        "--out-summary",
        type=Path,
        default=Path("artifacts/compare/promote_isrc_fp_summary.json"),
        help="Output JSON summary for review",
    )
    return ap.parse_args()


def _load_pairs(path: Path) -> list[Pair]:
    rows = list(csv.DictReader(path.open("r", encoding="utf-8")))
    pairs: list[Pair] = []
    for r in rows:
        isrc = (r.get("isrc") or "").strip()
        lib = Path((r.get("library_path") or "").strip())
        pro = Path((r.get("promoted_path") or "").strip())
        if not isrc or not lib or not pro:
            continue
        fp_equal = (r.get("fp_equal") or "").strip() == "1"
        pairs.append(
            Pair(
                isrc=isrc,
                library_path=lib,
                promoted_path=pro,
                sr_library=_as_int(r.get("sr_library")),
                sr_promoted=_as_int(r.get("sr_promoted")),
                bd_library=_as_int(r.get("bd_library")),
                bd_promoted=_as_int(r.get("bd_promoted")),
                br_library=_as_int(r.get("br_library")),
                br_promoted=_as_int(r.get("br_promoted")),
                size_library=_as_int(r.get("size_library")),
                size_promoted=_as_int(r.get("size_promoted")),
                fp_equal=fp_equal,
            )
        )
    return pairs


def main() -> int:
    args = parse_args()
    pairs_csv = args.pairs_csv.expanduser().resolve()
    dest_sad_root = args.dest_sad_root.expanduser().resolve()
    out_promote = args.out_promote_plan.expanduser().resolve()
    out_stash = args.out_stash_plan.expanduser().resolve()
    out_summary = args.out_summary.expanduser().resolve()

    pairs = [p for p in _load_pairs(pairs_csv) if p.fp_equal]
    if not pairs:
        print("No fp_equal pairs found; nothing to do.")
        return 0

    promote_rows: list[dict[str, str]] = []
    stash_rows: list[dict[str, str]] = []
    summary_pairs: list[dict[str, Any]] = []

    skipped_missing = 0
    skipped_integrity = 0

    for p in pairs:
        lib_exists = p.library_path.exists()
        pro_exists = p.promoted_path.exists()
        if not lib_exists or not pro_exists:
            skipped_missing += 1
            summary_pairs.append(
                {
                    "isrc": p.isrc,
                    "library_path": str(p.library_path),
                    "promoted_path": str(p.promoted_path),
                    "result": "skip_missing",
                    "library_exists": lib_exists,
                    "promoted_exists": pro_exists,
                }
            )
            continue

        lib_ok = True
        pro_ok = True
        if args.check_integrity:
            lib_ok = _check_flac_ok(p.library_path)
            pro_ok = _check_flac_ok(p.promoted_path)
            if not (lib_ok and pro_ok):
                skipped_integrity += 1
                summary_pairs.append(
                    {
                        "isrc": p.isrc,
                        "library_path": str(p.library_path),
                        "promoted_path": str(p.promoted_path),
                        "result": "skip_integrity",
                        "library_flac_ok": lib_ok,
                        "promoted_flac_ok": pro_ok,
                    }
                )
                continue

        lib_q = _quality_key(p.sr_library, p.bd_library, p.br_library, p.size_library)
        pro_q = _quality_key(p.sr_promoted, p.bd_promoted, p.br_promoted, p.size_promoted)
        if pro_q > lib_q:
            keeper = p.promoted_path
            dupe = p.library_path
            keeper_side = "promoted"
        elif lib_q > pro_q:
            keeper = p.library_path
            dupe = p.promoted_path
            keeper_side = "library"
        else:
            keeper = p.promoted_path
            dupe = p.library_path
            keeper_side = "promoted_tie"

        keeper_rel = _relative_under_volume(keeper)
        dupe_rel = _relative_under_volume(dupe)

        keeper_dest = dest_sad_root / keeper_rel
        stash_dest_root = Path("/Volumes") / dupe.resolve().parts[2] / "_work" / args.stash_folder_name
        stash_dest = stash_dest_root / dupe_rel

        promote_rows.append(
            {
                "action": "MOVE",
                "isrc": p.isrc,
                "path": str(keeper),
                "dest_path": str(keeper_dest),
                "reason": f"promote_isrc_fp_equal keeper_side={keeper_side}",
            }
        )
        stash_rows.append(
            {
                "action": "MOVE",
                "isrc": p.isrc,
                "path": str(dupe),
                "dest_path": str(stash_dest),
                "reason": f"stash_healthy_dupe_isrc_fp_equal keeper_side={keeper_side}",
            }
        )

        summary_pairs.append(
            {
                "isrc": p.isrc,
                "keeper_side": keeper_side,
                "keeper_src": str(keeper),
                "keeper_dest": str(keeper_dest),
                "dupe_src": str(dupe),
                "dupe_dest": str(stash_dest),
                "library_quality": {"sr": p.sr_library, "bd": p.bd_library, "br": p.br_library, "size": p.size_library},
                "promoted_quality": {"sr": p.sr_promoted, "bd": p.bd_promoted, "br": p.br_promoted, "size": p.size_promoted},
                "integrity_checked": bool(args.check_integrity),
                "result": "planned",
            }
        )

    out_promote.parent.mkdir(parents=True, exist_ok=True)
    out_stash.parent.mkdir(parents=True, exist_ok=True)
    out_summary.parent.mkdir(parents=True, exist_ok=True)

    def write_plan(path: Path, rows: list[dict[str, str]]) -> None:
        if not rows:
            path.write_text("action,isrc,path,dest_path,reason\n", encoding="utf-8")
            return
        fieldnames = ["action", "isrc", "path", "dest_path", "reason"]
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)

    write_plan(out_promote, promote_rows)
    write_plan(out_stash, stash_rows)

    out_summary.write_text(
        json.dumps(
            {
                "pairs_input": str(pairs_csv),
                "pairs_fp_equal": len(pairs),
                "planned_promote_moves": len(promote_rows),
                "planned_stash_moves": len(stash_rows),
                "skipped_missing": skipped_missing,
                "skipped_integrity": skipped_integrity,
                "dest_sad_root": str(dest_sad_root),
                "stash_folder_name": str(args.stash_folder_name),
                "check_integrity": bool(args.check_integrity),
                "pairs": summary_pairs,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Pairs (fp_equal): {len(pairs)}")
    print(f"Planned promote moves: {len(promote_rows)} -> {out_promote}")
    print(f"Planned stash moves:   {len(stash_rows)} -> {out_stash}")
    if skipped_missing:
        print(f"Skipped (missing):     {skipped_missing}")
    if skipped_integrity:
        print(f"Skipped (integrity):   {skipped_integrity}")
    print(f"Summary: {out_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
