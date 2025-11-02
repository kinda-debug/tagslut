#!/usr/bin/env python3
"""
Promote a repaired file into REPAIRED/final_selection and patch repair_report_apply.json.

Usage:
  python3 scripts/promote_and_patch.py --src <repaired-path> [--report repair_report_apply.json] [--dest-root /Volumes/dotad/MUSIC/REPAIRED/final_selection] [--to-repair /tmp/to_repair.txt]

This will:
 - move the repaired file into a mirrored tree under --dest-root (creating parents)
 - back up an existing destination as <file>.bak if present
 - update repair_report_apply.json to include a minimal repair object for the matching entry
 - remove the repaired path from /tmp/to_repair.txt (or provided --to-repair)

Designed for local use on the host where /Volumes/dotad/MUSIC is mounted.
"""
import argparse
import json
import os
import shutil
from pathlib import Path


def promote(src, dest_root):
    src_p = Path(src)
    if not src_p.exists():
        raise FileNotFoundError(f"source not found: {src}")

    # Try to infer original relative path under /Volumes/dotad/MUSIC
    try:
        candidate = str(src).replace('/tmp/repair_debug/REPAIRED/', '/Volumes/dotad/MUSIC/')
        if candidate.startswith('/Volumes/dotad/MUSIC'):
            rel = os.path.relpath(candidate, '/Volumes/dotad/MUSIC')
        else:
            rel = src_p.name
    except Exception:
        rel = src_p.name

    dst = Path(dest_root) / rel
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        bak = dst.with_suffix(dst.suffix + '.bak')
        print(f'Backing up existing {dst} -> {bak}')
        shutil.move(str(dst), str(bak))

    print(f'Moving {src} -> {dst}')
    shutil.move(str(src), str(dst))
    return str(dst), rel


def patch_report(report_path, sel_paths, out_path):
    # sel_paths is a set of possible selected/original paths to match
    with open(report_path, 'r') as f:
        data = json.load(f)
    patched = 0

    # Handle dict-mapped reports (mapping -> entry) and list reports
    if isinstance(data, dict):
        for key, val in list(data.items()):
            # value can be a string (path) or an object
            if isinstance(val, str):
                if val in sel_paths:
                    # replace value with an object containing selected + repair
                    data[key] = {
                        'selected': val,
                        'repair': {'exit_code': 0, 'output': out_path},
                    }
                    patched += 1
                    print('Patched mapping entry for', val)
                    # continue scanning to patch other possible matches
                    continue
            elif isinstance(val, dict):
                if any(
                    val.get(k) in sel_paths
                    for k in ('selected', 'original', 'path')
                ):
                    val['repair'] = {
                        'exit_code': 0,
                        'output': out_path,
                    }
                    patched += 1
                    print('Patched mapping entry for', key)
                    continue
    elif isinstance(data, list):
        for idx, entry in enumerate(data):
            if isinstance(entry, str):
                if entry in sel_paths:
                    # replace the string entry with an object
                    data[idx] = {
                        'selected': entry,
                        'repair': {'exit_code': 0, 'output': out_path},
                    }
                    patched += 1
                    print('Patched list entry for', entry)
                    continue
            elif isinstance(entry, dict):
                if any(
                    entry.get(k) in sel_paths
                    for k in ('selected', 'original', 'path')
                ):
                    entry['repair'] = {
                        'exit_code': 0,
                        'output': out_path,
                    }
                    patched += 1
                    display = (
                        entry.get('selected')
                        or entry.get('original')
                        or entry.get('path')
                    )
                    print('Patched list entry for', display)
                    continue
    else:
        print('Unsupported report JSON structure:', type(data))

    if patched:
        bak = report_path + '.bak'
        shutil.move(report_path, bak)
        with open(report_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f'Wrote {report_path} (backup at {bak})')
        print(f'Patched {patched} entries')
    else:
        # Try a relaxed suffix match on filename in case path prefixes differ
        # (examples: moved between directories or different root prefixes).
        relaxed = 0
        sel_fnames = set([Path(s).name for s in sel_paths])
        if isinstance(data, dict):
            for key, val in list(data.items()):
                key_tail = Path(key).name
                if key_tail in sel_fnames:
                    # add a repair object
                    if isinstance(val, dict):
                        val['repair'] = {
                            'exit_code': 0,
                            'output': out_path,
                        }
                    else:
                        data[key] = {
                            'selected': val,
                            'repair': {'exit_code': 0, 'output': out_path},
                        }
                    relaxed += 1
                    print('Relaxed-patched mapping entry for', key)
                    continue
                if isinstance(val, dict):
                    for k in ('selected', 'original', 'path'):
                        vv = val.get(k)
                        if vv and Path(vv).name in sel_fnames:
                            val['repair'] = {
                                'exit_code': 0,
                                'output': out_path,
                            }
                            relaxed += 1
                            print('Relaxed-patched mapping entry for', key)
                            break
        elif isinstance(data, list):
            for idx, entry in enumerate(data):
                if isinstance(entry, str):
                    if Path(entry).name in sel_fnames:
                        data[idx] = {
                            'selected': entry,
                            'repair': {'exit_code': 0, 'output': out_path},
                        }
                        relaxed += 1
                        print('Relaxed-patched list entry for', entry)
                        continue
                elif isinstance(entry, dict):
                    for k in ('selected', 'original', 'path'):
                        vv = entry.get(k)
                        if vv and Path(vv).name in sel_fnames:
                            entry['repair'] = {
                                'exit_code': 0,
                                'output': out_path,
                            }
                            relaxed += 1
                            disp = (
                                entry.get('selected')
                                or entry.get('original')
                                or entry.get('path')
                            )
                            print('Relaxed-patched list entry for', disp)
                            break

        if relaxed:
            bak = report_path + '.bak'
            shutil.move(report_path, bak)
            with open(report_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f'Wrote {report_path} (backup at {bak})')
            print(f'Relaxed-patched {relaxed} entries')
        else:
            print('No matching entry found in', report_path)


