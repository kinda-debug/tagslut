#!/usr/bin/env python3
"""
Check if move plan actually has duplicates (files with same MD5).
Move plan should have 19,339 unique MD5s - if it does, selection already happened.
"""
import csv

with open('artifacts/reports/library_move_plan.csv') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

# Check for duplicate MD5s in move plan
md5_counts = {}
for row in rows:
    md5 = row['md5']
    md5_counts[md5] = md5_counts.get(md5, 0) + 1

duplicates = {md5: count for md5, count in md5_counts.items() if count > 1}

with open('/tmp/move_plan_analysis.txt', 'w') as out:
    out.write(f"MOVE PLAN ANALYSIS\n")
    out.write(f"==================\n\n")
    out.write(f"Total files in plan: {len(rows)}\n")
    out.write(f"Unique MD5s: {len(md5_counts)}\n")
    out.write(f"MD5s with duplicates: {len(duplicates)}\n\n")
    
    if duplicates:
        out.write("DUPLICATE MD5S FOUND (unexpected!):\n")
        for md5, count in list(duplicates.items())[:10]:
            out.write(f"  {md5}: {count} copies\n")
            for row in rows:
                if row['md5'] == md5:
                    out.write(f"    - {row['source_root']:12} | {row['source'].split('/')[-1]}\n")
    else:
        out.write("✓ NO DUPLICATES - Move plan is correct\n")
        out.write("  Each MD5 appears exactly once\n")
        out.write("  This means the selection already happened during move plan creation\n\n")
    
    # Show distribution
    roots = {}
    for row in rows:
        root = row['source_root']
        roots[root] = roots.get(root, 0) + 1
    
    out.write("DISTRIBUTION BY SOURCE:\n")
    for root in sorted(roots.keys()):
        pct = 100 * roots[root] / len(rows)
        out.write(f"  {root:12} | {roots[root]:6} files ({pct:5.1f}%)\n")
    
    out.write("\nCONCLUSION:\n")
    out.write("The move plan shows which files were SELECTED to keep.\n")
    out.write("The corresponding files in Garbage/Quarantine were DELETED.\n")
    out.write("Selection was based on: source priority (MUSIC > Garbage > Quarantine)\n")

print("Analysis written to /tmp/move_plan_analysis.txt")
