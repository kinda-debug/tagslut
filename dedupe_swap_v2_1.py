#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DD ↔ MUSIC dedupe/health with AUDIO HASH matching (v2.1)
- Phase A: fast hash match (uses cache; no health)
- Phase B: metrics+health with progress and concurrency
- Health modes: fast|full|none
- Robust against files moved during run
"""

import argparse, csv, json, math, os, re, shutil, sqlite3, subprocess, sys, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

AUDIO_EXTS = {
    ".flac", ".mp3", ".m4a", ".aac", ".wav", ".aif", ".aiff", ".aifc",
    ".ogg", ".opus", ".wma", ".mka", ".mkv", ".alac"
}
EXCLUDE_DIR_NAMES_DEFAULT = {
    "_quarantine_from_gemini", "_replacements_backup", "_consumed_dupes",
    ".DS_Store", "@eaDir"
}
CACHE_PATH_DEFAULT = Path.home() / ".cache" / "dedupe_swap_audiohash.json"

HEX32_RE = re.compile(r"[0-9a-fA-F]{32}")
ZERO_HASH = "0" * 32

# -------------------- SQLite helpers --------------------
def db_open(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA mmap_size=268435456;")  # 256 MiB if available
    return conn

def db_ensure_schema(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS meta (
        k TEXT PRIMARY KEY,
        v TEXT
    );
    CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY,
        rel_path TEXT NOT NULL,
        root TEXT NOT NULL,
        ext TEXT NOT NULL,
        size INTEGER NOT NULL,
        mtime_ns INTEGER NOT NULL,
        in_quarantine INTEGER NOT NULL DEFAULT 0,
        audiohash TEXT,
        duration REAL,
        codec TEXT,
        healthy INTEGER,
        health_note TEXT,
        seen_at INTEGER NOT NULL
    ) WITHOUT ROWID;
    CREATE INDEX IF NOT EXISTS idx_files_hash ON files(audiohash);
    CREATE INDEX IF NOT EXISTS idx_files_rel  ON files(rel_path);
    CREATE INDEX IF NOT EXISTS idx_files_ext  ON files(ext);
    CREATE VIEW IF NOT EXISTS v_dupes AS
      SELECT audiohash, COUNT(*) AS n, GROUP_CONCAT(path, char(10)) AS paths
      FROM files
      WHERE audiohash IS NOT NULL AND audiohash != ''
      GROUP BY audiohash
      HAVING n > 1;
    """)
    conn.execute("INSERT OR REPLACE INTO meta(k, v) VALUES('schema_version','1');")

def db_upsert_file(conn: sqlite3.Connection, row: dict):
    conn.execute(
        """
        INSERT INTO files(path, rel_path, root, ext, size, mtime_ns, in_quarantine,
                          audiohash, duration, codec, healthy, health_note, seen_at)
        VALUES(:path, :rel_path, :root, :ext, :size, :mtime_ns, :in_quarantine,
               :audiohash, :duration, :codec, :healthy, :health_note, :seen_at)
        ON CONFLICT(path) DO UPDATE SET
          rel_path=excluded.rel_path,
          root=excluded.root,
          ext=excluded.ext,
          size=excluded.size,
          mtime_ns=excluded.mtime_ns,
          in_quarantine=excluded.in_quarantine,
          audiohash=COALESCE(excluded.audiohash, files.audiohash),
          duration=COALESCE(excluded.duration, files.duration),
          codec=COALESCE(excluded.codec, files.codec),
          healthy=COALESCE(excluded.healthy, files.healthy),
          health_note=COALESCE(excluded.health_note, files.health_note),
          seen_at=excluded.seen_at
        """,
        row
    )

def which(cmd: str) -> Optional[str]:
    from shutil import which as _which
    return _which(cmd)

def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 999, "", f"{type(e).__name__}: {e}"

HAVE_FFPROBE = which("ffprobe") is not None
HAVE_FFMPEG  = which("ffmpeg")  is not None
HAVE_FLAC    = which("flac")    is not None

# -------------------- hashing --------------------

