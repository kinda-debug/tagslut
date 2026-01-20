import csv
from collections import Counter
from pathlib import Path

plan_file = "dedupe_removal_plan.csv"
if not Path(plan_file).exists():
    print(f"Error: {plan_file} not found")
    exit(1)

stats = {
    "by_source_zone": Counter(),
    "by_keeper_zone": Counter(),
    "by_reason": Counter(),
    "top_dirs": Counter()
}

total_rows = 0
with open(plan_file, "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        total_rows += 1
        stats["by_source_zone"][row["source_zone"]] += 1
        stats["by_keeper_zone"][row["keeper_zone"]] += 1
        stats["by_reason"][row["reason"]] += 1

        path = Path(row["path"])
        # Use first 4 parts of the path for grouping (e.g., /Volumes/NAME/M/Subdir)
        if len(path.parts) > 3:
            top_dir = "/".join(path.parts[:4])
            stats["top_dirs"][top_dir] += 1

print("--- Removal Plan Summary ---")
print(f"Total files to be quarantined: {total_rows}")
print("\nFiles by Source Zone (Where they are now):")
for zone, count in stats["by_source_zone"].items():
    print(f"  {zone}: {count}")

print("\nKeepers by Zone (Where we are keeping the copy):")
for zone, count in stats["by_keeper_zone"].items():
    print(f"  {zone}: {count}")

print("\nTop Directories with most duplicates to remove:")
for dir, count in stats["top_dirs"].most_common(15):
    print(f"  {count} files in {dir}")

print("\nCommon Reasons:")
for reason, count in stats["by_reason"].items():
    print(f"  {reason}: {count}")
