from pathlib import Path
import csv, os

SRC = Path('artifacts/reports/safe_to_delete_recommend.csv')
OUT = Path('artifacts/reports/safe_to_delete_presence.csv')

if not SRC.exists():
    raise SystemExit(f"Missing source CSV: {SRC}")

total = 0
present = 0

OUT.parent.mkdir(parents=True, exist_ok=True)
with SRC.open(encoding='utf8', newline='') as r, OUT.open('w', encoding='utf8', newline='') as w:
    reader = csv.DictReader(r)
    writer = csv.DictWriter(w, fieldnames=['duplicate_path','canonical_path','exists'])
    writer.writeheader()
    for row in reader:
        dup = (row.get('duplicate_path') or row.get('duplicate') or '').strip()
        canon = (row.get('canonical_path') or row.get('canonical') or '').strip()
        if not dup:
            continue
        total += 1
        exists = os.path.exists(dup)
        if exists:
            present += 1
        writer.writerow({'duplicate_path': dup, 'canonical_path': canon, 'exists': '1' if exists else '0'})

print('Wrote presence table:', OUT)
print('Total recommended duplicates:', total)
print('Existing on disk:', present)
print('Missing on disk:', total - present)
