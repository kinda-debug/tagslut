#!/usr/bin/env python3

import argparse
import os
import copy
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote, unquote

from mutagen import File as MutagenFile


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aif", ".aiff", ".flac"}
INVALID_XML_CODEPOINTS = {
    codepoint for codepoint in range(32) if codepoint not in (9, 10, 13)
}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Build a healthy Rekordbox XML collection from the current pool, "
            "preserving source XML metadata when a unique match is available."
        )
    )
    parser.add_argument("source_xml", help="Existing Rekordbox XML used as metadata source")
    parser.add_argument("pool_root", help="Healthy pool root")
    parser.add_argument("output_xml", help="Output Rekordbox XML path")
    return parser.parse_args()


def is_audio_file(path):
    return path.suffix.lower() in AUDIO_EXTENSIONS and not path.name.startswith(".")


def iter_audio_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        current_root = Path(dirpath)
        for filename in filenames:
            path = current_root / filename
            if is_audio_file(path):
                yield path


def encode_location(path):
    return "file://localhost" + quote(path.as_posix(), safe="/")


def decode_location(location):
    raw = location.replace("file://localhost", "").replace("file://", "")
    return Path(unquote(raw))


def choose_tag_value(tags, keys):
    if not tags:
        return ""
    for key in keys:
        try:
            value = tags.get(key)
        except Exception:
            continue
        if value is None:
            continue
        if isinstance(value, list):
            if not value:
                continue
            value = value[0]
        text = str(value).strip()
        if text:
            return sanitize_xml_text(text)
    return ""


def sanitize_xml_text(value):
    return "".join(ch for ch in value if ord(ch) not in INVALID_XML_CODEPOINTS)


def extract_fallback_metadata(path):
    metadata = {
        "Name": sanitize_xml_text(path.stem),
        "Artist": sanitize_xml_text(path.parent.parent.name if len(path.parts) >= 2 else ""),
        "Album": sanitize_xml_text(path.parent.name),
        "Genre": "",
        "Kind": f"{path.suffix.lower().lstrip('.').upper()} File",
        "Size": str(path.stat().st_size),
        "TotalTime": "",
        "Year": "",
        "BitRate": "",
        "SampleRate": "",
        "Comments": "",
        "Location": encode_location(path),
        "DateAdded": str(date.today()),
    }

    try:
        audio = MutagenFile(path)
    except Exception:
        return metadata

    if audio is not None and getattr(audio, "info", None) is not None:
        length = getattr(audio.info, "length", None)
        bitrate = getattr(audio.info, "bitrate", None)
        sample_rate = getattr(audio.info, "sample_rate", None)
        if length is not None:
            metadata["TotalTime"] = str(int(round(length)))
        if bitrate is not None:
            metadata["BitRate"] = str(int(round(bitrate / 1000)))
        if sample_rate is not None:
            metadata["SampleRate"] = str(sample_rate)

    tags = getattr(audio, "tags", None)
    metadata["Name"] = choose_tag_value(tags, ["TIT2", "\xa9nam", "TITLE", "title"]) or metadata["Name"]
    metadata["Artist"] = choose_tag_value(tags, ["TPE1", "\xa9ART", "ARTIST", "artist"]) or metadata["Artist"]
    metadata["Album"] = choose_tag_value(tags, ["TALB", "\xa9alb", "ALBUM", "album"]) or metadata["Album"]
    metadata["Genre"] = choose_tag_value(tags, ["TCON", "\xa9gen", "GENRE", "genre"]) or metadata["Genre"]
    metadata["Year"] = choose_tag_value(tags, ["TDRC", "TYER", "\xa9day", "DATE", "date", "YEAR", "year"])
    metadata["Comments"] = choose_tag_value(tags, ["COMM::eng", "COMM", "\xa9cmt", "COMMENT", "comment"])
    return metadata


def normalize_source_track(track, path):
    keep_keys = [
        "TrackID",
        "Name",
        "Artist",
        "Composer",
        "Album",
        "Grouping",
        "Genre",
        "Kind",
        "Size",
        "TotalTime",
        "DiscNumber",
        "TrackNumber",
        "Year",
        "AverageBpm",
        "DateAdded",
        "BitRate",
        "SampleRate",
        "Comments",
        "PlayCount",
        "Rating",
        "Remixer",
        "Tonality",
        "Label",
        "Mix",
    ]
    data = {key: sanitize_xml_text(track.get(key, "")) for key in keep_keys}
    data["Size"] = str(path.stat().st_size)
    data["Location"] = encode_location(path)
    return data


