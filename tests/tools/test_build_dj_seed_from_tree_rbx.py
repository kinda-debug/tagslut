from __future__ import annotations

import csv
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

from mutagen.id3 import ID3, TALB, TIT2, TPE1, TRCK, TSRC


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "tools" / "build_dj_seed_from_tree_rbx"


def _load_module():
    loader = importlib.machinery.SourceFileLoader("build_dj_seed_from_tree_rbx_under_test", str(MODULE_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_dummy_mp3(
    path: Path,
    *,
    artist: str = "",
    title: str = "",
    album: str = "",
    track_number: str = "",
    isrc: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    if title:
        tags.add(TIT2(encoding=3, text=title))
    if artist:
        tags.add(TPE1(encoding=3, text=artist))
    if album:
        tags.add(TALB(encoding=3, text=album))
    if track_number:
        tags.add(TRCK(encoding=3, text=track_number))
    if isrc:
        tags.add(TSRC(encoding=3, text=isrc))
    tags.save(path)


def _tree_payload(entries: list[dict[str, object]], *, trailing_semicolon: bool = False) -> str:
    payload = {
        "name": "Contents",
        "path": "/Volumes/RBX_USB/RBX_SSD/Contents",
        "size": 1,
        "type": "directory",
        "children": entries,
    }
    suffix = ";" if trailing_semicolon else ""
    return "export default " + json.dumps(payload, ensure_ascii=False, indent=2) + suffix + "\n"


def _file_node(path: Path, *, size: int | None = None) -> dict[str, object]:
    return {
        "name": path.name,
        "path": str(path),
        "size": path.stat().st_size if path.exists() else (size if size is not None else 1234),
        "type": "file",
    }


def _dir_node(name: str, path: Path, children: list[dict[str, object]]) -> dict[str, object]:
    return {
        "name": name,
        "path": str(path),
        "size": 1,
        "type": "directory",
        "children": children,
    }


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def test_build_dj_seed_from_tree_rbx_outputs_expected_files_and_matches(tmp_path: Path, monkeypatch) -> None:
    module = _load_module()

    inspected_seed = tmp_path / "seed_existing" / "Artist Exact" / "Album Exact" / "Artist Exact - Song Exact.mp3"
    _write_dummy_mp3(
        inspected_seed,
        artist="Artist Exact",
        title="Song Exact",
        album="Album Exact",
        track_number="01",
        isrc="USABC1234567",
    )

    path_only_seed = tmp_path / "seed_missing" / "Crate A" / "Artist Context - Song Context.mp3"
    missing_seed = tmp_path / "seed_missing" / "Missing Artist - Missing Song.mp3"
    ambiguous_seed = tmp_path / "seed_missing" / "Artist Ambiguous - Same Song.mp3"

    pool_root = tmp_path / "pool"
    exact_match = pool_root / "clean" / "Artist Exact" / "Album Exact" / "Artist Exact - Song Exact.mp3"
    _write_dummy_mp3(
        exact_match,
        artist="Artist Exact",
        title="Song Exact",
        album="Album Exact",
        track_number="01",
        isrc="USABC1234567",
    )

    context_match = pool_root / "clean" / "Crate A" / "Album From Crate" / "Artist Context - Song Context.mp3"
    _write_dummy_mp3(
        context_match,
        artist="Artist Context",
        title="Song Context",
        album="Album From Crate",
        track_number="02",
    )

    context_other = pool_root / "clean" / "Elsewhere" / "Other Album" / "Artist Context - Song Context.mp3"
    _write_dummy_mp3(
        context_other,
        artist="Artist Context",
        title="Song Context",
        album="Other Album",
        track_number="02",
    )

    ambiguous_one = pool_root / "clean" / "Set1" / "Artist Ambiguous - Same Song.mp3"
    ambiguous_two = pool_root / "clean" / "Set2" / "Artist Ambiguous - Same Song.mp3"
    _write_dummy_mp3(ambiguous_one, artist="Artist Ambiguous", title="Same Song")
    _write_dummy_mp3(ambiguous_two, artist="Artist Ambiguous", title="Same Song")

    ignored_path = tmp_path / "seed_existing" / "Artist Exact" / "._junk.mp3"

    tree_js = tmp_path / "tree_rbx.js"
    tree_js.write_text(
        _tree_payload(
            [
                _dir_node(
                    "Artist Exact",
                    inspected_seed.parent.parent,
                    [
                        _dir_node(
                            "Album Exact",
                            inspected_seed.parent,
                            [
                                _file_node(inspected_seed),
                                _file_node(ignored_path, size=4096),
                            ],
                        )
                    ],
                ),
                _dir_node(
                    "Crate A",
                    path_only_seed.parent,
                    [_file_node(path_only_seed)],
                ),
                _file_node(missing_seed),
                _file_node(ambiguous_seed),
            ],
            trailing_semicolon=True,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "probe_duration_ffprobe", lambda _path: None)

    output_dir = tmp_path / "out"
    result = module.run(
        module.parse_args(
            [
                "--tree-js",
                str(tree_js),
                "--pool-root",
                str(pool_root),
                "--output-dir",
                str(output_dir),
            ]
        )
    )

    m3u_path = Path(result["m3u_path"])
    missing_path = Path(result["missing_path"])
    ambiguous_path = Path(result["ambiguous_path"])
    manifest_path = Path(result["manifest_path"])

    assert m3u_path.exists()
    assert missing_path.exists()
    assert ambiguous_path.exists()
    assert manifest_path.exists()

    m3u_lines = m3u_path.read_text(encoding="utf-8").splitlines()
    assert m3u_lines[0] == "#EXTM3U"
    assert m3u_lines[1:] == [str(exact_match.resolve()), str(context_match.resolve())]

    missing_header, missing_rows = _read_csv(missing_path)
    assert missing_header == [
        "seed_path",
        "seed_name",
        "seed_context_path",
        "seed_source_mode",
        "seed_artist",
        "seed_title",
        "seed_album",
        "seed_isrc",
        "best_tier_attempted",
        "note",
    ]
    assert len(missing_rows) == 1
    assert missing_rows[0]["seed_name"] == missing_seed.name
    assert missing_rows[0]["best_tier_attempted"] == "artist_title_exact"

    ambiguous_header, ambiguous_rows = _read_csv(ambiguous_path)
    assert ambiguous_header == [
        "seed_path",
        "seed_name",
        "seed_context_path",
        "seed_source_mode",
        "candidate_count",
        "best_tier_reached",
        "candidate_paths_json",
        "note",
    ]
    assert len(ambiguous_rows) == 1
    assert ambiguous_rows[0]["seed_name"] == ambiguous_seed.name
    ambiguous_paths = json.loads(ambiguous_rows[0]["candidate_paths_json"])
    assert ambiguous_paths == [str(ambiguous_one.resolve()), str(ambiguous_two.resolve())]

    manifest_rows = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["seed_name"] for row in manifest_rows] == [
        inspected_seed.name,
        "._junk.mp3",
        path_only_seed.name,
        missing_seed.name,
        ambiguous_seed.name,
    ]

    matched_inspected = next(row for row in manifest_rows if row["seed_name"] == inspected_seed.name)
    assert matched_inspected["outcome"] == "matched"
    assert matched_inspected["best_tier_reached"] == "isrc_exact"
    assert matched_inspected["seed_source_mode"] == "seed_file_inspected"
    assert matched_inspected["seed_artist"] == "Artist Exact"
    assert matched_inspected["chosen_candidate_path"] == str(exact_match.resolve())

    matched_path_only = next(row for row in manifest_rows if row["seed_name"] == path_only_seed.name)
    assert matched_path_only["outcome"] == "matched"
    assert matched_path_only["best_tier_reached"] == "artist_title_context"
    assert matched_path_only["seed_source_mode"] == "seed_path_only"
    assert matched_path_only["seed_context_path"] == "Contents/Crate A"
    assert matched_path_only["chosen_candidate_path"] == str(context_match.resolve())

    ignored_row = next(row for row in manifest_rows if row["seed_name"] == "._junk.mp3")
    assert ignored_row["outcome"] == "ignored"
    assert ignored_row["ignore_reason"] == "appledouble"

    assert sorted(path.name for path in output_dir.iterdir()) == [
        "dj_seed_ambiguous.csv",
        "dj_seed_from_tree_rbx.m3u",
        "dj_seed_match_manifest.jsonl",
        "dj_seed_missing.csv",
    ]


def test_load_seed_rows_respects_limit_after_ignore_filtering(tmp_path: Path) -> None:
    module = _load_module()
    first = tmp_path / "a" / "Artist One - Song One.mp3"
    second = tmp_path / "a" / "Artist Two - Song Two.mp3"
    ignored = tmp_path / "a" / "._ignore.mp3"
    tree_js = tmp_path / "tree_rbx.js"
    tree_js.write_text(
        _tree_payload(
            [
                _file_node(first),
                _file_node(ignored, size=4096),
                _file_node(second),
            ]
        ),
        encoding="utf-8",
    )

    seed_rows, ignored_rows = module.load_seed_rows(tree_js, limit=1)

    assert [row.seed_name for row in seed_rows] == [first.name]
    assert len(ignored_rows) == 1
    assert ignored_rows[0]["seed_name"] == ignored.name
