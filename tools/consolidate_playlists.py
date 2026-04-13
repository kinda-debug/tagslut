#!/usr/bin/env python3
import argparse
import datetime
import os
import pathlib
import shutil


PLAYLISTS_ROOT = pathlib.Path("/Volumes/MUSIC/playlists")


def _iso_mtime(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def _is_digits(s: str) -> bool:
    if not s:
        return False
    for ch in s:
        if ch < "0" or ch > "9":
            return False
    return True


def _has_timestamp_pattern(filename: str) -> bool:
    # Matches: _YYYYMMDD_HHMMSS or -YYYYMMDD-HHMMSS anywhere in the filename.
    n = len(filename)
    for i in range(n):
        if filename[i] not in "_-":
            continue
        if i + 1 + 8 + 1 + 6 > n:
            continue
        date_part = filename[i + 1 : i + 1 + 8]
        mid = filename[i + 1 + 8]
        time_part = filename[i + 1 + 8 + 1 : i + 1 + 8 + 1 + 6]
        if filename[i] == "_" and mid != "_":
            continue
        if filename[i] == "-" and mid != "-":
            continue
        if _is_digits(date_part) and _is_digits(time_part):
            return True
    return False


def _basename_any(path_str: str) -> str:
    s = path_str.strip().replace("\\", "/")
    return os.path.basename(s)


def _read_playlist_tracks(path: pathlib.Path) -> list[str]:
    tracks: list[str] = []
    with path.open("r", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith("#"):
                continue
            tracks.append(s)
    return tracks


def _walk_files(root: pathlib.Path) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = pathlib.Path(dirpath)
        pruned: list[str] = []
        for d in dirnames:
            if d.startswith("_archive_") or d.startswith("_junk_"):
                continue
            pruned.append(d)
        dirnames[:] = pruned
        for name in filenames:
            p = current / name
            try:
                if os.path.islink(p):
                    continue
            except OSError:
                continue
            lower = name.lower()
            if not (
                lower.endswith(".m3u")
                or lower.endswith(".m3u8")
                or lower.endswith(".bak")
                or lower.endswith(".txt")
                or lower.endswith(".zip")
                or lower.endswith(".xml")
                or name == ".DS_Store"
            ):
                continue
            files.append(p)
    return files


def _bucket_key(bucket: str) -> int:
    order = {"CANONICAL": 0, "ARCHIVE": 1, "JUNK": 2, "SKIP": 3}
    return order.get(bucket, 99)


def _choose_keeper(paths: list[pathlib.Path], mtimes: dict[pathlib.Path, float], root: pathlib.Path) -> pathlib.Path:
    def key(p: pathlib.Path) -> tuple[float, int, str]:
        try:
            rel = p.relative_to(root)
            depth = len(rel.parts)
        except Exception:
            depth = 10**9
        return (-mtimes.get(p, 0.0), depth, str(p))
    return min(paths, key=key)


def _unique_destination_path(dest: pathlib.Path) -> pathlib.Path:
    if not dest.exists():
        return dest
    suffix = "".join(dest.suffixes)
    base = dest.name[: -len(suffix)] if suffix else dest.name
    for i in range(1, 10_000):
        candidate = dest.with_name(f"{base}_{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Unable to find unique destination for: {dest}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse, deduplicate, classify, and consolidate playlists under /Volumes/MUSIC/playlists/")
    parser.add_argument("--apply", action="store_true", help="Apply moves (otherwise dry-run report only)")
    args = parser.parse_args()

    root = PLAYLISTS_ROOT
    if not root.exists() or not root.is_dir():
        print(f"ERROR: playlists root not found or not a directory: {root}")
        return 2

    today = datetime.date.today().strftime("%Y%m%d")
    archive_root = root / f"_archive_{today}"
    junk_root = root / f"_junk_{today}"
    log_path = root / f"_consolidation_log_{today}.txt"

    all_files = _walk_files(root)
    entries: list[dict] = []
    mtimes: dict[pathlib.Path, float] = {}

    for p in sorted(all_files, key=str):
        name_lower = p.name.lower()
        is_playlist = name_lower.endswith(".m3u") or name_lower.endswith(".m3u8")
        is_bak = name_lower.endswith(".bak")
        try:
            mtime = os.path.getmtime(p)
        except OSError:
            continue
        mtimes[p] = mtime

        if not is_playlist and not is_bak:
            entries.append({"path": p, "mtime": mtime, "tracks": None, "norm": None,
                            "track_count": None, "bucket": "SKIP", "reason": "",
                            "duplicate_of": None, "rel": None, "is_playlist": False, "is_bak": False})
            continue

        tracks = _read_playlist_tracks(p)
        norm = tuple(_basename_any(t) for t in tracks)
        entry = {"path": p, "mtime": mtime, "tracks": tracks, "norm": norm,
                 "track_count": len(tracks), "bucket": None, "reason": "",
                 "duplicate_of": None, "rel": p.relative_to(root), "is_playlist": is_playlist, "is_bak": is_bak}
        entries.append(entry)

    for e in entries:
        if e["bucket"] == "SKIP":
            continue
        p: pathlib.Path = e["path"]

        junk_reason = ""
        if p.name == " .m3u8":
            junk_reason = "space_only_filename"
        elif p.name.lower().endswith(".bak"):
            junk_reason = "bak_file"
        else:
            tracks = e["tracks"] or []
            if len(tracks) == 1:
                stem = p.stem.strip()
                upper = stem.upper()
                if (not upper.startswith("DJ")) and (not upper.startswith("PARTY")) and (" - " in stem):
                    junk_reason = "single_track_artist_title_filename"

        if junk_reason:
            e["bucket"] = "JUNK"
            e["reason"] = junk_reason

    playlist_dedupe_groups: dict[tuple[str, ...], list[dict]] = {}
    for e in entries:
        if e.get("bucket") is not None:
            continue
        if not e.get("is_playlist", False):
            continue
        playlist_dedupe_groups.setdefault(e["norm"], []).append(e)

    for norm, group in playlist_dedupe_groups.items():
        if len(group) <= 1:
            continue
        keeper = _choose_keeper([e["path"] for e in group], mtimes, root)
        for e in group:
            if e["path"] != keeper:
                e["duplicate_of"] = keeper

    for e in entries:
        if e["bucket"] in ("SKIP", "JUNK"):
            continue
        p: pathlib.Path = e["path"]
        rel: pathlib.Path = e["rel"]

        if e.get("duplicate_of") is not None:
            e["bucket"] = "ARCHIVE"
            e["reason"] = f"duplicate_of={e['duplicate_of']}"
            continue

        if _has_timestamp_pattern(p.name):
            e["bucket"] = "ARCHIVE"
            e["reason"] = "timestamp"
            continue

        if len(rel.parts) > 1:
            e["bucket"] = "ARCHIVE"
            e["reason"] = "subdirectory"
            continue

        e["bucket"] = "CANONICAL"

    grouped: dict[str, list[dict]] = {}
    for e in entries:
        grouped.setdefault(e["bucket"], []).append(e)

    for bucket in sorted(grouped.keys(), key=_bucket_key):
        print(f"\n== {bucket} ==")
        for e in sorted(grouped[bucket], key=lambda x: str(x["path"])):
            p = e["path"]
            mtime = _iso_mtime(e["mtime"])
            if bucket == "SKIP":
                print(f"- {p} | {mtime} | tracks=-")
                continue
            print(f"- {p} | {mtime} | tracks={e['track_count']}" + (f" | {e['reason']}" if e["reason"] else ""))

    if not args.apply:
        return 0

    moves: list[tuple[pathlib.Path, pathlib.Path]] = []
    for e in entries:
        bucket = e["bucket"]
        if bucket not in ("ARCHIVE", "JUNK"):
            continue
        src: pathlib.Path = e["path"]
        rel: pathlib.Path = e["rel"]
        if bucket == "ARCHIVE":
            dest = archive_root / rel
        else:
            dest = junk_root / src.name
        moves.append((src, dest))

    moved_archive = 0
    moved_junk = 0
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} apply start\n")
        for src, dest in moves:
            try:
                if not src.exists():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                final_dest = _unique_destination_path(dest)
                shutil.move(str(src), str(final_dest))
                log.write(f"MOVE {src} -> {final_dest}\n")
                if final_dest.is_relative_to(archive_root):
                    moved_archive += 1
                else:
                    moved_junk += 1
            except Exception as ex:
                log.write(f"ERROR moving {src} -> {dest}: {ex}\n")
        log.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} apply end\n")

    canonical_count = len(grouped.get("CANONICAL", []))
    print(f"\nSUMMARY: {canonical_count} canonical kept, {moved_archive} archived, {moved_junk} junked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
