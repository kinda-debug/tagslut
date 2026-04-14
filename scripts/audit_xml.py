#!/usr/bin/env python3

import argparse
import filecmp
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote, unquote


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Copy Rekordbox track files into one root and write a new XML with updated "
            "file://localhost locations. Missing source files are left unchanged."
        )
    )
    parser.add_argument("source_xml", help="Path to the exported Rekordbox XML")
    parser.add_argument("dest_root", help="New central root for copied audio files")
    parser.add_argument("output_xml", help="Path for the rewritten Rekordbox XML")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned changes without copying files or writing XML",
    )
    parser.add_argument(
        "--flatten",
        action="store_true",
        help=(
            "Put files directly under dest_root. Default is a clean library layout using "
            "Artist/Album/Filename."
        ),
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        help="Only relocate these file extensions, e.g. --extensions .mp3 .m4a",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-track decisions and more detailed summary output",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume from output_xml if it already exists. Tracks already rewritten into "
            "dest_root with a matching file are skipped."
        ),
    )
    parser.add_argument(
        "--keep-playlist",
        action="append",
        default=[],
        help=(
            "Keep only leaf playlists whose name contains this value. Repeat to keep more "
            "than one playlist."
        ),
    )
    parser.add_argument(
        "--prune-unreferenced-tracks",
        action="store_true",
        help="Remove tracks from COLLECTION that are not referenced by the kept playlists",
    )
    parser.add_argument(
        "--xdj-export",
        action="store_true",
        help=(
            "Apply XDJ export defaults: keep only valid playlist references and prune the "
            "collection to tracks used by the kept playlists."
        ),
    )
    return parser.parse_args()


def decode_location(location):
    if not location.startswith("file://"):
        return None

    if location.startswith("file://localhost"):
        raw_path = location[len("file://localhost") :]
    else:
        raw_path = location[len("file://") :]

    return Path(unquote(raw_path))


def encode_location(path):
    return "file://localhost" + quote(path.as_posix(), safe="/")


def build_target_path(source_path, dest_root, flatten):
    if flatten:
        return dest_root / source_path.name

    return dest_root / build_library_relative_path(source_path)


def sanitize_path_part(value, fallback):
    cleaned = (value or "").strip().strip(".")
    invalid = '<>:"/\\|?*'
    for char in invalid:
        cleaned = cleaned.replace(char, "_")
    cleaned = " ".join(cleaned.split())
    return cleaned or fallback


def split_source_parts(source_path):
    parent_parts = list(source_path.parent.parts)
    if not parent_parts:
        return None, None

    album = parent_parts[-1] if parent_parts else None
    artist = parent_parts[-2] if len(parent_parts) >= 2 else None
    return artist, album


def build_library_relative_path(source_path):
    artist, album = split_source_parts(source_path)
    artist_dir = sanitize_path_part(artist, "Unknown Artist")
    album_dir = sanitize_path_part(album, "Unknown Album")
    filename = sanitize_path_part(source_path.name, "unknown")
    return Path(artist_dir) / album_dir / filename


def files_match(left, right):
    if not right.exists():
        return False

    try:
        if left.samefile(right):
            return True
    except OSError:
        pass

    try:
        if left.stat().st_size != right.stat().st_size:
            return False
    except OSError:
        return False

    return filecmp.cmp(left, right, shallow=False)


def unique_target_path(target_path, source_path, track_id):
    if not target_path.exists() or files_match(source_path, target_path):
        return target_path, False

    stem = target_path.stem
    suffix = target_path.suffix
    candidate = target_path.with_name(f"{stem}__{track_id}{suffix}")
    counter = 1

    while candidate.exists() and not files_match(source_path, candidate):
        candidate = target_path.with_name(f"{stem}__{track_id}_{counter}{suffix}")
        counter += 1

    return candidate, True


def normalize_extensions(raw_extensions):
    if not raw_extensions:
        return None

    normalized = set()
    for ext in raw_extensions:
        ext = ext.lower()
        if not ext.startswith("."):
            ext = "." + ext
        normalized.add(ext)
    return normalized


def track_label(track):
    track_id = track.get("TrackID", "?")
    artist = track.get("Artist", "").strip() or "<unknown artist>"
    name = track.get("Name", "").strip() or "<unknown title>"
    return f"[{track_id}] {artist} - {name}"


def verbose_print(enabled, message):
    if enabled:
        print(message)


