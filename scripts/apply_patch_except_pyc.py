#!/usr/bin/env python3
"""Apply the large patch but skip .pyc and other binary pycache files.

This script extracts hunks from `archive/legacy_root/patches/patch.patch`
excluding paths that end with `.pyc` or contain `__pycache__`, writes them
into `tmp_full_patch_no_pyc.patch`, and runs `git apply --3way`.
If the apply succeeds (partially or fully), it stages changes, commits and
pushes them under a single commit.

Use carefully: this will create new files referenced by the patch.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "archive/legacy_root/patches/patch.patch"
OUT = ROOT / "tmp_full_patch_no_pyc.patch"

if not PATCH.exists():
    print("Patch file not found:", PATCH)
    sys.exit(1)

text = PATCH.read_text(encoding="utf-8")
lines = text.splitlines()
blocks = []
cur = None
for line in lines:
    if line.startswith('diff --git '):
        if cur is not None:
            blocks.append(cur)
        cur = [line]
    else:
        if cur is not None:
            cur.append(line)
if cur is not None:
    blocks.append(cur)

selected = []
skipped = []
for b in blocks:
    hdr = b[0]
    parts = hdr.split()
    # typical: diff --git a/path b/path
    if len(parts) >= 3:
        a = parts[2]
    else:
        a = parts[1] if len(parts) > 1 else parts[0]
    if a.startswith('a/'):
        path = a[2:]
    else:
        path = a
    lower = path.lower()
    if path.endswith('.pyc') or '__pycache__' in path:
        skipped.append(path)
        continue
    # skip explicit binary blobs markers referencing object files? Keep hunks unless .pyc
    selected.append('\n'.join(b))

if not selected:
    print('No hunks selected after filtering; nothing to apply.')
    sys.exit(0)

OUT.write_text('\n'.join(selected) + '\n', encoding='utf-8')
print(f'Wrote {OUT} with {len(selected)} hunks; skipped {len(skipped)} pyc/__pycache__ files.')
if skipped:
    print('Skipped examples:')
    for s in skipped[:20]:
        print(' -', s)

# Run git apply --3way
print('Applying patch with git apply --3way...')
proc = subprocess.run(['git', 'apply', '--3way', str(OUT)], cwd=ROOT, capture_output=True, text=True)
print(proc.stdout)
if proc.returncode != 0:
    print('git apply returned non-zero; continuing to stage whatever changed.')
    print(proc.stderr)

# Stage everything
subprocess.run(['git', 'add', '-A'], cwd=ROOT)
# Show staged files
staged = subprocess.run(['git', 'diff', '--staged', '--name-only'], cwd=ROOT, capture_output=True, text=True)
if staged.stdout.strip():
    print('Staged files:')
    print(staged.stdout)
    commit = subprocess.run(['git', 'commit', '-m', 'Apply large unified patch (excluding .pyc/__pycache__ entries)'], cwd=ROOT, capture_output=True, text=True)
    print(commit.stdout)
    if commit.returncode == 0:
        push = subprocess.run(['git', 'push', 'origin', 'main'], cwd=ROOT, capture_output=True, text=True)
        print(push.stdout)
        if push.returncode != 0:
            print('git push failed:')
            print(push.stderr)
    else:
        print('git commit failed or nothing to commit:')
        print(commit.stderr)
else:
    print('No staged changes to commit after apply.')

print('Done.')
