#!/usr/bin/env python3
"""
make_phase_v3_playlists.py

FULL phase_v3 playlists from TAGSLUT_DB (SQLite), table: files.

Outputs:
A) Roon FLAC playlists:
   <FLAC_ROOT>/Playlists_phase_v3/phase_{warmup,lift,peak,closing,archive}.m3u8
   relative to FLAC_ROOT when possible.

B) MP3 review playlists (subset):
   /Volumes/MUSIC/_work/absolute_dj_mp3/Playlists_phase_v3/phase_{...}.m3u8
   relative to MP3_ROOT when possible.

Key change vs earlier version:
- MP3 basename collision handling is deterministic using DB metadata:
  canonical_artist/canonical_title/canonical_album are used to select the best matching folder path.

Prereq:
  export TAGSLUT_DB=/path/to/music.db
"""

from __future__ import annotations

import os
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PHASES = ["warmup", "lift", "peak", "closing", "archive"]
MP3_ROOT = Path("/Volumes/MUSIC/_work/absolute_dj_mp3")


@dataclass(frozen=True)
class Track:
    path: Path
    phase: str
    bpm: Optional[float]
    energy: Optional[float]
    artist: str
    title: str
    album: str
    intensity: float = 0.0


def die(msg: str, code: int = 2) -> None:
    raise SystemExit(msg)


