#!/usr/bin/env python3
import argparse
import csv
import os
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple, Optional


@dataclass
class FileRecord:
    path: str
    checksum: str
    duration: Optional[float]
    sample_rate: Optional[int]
    bit_rate: Optional[int]
    bit_depth: Optional[int]
    in_music: bool
    exists: bool
    in_gemini: bool


def quality_key(rec: FileRecord) -> Tuple[float, int, int, int]:
    """
    Option A: rank by duration, bit_depth, sample_rate, bit_rate.
    Missing values are treated as 0.
    """
    dur = rec.duration if rec.duration is not None else 0.0
    bd = rec.bit_depth if rec.bit_depth is not None else 0
    sr = rec.sample_rate if rec.sample_rate is not None else 0
    br = rec.bit_rate if rec.bit_rate is not None else 0
    return (dur, bd, sr, br)


def derive_track_key(path: str) -> str:
    """
    Very simple heuristic to group 'same track' by filename only.
    Lower-cased basename without extension.
    This is only used to detect DIFFERENT_VERSIONS candidates.
    """
    base = os.path.basename(path)
    base_no_ext, _ = os.path.splitext(base)
    return base_no_ext.strip().lower()


def load_gemini_paths(gemini_list_path: str) -> Set[str]:
    if not gemini_list_path:
        return set()
    gemini_paths: Set[str] = set()
    with open(gemini_list_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                gemini_paths.add(line)
    return gemini_paths


def load_library(
    db_path: str,
    music_root: str,
    gemini_paths: Set[str],
) -> Dict[str, List[FileRecord]]:
    """
    Load all rows from library_files and group them by checksum.
    Returns: checksum -> list[FileRecord]
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    q = """
        SELECT
            path,
            checksum,
            duration,
            sample_rate,
            bit_rate,
            bit_depth
        FROM library_files;
    """
    rows = cur.execute(q).fetchall()
    conn.close()

    music_root_norm = music_root.rstrip("/") + "/"

    clusters: Dict[str, List[FileRecord]] = defaultdict(list)

    for path, checksum, duration, sample_rate, bit_rate, bit_depth in rows:
        if not checksum:
            # skip rows without checksum: cannot reconcile
            continue

        in_music = path.startswith(music_root_norm)
        exists = os.path.exists(path)
        in_gemini = path in gemini_paths

        rec = FileRecord(
            path=path,
            checksum=checksum,
            duration=duration,
            sample_rate=sample_rate,
            bit_rate=bit_rate,
            bit_depth=bit_depth,
            in_music=in_music,
            exists=exists,
            in_gemini=in_gemini,
        )
        clusters[checksum].append(rec)

    return clusters


def detect_different_versions(clusters: Dict[str, List[FileRecord]]) -> Set[str]:
    """
    Build a map from (track_key) to set of checksums and mark those
    where the same 'track' appears with different checksums.
    Returns a set of checksums that belong to DIFFERENT_VERSIONS groups.
    """
    track_to_checksums: Dict[str, Set[str]] = defaultdict(set)

    for checksum, recs in clusters.items():
        for rec in recs:
            key = derive_track_key(rec.path)
            track_to_checksums[key].add(checksum)

    diff_version_checksums: Set[str] = set()
    for key, chks in track_to_checksums.items():
        if len(chks) > 1:
            diff_version_checksums.update(chks)

    return diff_version_checksums


def reconcile(
    db_path: str,
    music_root: str,
    gemini_list_path: Optional[str],
    out_csv: str,
) -> None:
    print("=== RECONCILIATION PASS ===")
    print(f"[INFO] DB:          {db_path}")
    print(f"[INFO] MUSIC root:  {music_root}")
    if gemini_list_path:
        print(f"[INFO] Gemini list: {gemini_list_path}")
    else:
        print("[INFO] Gemini list: (none)")

    # Load Gemini paths
    gemini_paths = load_gemini_paths(gemini_list_path) if gemini_list_path else set()
    print(f"[INFO] Gemini paths loaded: {len(gemini_paths)}")

    # Load DB as checksum clusters
    clusters = load_library(db_path, music_root, gemini_paths)
    print(f"[INFO] Unique checksums loaded: {len(clusters)}")

    # Detect DIFFERENT_VERSIONS groups
    diff_version_checksums = detect_different_versions(clusters)
    print(f"[INFO] Checksums in DIFFERENT_VERSIONS groups: {len(diff_version_checksums)}")

    # Prepare output
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    out_f = open(out_csv, "w", newline="")
    writer = csv.writer(out_f)

    # Header
    writer.writerow(
        [
            "checksum",
            "status",                  # combined flags
            "in_music",                # 0/1
            "outside_music_count",
            "best_source",             # best-quality path
            "music_paths",             # ';'-joined
            "outside_paths",           # ';'-joined
            "gemini_flagged_paths",    # ';'-joined
            "orphan_paths",            # ';'-joined (paths that do not exist on disk)
        ]
    )

    music_root_norm = music_root.rstrip("/") + "/"

    total_clusters = len(clusters)
    processed = 0

    for checksum, recs in clusters.items():
        processed += 1
        if processed % 1000 == 0:
            print(f"[INFO] Processed {processed}/{total_clusters} checksum groups…")

        # Partition into MUSIC and outside
        music_recs = [r for r in recs if r.in_music]
        outside_recs = [r for r in recs if not r.in_music]

        in_music_flag = 1 if len(music_recs) > 0 else 0
        outside_count = len(outside_recs)

        # Determine best_source by quality
        best_rec = max(recs, key=quality_key)

        # Base status
        status_flags = []

        # Orphan detection
        orphan_paths = [r.path for r in recs if not r.exists]
        if orphan_paths:
            status_flags.append("ORPHAN_PATH")

        # Base category by location
        if music_recs and outside_recs:
            # Both inside and outside MUSIC
            best_music_rec = max(music_recs, key=quality_key)
            best_global_rec = best_rec

            if best_global_rec.path.startswith(music_root_norm):
                # MUSIC already holds the best-quality copy
                status_flags.append("OK_MASTER")
                if len(music_recs) > 1:
                    status_flags.append("DUPLICATE_IN_MUSIC")
            else:
                # Better version exists outside MUSIC
                status_flags.append("BETTER_OUTSIDE")

        elif music_recs and not outside_recs:
            # Only in MUSIC
            if len(music_recs) > 1:
                status_flags.append("DUPLICATE_IN_MUSIC")
            else:
                status_flags.append("OK_MASTER")

        elif not music_recs and outside_recs:
            # Only outside MUSIC
            status_flags.append("ONLY_OUTSIDE")
        else:
            # No one in MUSIC, no one outside (theoretically impossible if DB paths are non-empty)
            status_flags.append("UNKNOWN_LOCATION")

        # DIFFERENT_VERSIONS flag
        if checksum in diff_version_checksums:
            status_flags.append("DIFFERENT_VERSIONS")

        # GEMINI flag
        gemini_flagged_paths = [r.path for r in recs if r.in_gemini]
        if gemini_flagged_paths:
            status_flags.append("GEMINI_FLAGGED")

        # Deduplicate flags and join
        status = "+".join(sorted(set(status_flags)))

        music_paths = ";".join(sorted(r.path for r in music_recs))
        outside_paths = ";".join(sorted(r.path for r in outside_recs))
        gemini_paths_str = ";".join(sorted(gemini_flagged_paths))
        orphan_paths_str = ";".join(sorted(orphan_paths))

        writer.writerow(
            [
                checksum,
                status,
                in_music_flag,
                outside_count,
                best_rec.path,
                music_paths,
                outside_paths,
                gemini_paths_str,
                orphan_paths_str,
            ]
        )

    out_f.close()
    print(f"[DONE] Reconciliation CSV written to: {out_csv}")
    print("=== RECONCILIATION PASS COMPLETE ===")


def main():
    parser = argparse.ArgumentParser(description="Checksum-based reconciliation of MUSIC vs all sources.")
    parser.add_argument(
        "--db",
        required=True,
        help="Path to SQLite DB (e.g., artifacts/db/library_final.db)",
    )
    parser.add_argument(
        "--music-root",
        required=True,
        help="Canonical MUSIC root (e.g., /Volumes/dotad/MUSIC)",
    )
    parser.add_argument(
        "--gemini-list",
        required=False,
        default=None,
        help="Path to Gemini duplicate list text file (one path per line). Optional.",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output CSV path for reconciliation report.",
    )

    args = parser.parse_args()

    reconcile(
        db_path=args.db,
        music_root=args.music_root,
        gemini_list_path=args.gemini_list,
        out_csv=args.out,
    )


if __name__ == "__main__":
    main()
