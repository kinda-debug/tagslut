#!/usr/bin/env python3
"""Run flac -t integrity check on entire library."""
import subprocess
import concurrent.futures
from pathlib import Path
from datetime import datetime

library_path = Path("/Volumes/COMMUNE/M/Library")

print(f"{'='*70}")
print(f"LIBRARY INTEGRITY CHECK")
print(f"{'='*70}")
print(f"Library: {library_path}")
print(f"Starting: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# Find all FLAC files (exclude macOS metadata files)
print("Finding FLAC files...")
flac_files = [f for f in library_path.rglob("*.flac") if not f.name.startswith("._")]
print(f"Found: {len(flac_files)} FLAC files\n")

def check_file(file_path):
    """Run flac -t on a single file."""
    try:
        result = subprocess.run(
            ['flac', '-ts', str(file_path)],
            capture_output=True,
            timeout=30,
            text=True
        )
        
        # Check for errors in stderr
        if result.returncode != 0 or 'ERROR' in result.stderr or 'LOST_SYNC' in result.stderr:
            return ('CORRUPT', str(file_path), result.stderr)
        else:
            return ('VALID', None, None)
            
    except subprocess.TimeoutExpired:
        return ('TIMEOUT', str(file_path), 'Timeout after 30 seconds')
    except Exception as e:
        return ('ERROR', str(file_path), str(e))

print(f"Running integrity checks with 8 workers...")
print(f"{'='*70}\n")

valid_count = 0
corrupt_files = []
timeout_files = []
error_files = []

start_time = datetime.now()

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    futures = {executor.submit(check_file, f): f for f in flac_files}
    
    for idx, future in enumerate(concurrent.futures.as_completed(futures), 1):
        status, path, error = future.result()
        
        if status == 'VALID':
            valid_count += 1
        elif status == 'CORRUPT':
            corrupt_files.append((path, error))
            print(f"✗ CORRUPT: {Path(path).name}")
        elif status == 'TIMEOUT':
            timeout_files.append((path, error))
            print(f"⏱ TIMEOUT: {Path(path).name}")
        elif status == 'ERROR':
            error_files.append((path, error))
            print(f"⚠ ERROR: {Path(path).name}")
        
        # Progress update every 500 files
        if idx % 500 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = idx / elapsed
            print(f"Progress: {idx}/{len(flac_files)} ({idx/len(flac_files)*100:.1f}%) | {rate:.1f} files/sec")

end_time = datetime.now()
duration = (end_time - start_time).total_seconds()

print(f"\n{'='*70}")
print(f"INTEGRITY CHECK COMPLETE")
print(f"{'='*70}")
print(f"Total files checked: {len(flac_files)}")
print(f"Valid: {valid_count} ({valid_count/len(flac_files)*100:.1f}%)")
print(f"Corrupt: {len(corrupt_files)} ({len(corrupt_files)/len(flac_files)*100:.1f}%)")
print(f"Timeouts: {len(timeout_files)}")
print(f"Errors: {len(error_files)}")
print(f"Duration: {duration:.1f} seconds ({len(flac_files)/duration:.1f} files/sec)")

# Write detailed results
report_path = Path("/Volumes/COMMUNE/M/03_reports/library_integrity_20260116.txt")
with open(report_path, "w") as f:
    f.write(f"Library Integrity Check Report\n")
    f.write(f"Generated: {datetime.now().isoformat()}\n")
    f.write(f"Library: {library_path}\n\n")
    f.write(f"Summary:\n")
    f.write(f"  Total files: {len(flac_files)}\n")
    f.write(f"  Valid: {valid_count} ({valid_count/len(flac_files)*100:.2f}%)\n")
    f.write(f"  Corrupt: {len(corrupt_files)} ({len(corrupt_files)/len(flac_files)*100:.2f}%)\n")
    f.write(f"  Timeouts: {len(timeout_files)}\n")
    f.write(f"  Errors: {len(error_files)}\n")
    f.write(f"  Duration: {duration:.1f} seconds\n\n")
    
    if corrupt_files:
        f.write(f"Corrupt Files ({len(corrupt_files)}):\n")
        f.write(f"{'='*70}\n")
        for path, error in corrupt_files:
            f.write(f"{path}\n")
            f.write(f"  Error: {error[:200]}\n\n")
    
    if timeout_files:
        f.write(f"\nTimeout Files ({len(timeout_files)}):\n")
        f.write(f"{'='*70}\n")
        for path, error in timeout_files:
            f.write(f"{path}\n\n")
    
    if error_files:
        f.write(f"\nError Files ({len(error_files)}):\n")
        f.write(f"{'='*70}\n")
        for path, error in error_files:
            f.write(f"{path}\n")
            f.write(f"  Error: {error}\n\n")

print(f"\n✓ Detailed report: {report_path}")

if corrupt_files or timeout_files or error_files:
    print(f"\n⚠ Found {len(corrupt_files) + len(timeout_files) + len(error_files)} problematic files")
    print(f"Review report for details: {report_path}")
else:
    print(f"\n✓ All files passed integrity check!")

