#!/usr/bin/env python3
from pathlib import Path

def resolve_relative_output(src: Path, output_dir: Path) -> Path:
    if src.is_absolute():
        try:
            rel_path = src.relative_to('/Volumes/dotad/MUSIC')
        except Exception:
            rel_path = Path(src.name)
    else:
        rel_path = Path(src.name)
    return output_dir.joinpath(rel_path)

output_dir = Path('/Volumes/dotad/MUSIC/REPAIRED')
m3u_path = Path('/Volumes/dotad/MUSIC/broken_files_unrepaired.m3u')

with m3u_path.open('r', encoding='utf-8') as f:
    lines = f.readlines()

kept = []
removed = 0
for line in lines:
    line = line.strip()
    if not line:
        continue
    src = Path(line)
    dst = resolve_relative_output(src, output_dir)
    if dst.exists():
        print(f'Removed: {line}')
        removed += 1
    else:
        kept.append(line + '\n')

with m3u_path.open('w', encoding='utf-8') as f:
    f.writelines(kept)

print(f'Removed {removed} lines, kept {len(kept)} lines')