def audio_md5(path: Path) -> Optional[str]:
    """Compute decoded-audio MD5 using ffmpeg md5 muxer; return 32-hex or None."""
    if not HAVE_FFMPEG:
        return None
    rc, out, err = run_cmd(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a", "-f", "md5", "-"])
    if rc != 0:
        return None
    m = HEX32_RE.findall(out) or HEX32_RE.findall(err)
    return (m[-1].lower() if m else None)

def load_cache(cache_path: Path) -> Dict[str, Dict]:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_cache(cache_path: Path, data: Dict[str, Dict]):
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

def cache_key_for(path: Path) -> Optional[str]:
    try:
        st = path.stat()
        return f"{int(st.st_mtime_ns)}:{st.st_size}"
    except FileNotFoundError:
        return None

def get_hash_with_cache(path: Path, cache: Dict[str, Dict], save_every: Optional[Tuple[Path,int]]=None) -> Optional[str]:
    ck = cache_key_for(path)
    if ck is None:
        return None
    sp = str(path)
    ent = cache.get(sp)
    if ent and ent.get("k") == ck:
        cached_h = ent.get("h")
        if cached_h and cached_h != ZERO_HASH:
            return cached_h
        if cached_h == ZERO_HASH:
            # recompute via ffmpeg and update if real
            h2 = audio_md5(path)
            if h2 and h2 != ZERO_HASH:
                cache[sp] = {"k": ck, "h": h2}
                if save_every:
                    cache_path, n = save_every
                    cnt = cache.get("__writes__", 0) + 1
                    cache["__writes__"] = cnt
                    if cnt % n == 0:
                        try:
                            save_cache(cache_path, cache)
                        except Exception:
                            pass
                return h2
    h = audio_md5(path)
    if not h or h == ZERO_HASH:
        cache[sp] = {"k": ck, "h": None}
        return None
    cache[sp] = {"k": ck, "h": h}
    if save_every:
        cache_path, n = save_every
        cnt = cache.get("__writes__", 0) + 1
        cache["__writes__"] = cnt
        if cnt % n == 0:
            try:
                save_cache(cache_path, cache)
            except Exception:
                pass
    return h

# -------------------- probes / health --------------------

def ffprobe_duration(path: Path) -> Optional[float]:
    if not HAVE_FFPROBE:
        return None
    rc, out, _ = run_cmd([
        "ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=nw=1:nk=1", str(path)
    ])
    if rc != 0:
        return None
    try:
        v = float(out.strip())
        return v if math.isfinite(v) and v > 0 else None
    except:
        return None

def codec_info(path: Path) -> Optional[str]:
    if not HAVE_FFPROBE:
        return None
    rc, out, _ = run_cmd([
        "ffprobe","-v","error","-select_streams","a:0",
        "-show_entries","stream=codec_name,codec_type",
        "-of","json", str(path)
    ])
    if rc != 0:
        return None
    try:
        data = json.loads(out)
        for s in data.get("streams", []):
            if s.get("codec_type") == "audio":
                return s.get("codec_name")
    except:
        pass
    return None

def health_check(path: Path, mode: str) -> Tuple[bool, str]:
    """
    mode:
      - 'none' : assume healthy (fastest)
      - 'fast' : cheap sanity (ffprobe ok) -> healthy; else unhealthy
      - 'full' : flac -t for .flac, else full ffmpeg decode to null with -xerror
    """
    ext = path.suffix.lower()
    if mode == "none":
        return True, "assumed healthy (none)"
    if mode == "fast":
        # ffprobe access implies container/stream parsable
        ok = ffprobe_duration(path) is not None
        return (ok, "ffprobe ok" if ok else "ffprobe failed")
    # full
    if ext == ".flac" and HAVE_FLAC:
        rc,_,_ = run_cmd(["flac","-t",str(path)])
        return (rc == 0, "flac -t ok" if rc == 0 else "flac -t failed")
    if HAVE_FFMPEG:
        rc,_,_ = run_cmd(["ffmpeg","-v","error","-xerror","-i",str(path),"-f","null","-"])
        return (rc == 0, "ffmpeg decode ok" if rc == 0 else "ffmpeg decode failed")
    return False, "no decoder available"

def file_metrics(path: Path, health_mode: str) -> Dict:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return {"missing": True}
    dur = ffprobe_duration(path)
    healthy, note = health_check(path, health_mode)
    codc = codec_info(path)
    return {
        "missing": False,
        "size": size,
        "duration": dur,
        "healthy": healthy,
        "health_note": note,
        "codec": codc or ""
    }

# -------------------- decisions & fs ops --------------------

def better_choice(m: Dict, d: Dict, tol_sec: float) -> Tuple[str, str]:
    if m.get("missing") and d.get("missing"):
        return "SKIP_BOTH_MISSING", "both moved during run"
    if m.get("missing"):
        # MUSIC missing; if DD exists, propose swap-in into original MUSIC path
        return "SWAP_IN", "MUSIC missing; DD exists"
    if d.get("missing"):
        return "KEEP_MUSIC", "DD missing; keep MUSIC"

    m_ok, d_ok = m["healthy"], d["healthy"]
    m_dur, d_dur = m["duration"], d["duration"]
    m_size, d_size = m["size"], d["size"]

    if not m_ok and not d_ok:
        return "BOTH_CORRUPT", "Both failed health checks"
    if m_ok and not d_ok:
        return "KEEP_MUSIC", "MUSIC healthy; DD not"
    if d_ok and not m_ok:
        return "SWAP_IN", "DD healthy; MUSIC not"

    # both healthy → prefer longer (with tolerance), then larger
    if (m_dur is not None) and (d_dur is not None):
        if d_dur > m_dur + tol_sec:
            return "SWAP_IN", f"DD longer ({d_dur:.3f}s > {m_dur:.3f}s)"
        if m_dur > d_dur + tol_sec:
            return "KEEP_MUSIC", f"MUSIC longer ({m_dur:.3f}s > {d_dur:.3f}s)"
        if d_size > m_size:
            return "SWAP_IN", f"Dur≈; DD larger ({d_size} > {m_size})"
        return "KEEP_MUSIC", f"Dur≈; MUSIC larger-or-equal ({m_size} >= {d_size})"

    # if durations missing, fall back to size
    if d_size > m_size:
        return "SWAP_IN", f"No/partial duration; DD larger ({d_size} > {m_size})"
    return "KEEP_MUSIC", f"No/partial duration; MUSIC larger-or-equal ({m_size} >= {d_size})"

def ensure_dir(p: Path): p.mkdir(parents=True, exist_ok=True)

def unique_backup_path(base: Path) -> Path:
    """Return a unique backup path based on 'base' by appending a timestamp and counter if needed."""
    if not base.exists():
        return base
    ts = time.strftime("%Y%m%d%H%M%S")
    candidate = base.with_suffix(base.suffix + f".bak{ts}")
    i = 1
    while candidate.exists():
        candidate = base.with_suffix(base.suffix + f".bak{ts}_{i}")
        i += 1
    return candidate

def safe_move(src: Path, dst: Path):
    ensure_dir(dst.parent)
    tmp = dst.with_suffix(dst.suffix + ".swaptmp")
    if tmp.exists(): tmp.unlink()
    shutil.move(str(src), str(tmp))
    if dst.exists(): dst.unlink()
    shutil.move(str(tmp), str(dst))

def copy_over(src: Path, dst: Path):
    ensure_dir(dst.parent)
    tmp = dst.with_suffix(dst.suffix + ".copytmp")
    if tmp.exists(): tmp.unlink()
    shutil.copy2(str(src), str(tmp))
    if dst.exists(): dst.unlink()
    shutil.move(str(tmp), str(dst))

# -------------------- helpers --------------------

def best_music_path_for_hash(paths: List[Path]) -> Path:
    """Cheap pick during Phase A: prefer non-quarantine; otherwise first.
    Real duration/health comparison happens in Phase B."""
    for p in paths:
        if "_quarantine_from_gemini" not in p.parts:
            return p
    return paths[0]

def should_skip_dirname(name: str, excluded: set) -> bool:
    return name in excluded

# -------------------- build DB --------------------
def build_sqlite_db(music_root: Path, cache_path: Path, exts: set, exclude_names: set,
                    health_mode: str, workers: int, metrics_workers: int, db_path: Path,
                    prune: bool):
    scan_ts = int(time.time())
    print(f"Building SQLite DB for MUSIC at {db_path} …", file=sys.stderr, flush=True)
    conn = db_open(db_path)
    with conn:
        db_ensure_schema(conn)

    # Collect file list (respect exclude names)
    music_files: List[Path] = []
    for root, dirs, fs in os.walk(music_root):
        dirs[:] = [d for d in dirs if not should_skip_dirname(d, exclude_names)]
        for f in fs:
            p = Path(root) / f
            if p.suffix.lower() in exts:
                music_files.append(p)
    print(f"[db] MUSIC candidates: {len(music_files)} files", file=sys.stderr, flush=True)

    cache = load_cache(cache_path)

    def record_for(p: Path) -> Optional[dict]:
        try:
            st = p.stat()
        except FileNotFoundError:
            return None
        rel = None
        try:
            rel = p.resolve().relative_to(music_root.resolve())
        except Exception:
            rel = Path(p.name)
        h = get_hash_with_cache(p, cache, (cache_path, 500))
        # Avoid poisoning DB with zero/None hashes
        if h == ZERO_HASH:
            h = None
        dur = ffprobe_duration(p)
        healthy, note = health_check(p, health_mode)
        codc = codec_info(p)
        in_quar = 1 if "_quarantine_from_gemini" in p.parts else 0
        return {
            "path": str(p),
            "rel_path": str(rel),
            "root": str(music_root),
            "ext": p.suffix.lower(),
            "size": st.st_size,
            "mtime_ns": int(st.st_mtime_ns),
            "in_quarantine": in_quar,
            "audiohash": h,
            "duration": float(dur) if dur is not None else None,
            "codec": codc or None,
            "healthy": 1 if healthy else 0,
            "health_note": note,
            "seen_at": scan_ts
        }

    rows_buf = []
    inserted = 0

    # Compute metrics concurrently
    def worker(p: Path):
        try:
            return record_for(p)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=max(1, metrics_workers)) as ex:
        futs = [ex.submit(worker, p) for p in music_files]
        for i, ft in enumerate(as_completed(futs), 1):
            rec = ft.result()
            if i % 200 == 0:
                print(f"[db] metrics {i}/{len(music_files)}", file=sys.stderr, flush=True)
            if not rec:
                continue
            rows_buf.append(rec)
            # Flush in batches
            if len(rows_buf) >= 500:
                with conn:
                    for r in rows_buf:
                        db_upsert_file(conn, r)
                inserted += len(rows_buf)
                rows_buf.clear()

    # Flush remaining
    if rows_buf:
        with conn:
            for r in rows_buf:
                db_upsert_file(conn, r)
        inserted += len(rows_buf)
        rows_buf.clear()

    if prune:
        # delete stale rows for this root not seen in this scan
        with conn:
            conn.execute(
                "DELETE FROM files WHERE root = ? AND seen_at < ?",
                (str(music_root), scan_ts)
            )

    with conn:
        conn.execute("ANALYZE;")

    print(f"[db] Upserted {inserted} rows into {db_path}", file=sys.stderr, flush=True)
    # Persist cache too
    try:
        save_cache(cache_path, load_cache(cache_path))
    except Exception:
        pass