def is_under_root(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def pct(part, whole):
    if not whole:
        return "0.0%"
    return f"{(part / whole) * 100:.1f}%"


def print_summary(
    source_xml,
    resume_source,
    dest_root,
    output_xml,
    args,
    scanned,
    rewritten,
    copied,
    reused_existing,
    resumed_existing,
    collisions,
    missing,
    skipped_non_file,
    skipped_extension,
    kept_playlist_count,
    removed_playlist_count,
    removed_playlist_refs,
    pruned_track_count,
):
    unchanged = scanned - rewritten

    print("\nSummary")
    print(f"- Source XML: {source_xml}")
    print(f"- Active input XML: {resume_source}")
    print(f"- Destination root: {dest_root}")
    print(f"- Output XML: {output_xml}")
    print(f"- Mode: {'dry-run' if args.dry_run else 'write'}")
    print(f"- Resume: {'enabled' if args.resume else 'disabled'}")
    print(f"- Path strategy: {'flatten' if args.flatten else 'artist/album/filename'}")
    print(
        "- Extension filter: "
        + (", ".join(sorted(normalize_extensions(args.extensions))) if args.extensions else "none")
    )
    print(f"- Tracks scanned: {scanned}")
    print(f"- Tracks rewritten: {rewritten} ({pct(rewritten, scanned)})")
    print(f"- Tracks unchanged: {unchanged} ({pct(unchanged, scanned)})")
    print(f"- Files copied this run: {copied}")
    print(f"- Existing matching targets reused: {reused_existing}")
    print(f"- Resume-skipped centralized tracks: {resumed_existing}")
    print(f"- Collision-safe renames: {collisions}")
    print(f"- Missing source files: {len(missing)}")
    print(f"- Non-file locations skipped: {skipped_non_file}")
    print(f"- Extension-filtered tracks skipped: {skipped_extension}")
    print(f"- Playlists kept: {kept_playlist_count}")
    print(f"- Playlists removed: {removed_playlist_count}")
    print(f"- Dead playlist references removed: {removed_playlist_refs}")
    print(f"- Tracks pruned from collection: {pruned_track_count}")
    if args.dry_run:
        print("- Output write: skipped (dry run)")
    else:
        print("- Output write: completed")


def normalize_playlist_filters(values):
    return [value.strip().casefold() for value in values if value and value.strip()]


def playlist_matches(name, filters):
    if not filters:
        return True
    normalized_name = (name or "").casefold()
    return any(value in normalized_name for value in filters)


def prune_playlists(playlists_node, valid_track_ids, keep_filters):
    if playlists_node is None:
        return 0, 0, 0

    kept = 0
    removed = 0
    removed_refs = 0

    def walk(node):
        nonlocal kept, removed, removed_refs
        for child in list(node.findall("NODE")):
            node_type = child.get("Type")
            if node_type == "1":
                if not playlist_matches(child.get("Name", ""), keep_filters):
                    node.remove(child)
                    removed += 1
                    continue

                for track_ref in list(child.findall("TRACK")):
                    key = track_ref.get("Key", "")
                    if key not in valid_track_ids:
                        child.remove(track_ref)
                        removed_refs += 1

                child.set("Entries", str(len(child.findall("TRACK"))))
                kept += 1
                continue

            walk(child)
            child.set("Count", str(len(child.findall("NODE"))))
            if len(child.findall("NODE")) == 0:
                node.remove(child)

    walk(playlists_node)
    return kept, removed, removed_refs


def referenced_track_ids(playlists_node):
    if playlists_node is None:
        return set()

    referenced = set()
    for playlist in playlists_node.findall(".//NODE[@Type='1']"):
        for track_ref in playlist.findall("TRACK"):
            key = track_ref.get("Key")
            if key:
                referenced.add(key)
    return referenced


def prune_collection(collection, keep_track_ids):
    pruned = 0
    for track in list(collection.findall("TRACK")):
        if track.get("TrackID", "") not in keep_track_ids:
            collection.remove(track)
            pruned += 1
    collection.set("Entries", str(len(collection.findall("TRACK"))))
    return pruned


def main():
    args = parse_args()

    source_xml = Path(args.source_xml).expanduser()
    dest_root = Path(args.dest_root).expanduser()
    output_xml = Path(args.output_xml).expanduser()
    extension_filter = normalize_extensions(args.extensions)

    resume_source = source_xml
    if args.resume and output_xml.exists():
        resume_source = output_xml

    tree = ET.parse(resume_source)
    root = tree.getroot()
    collection = root.find("COLLECTION")
    playlists = root.find("PLAYLISTS")

    if collection is None:
        print("Error: COLLECTION node not found in XML.", file=sys.stderr)
        return 1

    scanned = 0
    rewritten = 0
    copied = 0
    reused_existing = 0
    resumed_existing = 0
    collisions = 0
    skipped_non_file = 0
    skipped_extension = 0
    missing = []
    keep_filters = normalize_playlist_filters(args.keep_playlist)
    valid_track_ids = set()

    source_to_target = {}

    verbose_print(
        args.verbose,
        f"input XML: {resume_source} ({'resume state' if resume_source == output_xml else 'source export'})",
    )

    for track in collection.findall("TRACK"):
        scanned += 1

        location = track.get("Location", "")
        source_path = decode_location(location)
        if source_path is None:
            skipped_non_file += 1
            verbose_print(
                args.verbose,
                f"skip non-file location: {track_label(track)} :: {location}",
            )
            continue

        if extension_filter and source_path.suffix.lower() not in extension_filter:
            skipped_extension += 1
            verbose_print(
                args.verbose,
                f"skip extension: {track_label(track)} :: {source_path.suffix or '<none>'}",
            )
            continue

        if not source_path.exists():
            missing.append(
                (
                    track.get("TrackID", ""),
                    track.get("Artist", ""),
                    track.get("Name", ""),
                    str(source_path),
                )
            )
            verbose_print(
                args.verbose,
                f"missing source: {track_label(track)} :: {source_path}",
            )
            continue

        if args.resume and is_under_root(source_path, dest_root) and source_path.exists():
            rewritten += 1
            resumed_existing += 1
            source_to_target[source_path] = source_path
            verbose_print(
                args.verbose,
                f"resume already centralized: {track_label(track)} :: {source_path}",
            )
            continue

        target_path = source_to_target.get(source_path)
        if target_path is None:
            base_target = build_target_path(source_path, dest_root, args.flatten)
            target_path, had_collision = unique_target_path(
                base_target, source_path, track.get("TrackID", "track")
            )
            source_to_target[source_path] = target_path
            if had_collision:
                collisions += 1
                verbose_print(
                    args.verbose,
                    f"collision rename: {track_label(track)} :: {target_path}",
                )
            else:
                verbose_print(
                    args.verbose,
                    f"map source: {track_label(track)} :: {source_path} -> {target_path}",
                )
        else:
            verbose_print(
                args.verbose,
                f"reuse mapping: {track_label(track)} :: {source_path} -> {target_path}",
            )

        if not args.dry_run:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                if files_match(source_path, target_path):
                    reused_existing += 1
                    verbose_print(
                        args.verbose,
                        f"reuse existing file: {track_label(track)} :: {target_path}",
                    )
                else:
                    print(
                        f"Error: target exists and does not match source: {target_path}",
                        file=sys.stderr,
                    )
                    return 1
            else:
                shutil.copy2(source_path, target_path)
                copied += 1
                verbose_print(
                    args.verbose,
                    f"copied file: {track_label(track)} :: {target_path}",
                )
        else:
            verbose_print(
                args.verbose,
                f"dry run rewrite: {track_label(track)} :: {target_path}",
            )

        track.set("Location", encode_location(target_path))
        rewritten += 1
        track_id = track.get("TrackID", "")
        if track_id:
            valid_track_ids.add(track_id)

    kept_playlist_count = 0
    removed_playlist_count = 0
    removed_playlist_refs = 0
    pruned_track_count = 0

    if args.xdj_export:
        args.prune_unreferenced_tracks = True

    if playlists is not None:
        kept_playlist_count, removed_playlist_count, removed_playlist_refs = prune_playlists(
            playlists,
            valid_track_ids,
            keep_filters,
        )

    if args.prune_unreferenced_tracks:
        referenced_ids = referenced_track_ids(playlists)
        keep_track_ids = valid_track_ids & referenced_ids
        pruned_track_count = prune_collection(collection, keep_track_ids)

    if not args.dry_run:
        output_xml.parent.mkdir(parents=True, exist_ok=True)
        tree.write(output_xml, encoding="UTF-8", xml_declaration=True)

    if missing:
        limit = len(missing) if args.verbose else 20
        print(f"\nMissing source files ({min(limit, len(missing))} shown of {len(missing)}):")
        for track_id, artist, name, path in missing[:limit]:
            print(f"- [{track_id}] {artist} - {name} :: {path}")

    print_summary(
        source_xml,
        resume_source,
        dest_root,
        output_xml,
        args,
        scanned,
        rewritten,
        copied,
        reused_existing,
        resumed_existing,
        collisions,
        missing,
        skipped_non_file,
        skipped_extension,
        kept_playlist_count,
        removed_playlist_count,
        removed_playlist_refs,
        pruned_track_count,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