def index_source_tracks(collection):
    by_path = {}
    by_size_name = defaultdict(list)
    by_size = defaultdict(list)
    max_track_id = 0

    for track in collection.findall("TRACK"):
        try:
            track_id = int(track.get("TrackID", "0"))
        except ValueError:
            track_id = 0
        max_track_id = max(max_track_id, track_id)

        location = track.get("Location", "")
        if location.startswith("file://"):
            by_path[str(decode_location(location))] = track

        size = track.get("Size", "")
        name = decode_location(location).name if location.startswith("file://") else ""
        if size:
            by_size_name[(size, name)].append(track)
            by_size[size].append(track)

    return by_path, by_size_name, by_size, max_track_id


def choose_source_track(path, by_path, by_size_name, by_size):
    exact = by_path.get(str(path))
    if exact is not None:
        return exact, "exact_path"

    size = str(path.stat().st_size)
    exact_name_matches = by_size_name.get((size, path.name), [])
    if len(exact_name_matches) == 1:
        return exact_name_matches[0], "size_name"

    size_matches = by_size.get(size, [])
    if len(size_matches) == 1:
        return size_matches[0], "size_only"

    return None, "fallback"


def build_track_element(track_data):
    track = ET.Element("TRACK")
    for key, value in track_data.items():
        if value != "":
            track.set(key, sanitize_xml_text(value))
    return track


def filter_playlist_node(node, valid_track_ids):
    node_copy = ET.Element(node.tag, node.attrib)

    if node.get("Type") == "1":
        kept = 0
        for track_ref in node.findall("TRACK"):
            key = track_ref.get("Key", "")
            if key in valid_track_ids:
                node_copy.append(copy.deepcopy(track_ref))
                kept += 1
        node_copy.set("Entries", str(kept))
        return node_copy if kept > 0 else None

    kept_children = 0
    for child in node.findall("NODE"):
        filtered = filter_playlist_node(child, valid_track_ids)
        if filtered is not None:
            node_copy.append(filtered)
            kept_children += 1
    node_copy.set("Count", str(kept_children))
    return node_copy if node.get("Name") == "ROOT" or kept_children > 0 else None


def main():
    args = parse_args()

    source_xml = Path(args.source_xml).expanduser()
    pool_root = Path(args.pool_root).expanduser()
    output_xml = Path(args.output_xml).expanduser()

    source_tree = ET.parse(source_xml)
    source_root = source_tree.getroot()
    source_collection = source_root.find("COLLECTION")
    if source_collection is None:
        raise SystemExit("COLLECTION node not found in source XML")

    by_path, by_size_name, by_size, max_track_id = index_source_tracks(source_collection)

    root = ET.Element("DJ_PLAYLISTS", source_root.attrib)
    product = source_root.find("PRODUCT")
    if product is not None:
        root.append(ET.Element("PRODUCT", product.attrib))
    collection = ET.SubElement(root, "COLLECTION")
    playlists = ET.SubElement(root, "PLAYLISTS")

    stats = Counter()
    next_track_id = max_track_id + 1
    valid_track_ids = set()

    for path in sorted(iter_audio_files(pool_root)):
        stats["pool_files"] += 1
        source_track, reason = choose_source_track(path, by_path, by_size_name, by_size)
        stats[reason] += 1

        if source_track is not None:
            data = normalize_source_track(source_track, path)
        else:
            data = extract_fallback_metadata(path)
            data.update(
                {
                    "TrackID": str(next_track_id),
                    "Composer": "",
                    "Grouping": "",
                    "DiscNumber": "0",
                    "TrackNumber": "0",
                    "AverageBpm": "",
                    "PlayCount": "0",
                    "Rating": "0",
                    "Remixer": "",
                    "Tonality": "",
                    "Label": "",
                    "Mix": "",
                }
            )
            next_track_id += 1

        valid_track_ids.add(data["TrackID"])
        collection.append(build_track_element(data))

    collection.set("Entries", str(stats["pool_files"]))

    source_playlists = source_root.find("PLAYLISTS")
    if source_playlists is not None:
        root_node = source_playlists.find("NODE")
        if root_node is not None:
            filtered_root = filter_playlist_node(root_node, valid_track_ids)
            if filtered_root is not None:
                playlists.append(filtered_root)

    tree = ET.ElementTree(root)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="  ")
    output_xml.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_xml, encoding="UTF-8", xml_declaration=True)

    print("Summary")
    print(f"- Source XML: {source_xml}")
    print(f"- Pool root: {pool_root}")
    print(f"- Output XML: {output_xml}")
    print(f"- Pool files written: {stats['pool_files']}")
    print(f"- Metadata from exact path: {stats['exact_path']}")
    print(f"- Metadata from size+name: {stats['size_name']}")
    print(f"- Metadata from size-only: {stats['size_only']}")
    print(f"- Metadata from fallback tags/path: {stats['fallback']}")


if __name__ == "__main__":
    raise SystemExit(main())
