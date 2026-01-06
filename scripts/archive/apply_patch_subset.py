#!/usr/bin/env python3
"""Apply subset of large patch for scripts/ and tools/ safely.

This script extracts hunks from `archive/legacy_root/patches/patch.patch`
that target files under `scripts/` or `tools/` which exist in the
working tree, writes them to a temporary patch file, and runs
`git apply --3way` on that file. If changes are applied it stages,
commits, and pushes them.

Usage: python3 scripts/apply_patch_subset.py
"""
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "archive/legacy_root/patches/patch.patch"
OUT = ROOT / "tmp_scripts_tools_patch.patch"

if not PATCH.exists():
    print("Patch file not found:", PATCH)
    sys.exit(1)

text = PATCH.read_text(encoding="utf-8")
lines = text.splitlines()
blocks = []
cur = None
for line in lines:
    if line.startswith("diff --git "):
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
    # parts example: ['diff', '--git', 'a/scripts/foo.py', 'b/scripts/foo.py']
    if len(parts) >= 3:
        a = parts[2]
    else:
        a = parts[1] if len(parts) > 1 else parts[0]
    if a.startswith('a/'):
        path = a[2:]
    else:
        path = a
    if (path.startswith('scripts/') or path.startswith('tools/')) and not path.endswith('.pyc'):
        if (ROOT / path).exists():
            selected.append('\n'.join(b))
        else:
            skipped.append(path)

if not selected:
    print(f"No matching hunks found for existing files under scripts/ or tools/. Skipped {len(skipped)} files.")
    for s in skipped[:100]:
        print("SKIP", s)
    sys.exit(0)

OUT.write_text('\n'.join(selected) + '\n', encoding='utf-8')
print(f"Wrote {OUT} with {len(selected)} hunks; skipped {len(skipped)} missing files.")
if skipped:
    print("First skipped files:")
    for s in skipped[:20]:
        print(" -", s)

# Apply the patch using git
print("Applying patch with 'git apply --3way'...")
proc = subprocess.run(["git", "apply", "--3way", str(OUT)], cwd=ROOT, capture_output=True, text=True)
print(proc.stdout)
if proc.returncode != 0:
    print("git apply returned non-zero (may have applied partially).")
    print(proc.stderr)

# Stage and commit changes under scripts/ and tools/
subprocess.run(["git", "add", "-A", "scripts", "tools"], cwd=ROOT)
# If there are staged changes, create a commit
status = subprocess.run(["git", "diff", "--staged", "--name-only"], cwd=ROOT, capture_output=True, text=True)
if status.stdout.strip():
    print("Staged files to commit:")
    print(status.stdout)
    commit = subprocess.run(["git", "commit", "-m", "Batch 4: apply top-level scripts/ and tools/ patch hunks"], cwd=ROOT, capture_output=True, text=True)
    print(commit.stdout)
    if commit.returncode == 0:
        push = subprocess.run(["git", "push", "origin", "main"], cwd=ROOT, capture_output=True, text=True)
        print(push.stdout)
        if push.returncode != 0:
            print("git push failed:")
            print(push.stderr)
    else:
        print("git commit failed or nothing to commit:")
        print(commit.stderr)
else:
    print("No staged changes to commit for scripts/ or tools/.")

print("Done.")
