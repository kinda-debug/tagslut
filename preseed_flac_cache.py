#!/usr/bin/env python3
# Preseed dedupe_swap_v2 cache for FLAC using metaflac's built-in audio MD5.
import os, sys, json, subprocess
from pathlib import Path

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def have(cmd):
    from shutil import which
    return which(cmd) is not None

def cache_key(p: Path) -> str:
    st = p.stat()
    return f"{int(st.st_mtime_ns)}:{st.st_size}"

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--music-root", default="/Volumes/dotad/MUSIC")
    ap.add_argument("--dupe-root", default=None, help="Optional: also preseed DD")
    ap.add_argument("--cache", default=str(Path.home()/".cache"/"dedupe_swap_audiohash.json"))
    ap.add_argument("--exts", default=".flac", help="Comma-separated (default: .flac)")
    ap.add_argument("--save-every", type=int, default=500)
    args = ap.parse_args()

    if not have("metaflac"):
        print("ERROR: metaflac not found. Install with: brew install flac", file=sys.stderr)
        sys.exit(2)

    roots = [Path(args.music_root)]
    if args.dupe_root: roots.append(Path(args.dupe_root))
    exts = {e if e.startswith(".") else "."+e for e in (x.strip().lower() for x in args.exts.split(",") if x.strip())}

    cache_path = Path(args.cache)
    cache = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    to_process = []
    for root in roots:
        if not root.exists(): continue
        for r, ds, fs in os.walk(root):
            for f in fs:
                p = Path(r)/f
                if p.suffix.lower() in exts:
                    to_process.append(p)

    done=0; wrote=0; skipped=0; failed=0
    for p in to_process:
        try:
            k = cache_key(p)
            ent = cache.get(str(p))
            if ent and ent.get("k")==k and ent.get("h"):
                skipped+=1; continue
            rc,out,err = run(["metaflac","--show-md5sum", str(p)])
            if rc!=0 or not out or len(out)<32:
                failed+=1; continue
            md5 = out.splitlines()[0].split()[-1].strip().lower()
            if len(md5)!=32 or set(md5)-set("0123456789abcdef"):
                failed+=1; continue
            cache[str(p)] = {"k": k, "h": md5}
            wrote+=1
        except Exception:
            failed+=1
        done+=1
        if wrote and wrote % args.save_every == 0:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"[cache] saved ({wrote} new) …")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"Done. files={len(to_process)} wrote={wrote} skipped={skipped} failed={failed}")
    print(f"Cache: {cache_path}")

if __name__ == "__main__":
    main()
