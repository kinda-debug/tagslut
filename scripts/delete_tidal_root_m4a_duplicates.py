#!/usr/bin/env python3
from pathlib import Path


def main() -> int:
    root = Path("/Volumes/MUSIC/staging/tidal")
    deleted = 0
    for m4a in sorted(root.glob("*.m4a")):
        flac = m4a.with_suffix(".flac")
        if flac.exists():
            m4a.unlink()
            deleted += 1
            print(f"deleted: {m4a.name}")
    print(f"deleted_count: {deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
