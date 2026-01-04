#!/usr/bin/env python3
"""
Export dupeGuru CSV results into organized A/B comparison directories.

Creates clean review structure:
    _dupe_review/
        group_0001/
            A_library.flac
            B_library.flac
        group_0002/
            A_library.flac
            C_library.flac

Usage:
    python3 tools/export_dupe_groups.py --csv /path/to/dupeguru.csv \\
                                                                            --out /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY/_DUPE_REVIEW
"""
import argparse
import csv
import shutil
from pathlib import Path


def infer_label(path: Path, labels: dict) -> str:
    """Infer volume label from path."""
    path_str = str(path)
    for key, label in labels.items():
        if f"/{key}/" in path_str:
            return label
    return "X_unknown"


def export_dupe_groups(csv_path: Path, out_root: Path, labels: dict):
    """Export dupe groups from CSV to organized folders."""
    out_root.mkdir(parents=True, exist_ok=True)
    
    groups = {}
    
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gid = row["Group ID"]
            path = Path(row["Folder"]) / row["Filename"]
            groups.setdefault(gid, []).append(path)
    
    exported = 0
    for gid, files in groups.items():
        if len(files) < 2:
            continue
        
        gdir = out_root / f"group_{int(gid):04d}"
        gdir.mkdir(exist_ok=True)
        
        for fpath in files:
            if not fpath.exists():
                print(f"WARN: Missing file: {fpath}")
                continue
            
            label = infer_label(fpath, labels)
            dst = gdir / f"{label}_{fpath.name}"
            
            if not dst.exists():
                shutil.copy2(fpath, dst)
                print(f"  {gdir.name}/{dst.name}")
        
        exported += 1
    
    print(f"\n✓ Exported {exported} dupe groups to {out_root}")


def main():
    parser = argparse.ArgumentParser(
        description="Export dupeGuru CSV to organized A/B comparison folders"
    )
    parser.add_argument(
        "--csv",
        required=True,
        type=Path,
        help="Path to dupeGuru CSV export"
    )
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="Output root directory for review structure"
    )
    parser.add_argument(
        "--labels",
        nargs="+",
        default=["recovery=A_library"],
        help="Volume label mappings (format: volume=prefix)"
    )
    
    args = parser.parse_args()
    
    # Parse label mappings
    labels = {}
    for mapping in args.labels:
        volume, prefix = mapping.split("=")
        labels[volume] = prefix
    
    export_dupe_groups(args.csv, args.out, labels)


if __name__ == "__main__":
    main()