# -------------------- main --------------------

def main():
    ap = argparse.ArgumentParser(description="Ensure best copies in MUSIC vs DD using AUDIO HASH (v2.1).")
    ap.add_argument("--music-root", default="/Volumes/dotad/MUSIC", type=str)
    ap.add_argument("--dupe-root",  default="/Volumes/dotad/DD",     type=str)
    ap.add_argument("--report",     default=str(Path.cwd() / f"dedupe_report_{int(time.time())}.csv"), type=str)
    ap.add_argument("--backup-root",   default="/Volumes/dotad/DD/_replacements_backup", type=str)
    ap.add_argument("--consumed-root", default="/Volumes/dotad/DD/_consumed_dupes", type=str)
    ap.add_argument("--tolerance-sec", default=0.5, type=float)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--workers", default=os.cpu_count() or 4, type=int, help="threads for hashing")
    ap.add_argument("--metrics-workers", default=max(2, (os.cpu_count() or 4)//2), type=int, help="threads for metrics/health")
    ap.add_argument("--exts", default=",".join(sorted(AUDIO_EXTS)), type=str)
    ap.add_argument("--cache", default=str(CACHE_PATH_DEFAULT), type=str)
    ap.add_argument("--cache-save-every", default=500, type=int, help="incremental cache save cadence")
    ap.add_argument("--include-quarantine", action="store_true", help="allow quarantine folder as keepers")
    ap.add_argument("--extra-exclude", default="", type=str, help="comma-separated extra dir names to ignore")
    ap.add_argument("--health", choices=["fast","full","none"], default="fast",
                    help="health check mode (default fast). NOTE: full is slower.")
    ap.add_argument("--build-db", action="store_true",
                    help="Scan MUSIC and (re)build a SQLite index, then exit")
    ap.add_argument("--db-path", default=str(Path.home() / ".cache" / "music_index.db"), type=str,
                    help="Path to the SQLite database to create/update")
    ap.add_argument("--db-prune", action="store_true",
                    help="Prune rows for files under MUSIC that were not seen in this run")
    ap.add_argument("--db-health", choices=["none","fast","full"], default="fast",
                    help="Health mode to use while building the DB (default: fast)")
    args = ap.parse_args()

    music_root = Path(args.music_root).resolve()
    dupe_root  = Path(args.dupe_root).resolve()
    backup_root   = Path(args.backup_root).resolve()
    consumed_root = Path(args.consumed_root).resolve()
    tol = float(args.tolerance_sec)
    exts = {("." + e.strip().lower() if not e.strip().startswith(".") else e.strip().lower())
            for e in args.exts.split(",") if e.strip()}

    if not music_root.exists():
        print(f"ERROR: MUSIC root not found: {music_root}", file=sys.stderr); sys.exit(2)
    if not dupe_root.exists():
        print(f"ERROR: DUPE root not found: {dupe_root}", file=sys.stderr); sys.exit(2)
    if not HAVE_FFMPEG:
        print("ERROR: ffmpeg not found (brew install ffmpeg)", file=sys.stderr); sys.exit(2)

    exclude_names = set(EXCLUDE_DIR_NAMES_DEFAULT)
    if args.include_quarantine and "_quarantine_from_gemini" in exclude_names:
        exclude_names.remove("_quarantine_from_gemini")
    if args.extra_exclude:
        exclude_names |= {x.strip() for x in args.extra_exclude.split(",") if x.strip()}

    # Optional: build SQLite DB for MUSIC and exit
    if args.build_db:
        # reuse exclude_names logic; include/exclude quarantine depending on --include-quarantine
        build_sqlite_db(
            music_root=music_root,
            cache_path=Path(args.cache),
            exts=exts,
            exclude_names=exclude_names,
            health_mode=args.db_health,
            workers=int(args.workers),
            metrics_workers=int(args.metrics_workers),
            db_path=Path(args.db_path),
            prune=bool(args.db_prune)
        )
        print("DB build completed.", file=sys.stderr, flush=True)
        return

    # Load cache
    cache_path = Path(args.cache)
    cache = load_cache(cache_path)

    # ---------- Phase A: build MUSIC hash index ----------
    print("Hash-indexing MUSIC…", file=sys.stderr)
    music_files: List[Path] = []
    for root, dirs, fs in os.walk(music_root):
        dirs[:] = [d for d in dirs if not should_skip_dirname(d, exclude_names)]
        for f in fs:
            p = Path(root)/f
            if p.suffix.lower() in exts:
                music_files.append(p)

    h2paths: Dict[str, List[Path]] = defaultdict(list)
    def m_worker(p: Path):
        try:
            h = get_hash_with_cache(p, cache, (cache_path, args.cache_save_every))
            return (p, h)
        except Exception:
            return (p, None)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = [ex.submit(m_worker, p) for p in music_files]
        for i, ft in enumerate(as_completed(futs), 1):
            if i % 200 == 0:
                print(f"[hash] MUSIC {i}/{len(music_files)}", file=sys.stderr, flush=True)
            p, h = ft.result()
            if h and h != ZERO_HASH:
                h2paths[h].append(p)

    # ---------- Phase A: scan DD & match ----------
    print("Scanning DD…", file=sys.stderr, flush=True)
    dd_files: List[Path] = []
    # Exclude our own working folders under DD, but allow quarantine
    dd_exclude_names = {"_replacements_backup", "_consumed_dupes", "@eaDir", ".DS_Store"}
    for root, dirs, fs in os.walk(dupe_root):
        # prevent walking into backup/consumed folders
        dirs[:] = [d for d in dirs if d not in dd_exclude_names]
        for f in fs:
            p = Path(root) / f
            if p.suffix.lower() in exts:
                dd_files.append(p)
    print(f"[scan] DD candidates: {len(dd_files)} files", file=sys.stderr, flush=True)

    pairs = []  # list of (music_path, dd_path)
    rows = []
    totals = {
        "dd_hashed": 0, "pairs": 0, "missing_in_music": 0, "errors": 0,
        "keep_music": 0, "swap_in": 0, "both_corrupt": 0, "no_decision": 0
    }

    def dd_worker(p: Path):
        try:
            h = get_hash_with_cache(p, cache, (cache_path, args.cache_save_every))
            return (p, h)
        except Exception:
            return (p, None)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = [ex.submit(dd_worker, p) for p in dd_files]
        for i, ft in enumerate(as_completed(futs), 1):
            p, h = ft.result()
            if i % 50 == 0:
                print(f"[hash] DD {i}/{len(dd_files)}", file=sys.stderr, flush=True)
            if h is None:
                totals["errors"] += 1
                rows.append({
                    "status":"ERROR","reason":"audio hash failed","match_type":"audiohash",
                    "music_path":"","dd_path":str(p),"in_quarantine":"",
                    "m_duration":"","d_duration":"","m_size":"","d_size":"",
                    "m_healthy":"","d_healthy":"","m_codec":"","d_codec":""
                })
                continue
            totals["dd_hashed"] += 1
            m_candidates = h2paths.get(h, [])
            if not m_candidates:
                totals["missing_in_music"] += 1
                rows.append({
                    "status":"MISSING_IN_MUSIC","reason":"no audiohash match in MUSIC","match_type":"audiohash",
                    "music_path":"","dd_path":str(p),"in_quarantine":"",
                    "m_duration":"","d_duration":"","m_size":str(p.stat().st_size) if p.exists() else "",
                    "m_healthy":"","d_healthy":"","m_codec":"","d_codec":""
                })
                continue
            mp = best_music_path_for_hash(m_candidates)
            pairs.append((mp, p))

    # Deduplicate pairs by MUSIC path to avoid multiple swaps to the same file in a single run
    seen_music = set()
    deduped_pairs = []
    for mp, dp in pairs:
        if mp in seen_music:
            continue
        seen_music.add(mp)
        deduped_pairs.append((mp, dp))
    pairs = deduped_pairs

    # ---------- Phase B: metrics & decisions ----------
    print(f"Evaluating metrics/health on {len(pairs)} matched pairs (health={args.health})…", file=sys.stderr, flush=True)

    def metric_worker(mp: Path, dp: Path):
        m = file_metrics(mp, "full" if (args.apply and args.health=="fast") else args.health)
        d = file_metrics(dp, "full" if (args.apply and args.health=="fast") else args.health)
        decision, reason = better_choice(m, d, tol)
        return (mp, dp, m, d, decision, reason)

    with ThreadPoolExecutor(max_workers=max(1, args.metrics_workers)) as ex:
        futs = [ex.submit(metric_worker, mp, dp) for (mp, dp) in pairs]
        for i, ft in enumerate(as_completed(futs), 1):
            if i % 100 == 0:
                print(f"[metrics] {i}/{len(pairs)}", file=sys.stderr, flush=True)
            try:
                mp, dp, m, d, decision, reason = ft.result()
            except Exception as e:
                totals["errors"] += 1
                rows.append({
                    "status":"ERROR","reason":f"metrics failed: {type(e).__name__}: {e}","match_type":"audiohash",
                    "music_path":"","dd_path":"","in_quarantine":"",
                    "m_duration":"","d_duration":"","m_size":"","d_size":"",
                    "m_healthy":"","d_healthy":"","m_codec":"","d_codec":""
                })
                continue

            # Apply if needed
            if args.apply and decision == "SWAP_IN":
                try:
                    rel = mp.resolve().relative_to(music_root.resolve())
                except Exception:
                    rel = Path(mp.name)
                backup_target = unique_backup_path(backup_root / rel)
                try:
                    print(f"SWAP: MUSIC -> {backup_target}", file=sys.stderr)
                    safe_move(mp, backup_target)
                except Exception as e:
                    # if MUSIC missing now, continue by copying DD into place
                    pass
                try:
                    print(f"SWAP: DD -> MUSIC at {mp}", file=sys.stderr)
                    copy_over(dp, mp)
                except Exception as e:
                    pass
                try:
                    dd_rel = dp.resolve().relative_to(dupe_root.resolve())
                except Exception:
                    dd_rel = Path(dp.name)
                consumed_target = consumed_root / dd_rel
                try:
                    print(f"SWAP: DD original -> {consumed_target}", file=sys.stderr)
                    safe_move(dp, consumed_target)
                except Exception:
                    pass

            totals["pairs"] += 1
            if decision == "KEEP_MUSIC": totals["keep_music"] += 1
            elif decision == "SWAP_IN": totals["swap_in"] += 1
            elif decision == "BOTH_CORRUPT": totals["both_corrupt"] += 1
            else: totals["no_decision"] += 1

            try_in_quar = "1" if "_quarantine_from_gemini" in Path(mp).parts else "0"
            rows.append({
                "status": decision, "reason": reason, "match_type":"audiohash",
                "music_path": str(mp), "dd_path": str(dp),
                "in_quarantine": try_in_quar,
                "m_duration": f"{m.get('duration'):.3f}" if m.get("duration") is not None else "",
                "d_duration": f"{d.get('duration'):.3f}" if d.get("duration") is not None else "",
                "m_size": f"{m.get('size','')}", "d_size": f"{d.get('size','')}",
                "m_healthy": "1" if m.get("healthy") else "0",
                "d_healthy": "1" if d.get("healthy") else "0",
                "m_codec": m.get("codec",""), "d_codec": d.get("codec","")
            })

    # Save cache one last time
    try: save_cache(cache_path, cache)
    except Exception: pass

    # Write report
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "status","reason","match_type","in_quarantine","music_path","dd_path",
            "m_duration","d_duration","m_size","d_size","m_healthy","d_healthy","m_codec","d_codec"
        ]
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print("\nDone.")
    print(f"Report: {report_path}")
    print("Summary:")
    for k in ["pairs","keep_music","swap_in","both_corrupt","missing_in_music","no_decision","errors","dd_hashed"]:
        print(f"  {k}: {totals.get(k,0)}")

    problems = [r for r in rows if r["status"] == "BOTH_CORRUPT"]
    if problems:
        print("\nFiles that are corrupted with no better duplicate found:")
        for r in problems:
            print(f"  MUSIC: {r['music_path']}\n     DD: {r['dd_path']}")
    else:
        print("\nNo pairs where both copies failed health checks.")
    # Fin
if __name__ == "__main__":
    main()
