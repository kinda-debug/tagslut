#!/usr/bin/env python3

import argparse
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote, unquote


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aif", ".aiff", ".flac"}
HEX_PREFIX_RE = re.compile(r"^[0-9A-Fa-f]{8}_")


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Rewrite Rekordbox XML track locations to files found under a centralized "
            "POOL_LIBRARY."
        )
    )
    parser.add_argument("source_xml", help="Path to the source Rekordbox XML")
    parser.add_argument("pool_root", help="Path to the centralized POOL_LIBRARY root")
    parser.add_argument("output_xml", help="Path to the rewritten Rekordbox XML")
    parser.add_argument(
        "--report",
        help="Optional path for an unresolved/ambiguous match report",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate matches without writing the rewritten XML",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-track rewrite decisions",
    )
    return parser.parse_args()


def encode_location(path):
    return "file://localhost" + quote(path.as_posix(), safe="/")


def decode_basename(location):
    if not location.startswith("file://"):
        return ""
    raw = location.replace("file://localhost", "").replace("file://", "")
    return Path(unquote(raw)).name


def verbose_print(enabled, message):
    if enabled:
        print(message)


def score_path(path):
    score = 0
    name = path.name
    if "__conflict" in name:
        score -= 100
    if HEX_PREFIX_RE.match(name):
        score -= 10
    if any(part.startswith(".") for part in path.parts):
        score -= 5
    return score


def index_pool(pool_root):
    by_size = defaultdict(list)
    by_size_basename = defaultdict(list)
    counts = Counter()

    for dirpath, dirnames, filenames in os.walk(pool_root):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        current_root = Path(dirpath)
        for filename in filenames:
            if filename.startswith("."):
                continue
            path = current_root / filename
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            by_size[size].append(path)
            by_size_basename[(size, path.name)].append(path)
            counts["audio_files"] += 1

    return by_size, by_size_basename, counts


def choose_match(track, by_size, by_size_basename):
    try:
        size = int(track.get("Size", ""))
    except (TypeError, ValueError):
        return None, "missing_size", []

    basename = decode_basename(track.get("Location", ""))
    exact_matches = by_size_basename.get((size, basename), [])
    if len(exact_matches) == 1:
        return exact_matches[0], "size_basename_unique", exact_matches

    size_matches = by_size.get(size, [])
    if not size_matches:
        return None, "no_size_match", []

    if len(size_matches) == 1:
        return size_matches[0], "size_unique", size_matches

    best_score = max(score_path(path) for path in size_matches)
    best_paths = [path for path in size_matches if score_path(path) == best_score]
    if len(best_paths) == 1:
        return best_paths[0], "heuristic_unique", size_matches

    return None, "ambiguous", size_matches


def write_report(report_path, unresolved_rows):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as handle:
        for row in unresolved_rows:
            handle.write(
                f"[{row['track_id']}] {row['artist']} - {row['name']} :: {row['reason']}\n"
            )
            for candidate in row["candidates"]:
                handle.write(f"  {candidate}\n")


def main():
    args = parse_args()

    source_xml = Path(args.source_xml).expanduser()
    pool_root = Path(args.pool_root).expanduser()
    output_xml = Path(args.output_xml).expanduser()
    report_path = (
        Path(args.report).expanduser()
        if args.report
        else output_xml.with_suffix(output_xml.suffix + ".unresolved.txt")
    )

    by_size, by_size_basename, pool_counts = index_pool(pool_root)

    tree = ET.parse(source_xml)
    root = tree.getroot()
    collection = root.find("COLLECTION")
    if collection is None:
        raise SystemExit("COLLECTION node not found in XML")

    stats = Counter()
    unresolved_rows = []

    for track in collection.findall("TRACK"):
        stats["tracks_scanned"] += 1
        match, reason, candidates = choose_match(track, by_size, by_size_basename)
        stats[reason] += 1

        track_id = track.get("TrackID", "?")
        artist = track.get("Artist", "").strip()
        name = track.get("Name", "").strip()

        if match is None:
            unresolved_rows.append(
                {
                    "track_id": track_id,
                    "artist": artist,
                    "name": name,
                    "reason": reason,
                    "candidates": [str(path) for path in candidates[:10]],
                }
            )
            verbose_print(
                args.verbose,
                f"leave unchanged [{track_id}] {artist} - {name} :: {reason}",
            )
            continue

        track.set("Location", encode_location(match))
        stats["tracks_rewritten"] += 1
        verbose_print(
            args.verbose,
            f"rewrite [{track_id}] {artist} - {name} -> {match}",
        )

    if not args.dry_run:
        output_xml.parent.mkdir(parents=True, exist_ok=True)
        tree.write(output_xml, encoding="UTF-8", xml_declaration=True)
        write_report(report_path, unresolved_rows)

    print("Summary")
    print(f"- Source XML: {source_xml}")
    print(f"- POOL_LIBRARY: {pool_root}")
    print(f"- Output XML: {output_xml}")
    print(f"- Pool audio files indexed: {pool_counts['audio_files']}")
    print(f"- Tracks scanned: {stats['tracks_scanned']}")
    print(f"- Tracks rewritten: {stats['tracks_rewritten']}")
    print(f"- Unique by size: {stats['size_unique']}")
    print(f"- Unique by size+basename: {stats['size_basename_unique']}")
    print(f"- Unique by heuristic: {stats['heuristic_unique']}")
    print(f"- Ambiguous: {stats['ambiguous']}")
    print(f"- No size match: {stats['no_size_match']}")
    print(f"- Missing size: {stats['missing_size']}")
    if args.dry_run:
        print("- Write mode: dry-run")
    else:
        print(f"- Unresolved report: {report_path}")


if __name__ == "__main__":
    raise SystemExit(main())
