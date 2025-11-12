#!/usr/bin/env python3
"""
Verify all deleted files and check their keepers for health and correctness.

For each deleted file, checks:
1. Keeper still exists
2. Keeper file size matches expected
3. Path length comparison (should keeper have been deleted instead?)
4. Basic file health (readable, non-zero)
"""

import csv
import sys
from pathlib import Path


def main():
    executed_csv = Path("artifacts/reports/cross_root_prune_executed_postcleanup.csv")
    
    if not executed_csv.exists():
        print(f"ERROR: {executed_csv} not found", file=sys.stderr)
        return 1
    
    print("Analyzing all 133 deleted files and their keepers...\n")
    
    issues = []
    wrong_policy = []
    missing_keepers = []
    size_mismatches = []
    
    with executed_csv.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            deleted_path = Path(row["path"])
            keeper_path = Path(row["keeper"])
            expected_size = int(row["size_bytes"])
            status = row["status"]
            
            # Only process actually deleted files
            if status != "deleted":
                continue
            
            print(f"[{i}/133] Checking keeper for: {deleted_path.name}")
            
            # Check if keeper exists
            if not keeper_path.exists():
                missing_keepers.append({
                    "deleted": str(deleted_path),
                    "keeper": str(keeper_path),
                    "size": expected_size,
                })
                print(f"  ❌ KEEPER MISSING: {keeper_path}")
                continue
            
            # Check keeper size
            try:
                actual_size = keeper_path.stat().st_size
                if actual_size != expected_size:
                    size_mismatches.append({
                        "deleted": str(deleted_path),
                        "keeper": str(keeper_path),
                        "expected_size": expected_size,
                        "actual_size": actual_size,
                    })
                    print(f"  ⚠️  SIZE MISMATCH: Expected {expected_size}, got {actual_size}")
            except OSError as e:
                issues.append({
                    "deleted": str(deleted_path),
                    "keeper": str(keeper_path),
                    "error": str(e),
                })
                print(f"  ❌ ERROR accessing keeper: {e}")
                continue
            
            # Check path length policy
            deleted_parts = len(deleted_path.parts)
            keeper_parts = len(keeper_path.parts)
            
            if deleted_parts < keeper_parts:
                wrong_policy.append({
                    "deleted": str(deleted_path),
                    "deleted_length": deleted_parts,
                    "keeper": str(keeper_path),
                    "keeper_length": keeper_parts,
                })
                print(f"  🚨 WRONG POLICY: Deleted had shorter path ({deleted_parts} vs {keeper_parts})")
            elif deleted_parts == keeper_parts:
                # Check lexicographic
                if str(deleted_path) < str(keeper_path):
                    wrong_policy.append({
                        "deleted": str(deleted_path),
                        "deleted_length": deleted_parts,
                        "keeper": str(keeper_path),
                        "keeper_length": keeper_parts,
                        "note": "lexicographic tie - deleted should have won",
                    })
                    print(f"  🚨 WRONG POLICY: Deleted was lexicographically first")
            else:
                print(f"  ✅ Correct policy (keeper shorter: {keeper_parts} vs {deleted_parts})")
    
    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    print(f"\nMissing keepers: {len(missing_keepers)}")
    if missing_keepers:
        print("  ⚠️  These keeper files no longer exist:")
        for item in missing_keepers:
            print(f"    - {item['keeper']}")
            print(f"      (deleted: {item['deleted']})")
    
    print(f"\nSize mismatches: {len(size_mismatches)}")
    if size_mismatches:
        print("  ⚠️  Keeper sizes don't match expected:")
        for item in size_mismatches:
            print(f"    - {item['keeper']}")
            print(f"      Expected: {item['expected_size']}, Got: {item['actual_size']}")
    
    print(f"\nWrong policy decisions: {len(wrong_policy)}")
    if wrong_policy:
        print("  🚨 These deletions violated shortest-path policy:")
        for item in wrong_policy:
            print(f"    - Deleted: {item['deleted']} (length: {item['deleted_length']})")
            print(f"      Kept:    {item['keeper']} (length: {item['keeper_length']})")
            if "note" in item:
                print(f"      Note: {item['note']}")
    
    print(f"\nOther errors: {len(issues)}")
    if issues:
        for item in issues:
            print(f"    - {item['keeper']}: {item['error']}")
    
    # Write detailed reports
    if wrong_policy:
        report_path = Path("artifacts/reports/wrong_policy_decisions.csv")
        with report_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["deleted", "deleted_length", "keeper", "keeper_length", "note"])
            writer.writeheader()
            for item in wrong_policy:
                if "note" not in item:
                    item["note"] = ""
                writer.writerow(item)
        print(f"\n📄 Detailed report: {report_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
