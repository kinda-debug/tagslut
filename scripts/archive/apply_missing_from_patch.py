#!/usr/bin/env python3
"""Create and apply a patch with hunks for missing files from the large patch.

Reads `artifacts/skipped_patch_paths.txt` for entries marked "SKIP (missing): <path>" and
generates a patch containing hunks from `archive/legacy_root/patches/patch.patch` for those
paths (excluding .pyc/__pycache__). Applies with `git apply --3way`, stages, commits, pushes.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIPPED = ROOT / 'artifacts' / 'skipped_patch_paths.txt'
PATCH = ROOT / 'archive' / 'legacy_root' / 'patches' / 'patch.patch'
OUT = ROOT / 'tmp_missing.patch'

if not SKIPPED.exists():
    print('Skipped list not found:', SKIPPED)
    sys.exit(1)
if not PATCH.exists():
    print('Original patch not found:', PATCH)
    sys.exit(1)

# Read missing paths
missing = []
for line in SKIPPED.read_text(encoding='utf-8').splitlines():
    line=line.strip()
    if not line:
        continue
    if line.startswith('SKIP (missing):'):
        path=line.split(':',1)[1].strip()
        if path.endswith('.pyc') or '__pycache__' in path:
            continue
        missing.append(path)

if not missing:
    print('No missing non-pyc paths found to restore')
    sys.exit(0)

print('Missing count:', len(missing))
# Parse original patch into blocks
text = PATCH.read_text(encoding='utf-8')
lines = text.splitlines()
blocks=[]
cur=None
for line in lines:
    if line.startswith('diff --git '):
        if cur is not None:
            blocks.append(cur)
        cur=[line]
    else:
        if cur is not None:
            cur.append(line)
if cur is not None:
    blocks.append(cur)

selected=[]
missset=set(missing)
for b in blocks:
    hdr=b[0]
    parts=hdr.split()
    if len(parts)>=3:
        a=parts[2]
    else:
        a=parts[1] if len(parts)>1 else parts[0]
    if a.startswith('a/'):
        path=a[2:]
    else:
        path=a
    if path in missset:
        if path.endswith('.pyc') or '__pycache__' in path:
            continue
        selected.append('\n'.join(b))

if not selected:
    print('No hunks found for requested missing paths')
    sys.exit(0)

OUT.write_text('\n'.join(selected)+"\n", encoding='utf-8')
print('Wrote', OUT, 'with', len(selected), 'hunks')
# Apply
proc = subprocess.run(['git','apply','--3way',str(OUT)], cwd=ROOT, capture_output=True, text=True)
print(proc.stdout)
if proc.returncode != 0:
    print('git apply returned non-zero; stderr:')
    print(proc.stderr)

# Stage everything
subprocess.run(['git','add','-A'], cwd=ROOT)
# Commit if staged
staged = subprocess.run(['git','diff','--staged','--name-only'], cwd=ROOT, capture_output=True, text=True)
if staged.stdout.strip():
    print('Staged files count:', len(staged.stdout.splitlines()))
    commit = subprocess.run(['git','commit','-m','Restore missing files from patch (apply missing hunks)'], cwd=ROOT, capture_output=True, text=True)
    print(commit.stdout)
    if commit.returncode == 0:
        push = subprocess.run(['git','push','origin','main'], cwd=ROOT, capture_output=True, text=True)
        print(push.stdout)
        if push.returncode != 0:
            print('git push failed:')
            print(push.stderr)
else:
    print('No staged changes to commit')

print('Done')