def write_m3u8(path: Path, lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for line in lines:
            f.write(line + "\n")


def safe_float(x: object) -> Optional[float]:
    if x is None:
        return None
    try:
        s = str(x).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def norm_text(s: object) -> str:
    if s is None:
        return ""
    return str(s).strip()


def percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        raise ValueError("percentile() called with empty list")
    if p <= 0:
        return sorted_vals[0]
    if p >= 1:
        return sorted_vals[-1]
    n = len(sorted_vals)
    idx = (n - 1) * p
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def robust_z(x: Optional[float], median: float, iqr: float) -> float:
    if x is None:
        return 0.0
    if iqr <= 1e-12:
        return 0.0
    return (x - median) / iqr


def detect_flac_root(paths: List[Path]) -> Path:
    if not paths:
        die("No paths available to detect FLAC root")

    sample = paths[:6000]
    counts: Counter[str] = Counter()

    for p in sample:
        parts = p.parts
        if len(parts) < 4:
            continue
        for depth in (3, 4, 5, 6):
            if len(parts) > depth:
                prefix = Path(*parts[:depth]).as_posix()
                counts[prefix] += 1

    if not counts:
        return paths[0].parent

    best_prefix, _ = counts.most_common(1)[0]
    return Path(best_prefix)


def build_mp3_index_multi(mp3_root: Path) -> Dict[str, List[Path]]:
    m: Dict[str, List[Path]] = defaultdict(list)
    for p in mp3_root.rglob("*.mp3"):
        m[p.name.lower()].append(p)
    return m


def score_candidate_path(candidate: Path, artist: str, title: str, album: str) -> int:
    """
    Score how well a candidate MP3 path matches DB metadata.
    We only have folder names, so this is a heuristic:
      +3 if artist string appears in path
      +2 if album string appears in path
      +1 if title string appears in path (rare; usually filename)
    """
    hay = candidate.as_posix().lower()
    score = 0

    a = artist.lower().strip()
    al = album.lower().strip()
    t = title.lower().strip()

    if a and a in hay:
        score += 3
    if al and al in hay:
        score += 2
    if t and t in hay:
        score += 1

    return score


def choose_mp3_for_track(
    candidates: List[Path],
    artist: str,
    title: str,
    album: str,
) -> Path:
    """
    Pick the best MP3 candidate among colliding basenames.
    If all scores tie (or are zero), return the first but caller should log.
    """
    scored = [(score_candidate_path(p, artist, title, album), p) for p in candidates]
    scored.sort(key=lambda x: (x[0], x[1].as_posix()), reverse=True)
    return scored[0][1]


def main() -> int:
    db = os.environ.get("TAGSLUT_DB")
    if not db:
        die("TAGSLUT_DB is not set (export it to your music.db path).")

    db_path = Path(db)
    if not db_path.exists():
        die(f"TAGSLUT_DB points to non-existent path: {db_path}")

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cols = {r["name"] for r in cur.execute("PRAGMA table_info(files)")}
    required = {"path", "phase_v3"}
    missing = sorted(required - cols)
    if missing:
        die(f"files table missing required columns: {missing}")

    has_bpm = "canonical_bpm" in cols
    has_energy = "canonical_energy" in cols
    has_artist = "canonical_artist" in cols
    has_title = "canonical_title" in cols
    has_album = "canonical_album" in cols

    select_cols = ["path", "phase_v3"]
    select_cols.append("canonical_bpm" if has_bpm else "NULL AS canonical_bpm")
    select_cols.append("canonical_energy" if has_energy else "NULL AS canonical_energy")
    select_cols.append("canonical_artist" if has_artist else "'' AS canonical_artist")
    select_cols.append("canonical_title" if has_title else "'' AS canonical_title")
    select_cols.append("canonical_album" if has_album else "'' AS canonical_album")

    rows_db = list(cur.execute(f"""
        SELECT {", ".join(select_cols)}
        FROM files
        WHERE phase_v3 IS NOT NULL AND TRIM(phase_v3) <> ''
          AND path IS NOT NULL AND TRIM(path) <> ''
    """))

    if not rows_db:
        die("No rows found with non-empty phase_v3 in files.")

    tracks: List[Track] = []
    all_paths: List[Path] = []

    for r in rows_db:
        ph = norm_text(r["phase_v3"]).lower()
        if ph not in PHASES:
            continue

        p = Path(norm_text(r["path"]))
        if not str(p):
            continue

        bpm = safe_float(r["canonical_bpm"])
        energy = safe_float(r["canonical_energy"])
        artist = norm_text(r["canonical_artist"])
        title = norm_text(r["canonical_title"])
        album = norm_text(r["canonical_album"])

        t = Track(path=p, phase=ph, bpm=bpm, energy=energy, artist=artist, title=title, album=album)
        tracks.append(t)
        all_paths.append(p)

    if not tracks:
        die("phase_v3 exists, but no rows matched expected phases. Check PHASES vs DB content.")

    # Robust normalization on NON-archive subset
    non_archive = [t for t in tracks if t.phase != "archive"]
    bpm_vals = sorted([t.bpm for t in non_archive if t.bpm is not None])
    en_vals = sorted([t.energy for t in non_archive if t.energy is not None])

    if bpm_vals:
        bpm_med = percentile(bpm_vals, 0.50)
        bpm_iqr = max(percentile(bpm_vals, 0.75) - percentile(bpm_vals, 0.25), 1e-12)
    else:
        bpm_med, bpm_iqr = 0.0, 1.0

    if en_vals:
        en_med = percentile(en_vals, 0.50)
        en_iqr = max(percentile(en_vals, 0.75) - percentile(en_vals, 0.25), 1e-12)
    else:
        en_med, en_iqr = 0.0, 1.0

    computed: List[Track] = []
    for t in tracks:
        z_en = robust_z(t.energy, en_med, en_iqr)
        z_bpm = robust_z(t.bpm, bpm_med, bpm_iqr)
        intensity = 0.65 * z_en + 0.35 * z_bpm
        computed.append(Track(
            path=t.path, phase=t.phase, bpm=t.bpm, energy=t.energy,
            artist=t.artist, title=t.title, album=t.album, intensity=intensity
        ))

    flac_root = detect_flac_root(all_paths)
    roon_out = flac_root / "Playlists_phase_v3"

    print(f"DB: {db_path}")
    print(f"Detected FLAC root: {flac_root}")
    print(f"Roon playlists -> {roon_out}")
    print(f"MP3 root: {MP3_ROOT}")

    # Roon playlists (relative to flac_root)
    phase_to_flac_rel: Dict[str, List[str]] = {p: [] for p in PHASES}
    for ph in PHASES:
        ph_tracks = [t for t in computed if t.phase == ph]
        ph_tracks.sort(key=lambda x: x.intensity)
        for t in ph_tracks:
            try:
                rel = t.path.resolve().relative_to(flac_root.resolve()).as_posix()
            except Exception:
                rel = str(t.path)
            phase_to_flac_rel[ph].append(rel)

    for ph in PHASES:
        out = roon_out / f"phase_{ph}.m3u8"
        write_m3u8(out, phase_to_flac_rel[ph])
        print(f"ROON {ph:7s}: {len(phase_to_flac_rel[ph]):6d} tracks")

    # MP3 review playlists
    if not MP3_ROOT.exists():
        print("MP3 root does not exist; skipping MP3 playlists.")
        con.close()
        return 0

    mp3_multi = build_mp3_index_multi(MP3_ROOT)
    collisions = {k: v for k, v in mp3_multi.items() if len(v) > 1}
    if collisions:
        print(f"WARNING: {len(collisions)} mp3 basename collisions under {MP3_ROOT}. Using metadata-based resolution.")

    mp3_out = MP3_ROOT / "Playlists_phase_v3"
    phase_to_mp3_rel: Dict[str, List[str]] = {p: [] for p in PHASES}
    missing_mp3: List[Tuple[str, Path]] = []
    resolved_collisions: List[Tuple[str, List[Path], Path]] = []

    for ph in PHASES:
        ph_tracks = [t for t in computed if t.phase == ph]
        ph_tracks.sort(key=lambda x: x.intensity)

        for t in ph_tracks:
            mp3_name = t.path.with_suffix(".mp3").name.lower()
            cands = mp3_multi.get(mp3_name)
            if not cands:
                missing_mp3.append((ph, t.path))
                continue

            if len(cands) == 1:
                mp3_path = cands[0]
            else:
                mp3_path = choose_mp3_for_track(cands, t.artist, t.title, t.album)
                resolved_collisions.append((mp3_name, cands, mp3_path))

            try:
                rel = mp3_path.resolve().relative_to(MP3_ROOT.resolve()).as_posix()
            except Exception:
                rel = str(mp3_path)

            phase_to_mp3_rel[ph].append(rel)

    print(f"MP3 review playlists -> {mp3_out}")
    for ph in PHASES:
        out = mp3_out / f"phase_{ph}.m3u8"
        write_m3u8(out, phase_to_mp3_rel[ph])
        print(f"MP3  {ph:7s}: {len(phase_to_mp3_rel[ph]):6d} tracks (mapped)")

    if resolved_collisions:
        print("\nResolved MP3 basename collisions:")
        for name, cands, chosen in resolved_collisions[:20]:
            print(f"\n  {name}")
            for c in cands:
                mark = " <== chosen" if c == chosen else ""
                print(f"    {c}{mark}")
        if len(resolved_collisions) > 20:
            print(f"  ... and {len(resolved_collisions) - 20} more collision resolutions")

    print(f"\nMP3 mapping missing (expected for unconverted tracks): {len(missing_mp3)}")
    for ph, p in missing_mp3[:20]:
        print(f"  missing {ph}: {p}")
    if len(missing_mp3) > 20:
        print(f"  ... and {len(missing_mp3) - 20} more")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
