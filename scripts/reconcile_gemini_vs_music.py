#!/usr/bin/env python3
import argparse
import csv
import os

"""
Reconciliation step:
Reads the detailed gemini_dupe_analysis CSV and extracts only
entries that are safe to delete.

Keeps rows where recommendation == "safe_to_delete".
Outputs a CSV with a single column 'delete_path'.
"""

def reconcile(analysis_csv, out_csv):
    to_delete = []

    with open(analysis_csv, "r") as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("recommendation") == "safe_to_delete":
                gemini_path = row.get("gemini_path", "")
                if gemini_path:
                    to_delete.append([gemini_path])

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["delete_path"])
        w.writerows(to_delete)

    print(f"[DONE] Wrote reconcile list: {out_csv}")
    print(f"Safe-to-delete rows: {len(to_delete)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis-csv", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    reconcile(args.analysis_csv, args.out)


if __name__ == "__main__":
    main()