def remove_from_to_repair(to_repair_path, sel_paths):
    if not os.path.exists(to_repair_path):
        print('to-repair list not present:', to_repair_path)
        return 0
    raw = open(to_repair_path).read().splitlines()
    lines = [line.rstrip('\n') for line in raw]
    before = len(lines)
    lines = [line for line in lines if line not in sel_paths]
    open(to_repair_path, 'w').write('\n'.join(lines) + ('\n' if lines else ''))
    removed = before - len(lines)
    msg = 'Removed {} entries from {}; {} remain'.format(
        removed,
        to_repair_path,
        len(lines),
    )
    print(msg)
    return removed


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        '--src',
        required=True,
        help='path to repaired output'
    )
    p.add_argument(
        '--patch-only',
        dest='patch_only',
        action='store_true',
        help=(
            'Do not move files; only patch the report based on the '
            'existing src path'
        ),
    )
    p.add_argument(
        '--report',
        default='repair_report_apply.json'
    )
    p.add_argument(
        '--dest-root',
        default='/Volumes/dotad/MUSIC/REPAIRED/final_selection'
    )
    p.add_argument(
        '--to-repair',
        default='/tmp/to_repair.txt'
    )
    args = p.parse_args()

    src = args.src
    report = args.report
    dest_root = args.dest_root
    to_repair = args.to_repair

    # If patch-only is requested, don't move anything --- assume src already
    # exists at the final location and just patch the report using its files.
    if args.patch_only:
        dst = src
        # Try to infer a relative path for display
        try:
            rel = os.path.relpath(str(src), '/Volumes/dotad/MUSIC')
        except Exception:
            rel = Path(src).name
    else:
        dst, rel = promote(src, dest_root)

    # possible selected/original forms we might find in the JSON
    sel_candidates = set([src, dst, '/Volumes/dotad/MUSIC/' + rel])

    # If dst is a directory, include all individual file paths
    # (pre- and post-move)
    dst_p = Path(dst)
    src_p = Path(src)
    if dst_p.is_dir():
        for f in dst_p.rglob('*'):
            if f.is_file():
                # add post-move path
                sel_candidates.add(str(f))
                # add pre-move equivalent path (in case report pointed
                # to the pre-move location)
                try:
                    relsub = f.relative_to(dst_p)
                    pre = src_p / relsub
                    sel_candidates.add(str(pre))
                except Exception:
                    # if relative_to fails, skip the pre-move addition
                    pass

    if os.path.exists(report):
        patch_report(report, sel_candidates, dst)
    else:
        print('Report not found, skipping patch:', report)

    remove_from_to_repair(to_repair, sel_candidates)


if __name__ == '__main__':
    main()
