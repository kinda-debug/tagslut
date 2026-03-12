from __future__ import annotations

import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from mutagen.id3 import ID3, TALB, TBPM, TIT2, TKEY, TPE1


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "tools" / "dj" / "build_rekordbox_xml_from_pool.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_rekordbox_xml_from_pool_under_test", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_dummy_mp3(path: Path, *, title: str, artist: str, album: str, bpm: str = "", key: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))
    if bpm:
        tags.add(TBPM(encoding=3, text=bpm))
    if key:
        tags.add(TKEY(encoding=3, text=key))
    tags.save(path)


def test_build_rekordbox_xml_includes_collection_and_playlist_nodes(tmp_path: Path) -> None:
    module = _load_module()
    pool_root = tmp_path / "pool"
    playlists_root = tmp_path / "playlists"

    song_a = pool_root / "Artist A" / "Album A" / "Artist A - Song A.mp3"
    song_b = pool_root / "Artist B" / "Album B" / "Artist B - Song B.mp3"
    _write_dummy_mp3(song_a, title="Song A", artist="Artist A", album="Album A", bpm="123", key="Am")
    _write_dummy_mp3(song_b, title="Song B", artist="Artist B", album="Album B")

    playlist_path = playlists_root / "Set One.m3u"
    playlist_path.parent.mkdir(parents=True, exist_ok=True)
    playlist_path.write_text(
        "#EXTM3U\n../pool/Artist A/Album A/Artist A - Song A.mp3\n../pool/Artist B/Album B/Artist B - Song B.mp3\n",
        encoding="utf-8",
    )

    output_path = tmp_path / "rekordbox.xml"
    summary = module.build_rekordbox_xml(
        pool_root=pool_root,
        playlists_root=playlists_root,
        output_path=output_path,
        folder_name="Tomorrow Special",
        backup_existing=False,
    )

    assert summary["tracks"] == 2
    assert summary["playlists"] == 1
    tree = ET.parse(output_path)
    root = tree.getroot()
    collection = root.find("COLLECTION")
    assert collection is not None
    tracks = collection.findall("TRACK")
    assert len(tracks) == 2
    assert tracks[0].attrib["Name"] == "Song A"
    assert tracks[0].attrib["Artist"] == "Artist A"
    assert tracks[0].attrib["AverageBpm"] == "123"
    assert tracks[0].attrib["Tonality"] == "Am"

    playlists_node = root.find("PLAYLISTS")
    assert playlists_node is not None
    root_node = playlists_node.find("NODE")
    assert root_node is not None
    folder_node = root_node.find("NODE")
    assert folder_node is not None
    assert folder_node.attrib["Name"] == "Tomorrow Special"
    leaf = folder_node.find("NODE")
    assert leaf is not None
    assert leaf.attrib["Name"] == "Set One"
    refs = leaf.findall("TRACK")
    assert [item.attrib["Key"] for item in refs] == ["1", "2"]
