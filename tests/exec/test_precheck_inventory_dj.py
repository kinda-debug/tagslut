from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TALB, TIT2, TPE1

from tagslut.exec import precheck_inventory_dj
from tagslut.storage.schema import init_db


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.commit()
    conn.close()


def _write_decisions_csv(path: Path, *, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "playlist_index",
                "title",
                "artist",
                "album",
                "isrc",
                "db_path",
                "decision",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_dummy_mp3(path: Path, *, title: str, artist: str, album: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))
    tags.save(path)


def test_link_precheck_inventory_to_dj_reuses_existing_mp3_by_artist_token_match(tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    _init_db(db_path)
    conn = sqlite3.connect(str(db_path))
    source_path = tmp_path / "library" / "Meet Me.flac"
    conn.execute(
        """
        INSERT INTO files (path, canonical_title, canonical_artist, canonical_album, canonical_isrc)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(source_path), "Meet Me", "Mathame, Jonos, Son Of Son", "Meet Me", "ISRC-1"),
    )
    conn.commit()
    conn.close()

    decisions_csv = tmp_path / "precheck_decisions.csv"
    _write_decisions_csv(
        decisions_csv,
        rows=[
            {
                "playlist_index": "1",
                "title": "Meet Me",
                "artist": "Mathame, Jonos, Son Of Son",
                "album": "Meet Me",
                "isrc": "ISRC-1",
                "db_path": str(source_path),
                "decision": "skip",
            }
        ],
    )

    dj_root = tmp_path / "DJ_LIBRARY"
    matched_mp3 = dj_root / "_UNRESOLVED" / "lexicon_manual_absorb" / "missing_core_tags" / "Meet Me.mp3"
    _write_dummy_mp3(
        matched_mp3,
        title="Meet Me",
        artist="Jonos, Mathame, Son Of Son",
        album="Meet Me",
    )

    summary = precheck_inventory_dj.link_precheck_inventory_to_dj(
        db_path=db_path,
        decisions_csv=decisions_csv,
        dj_root=dj_root,
        playlist_dir=dj_root,
        playlist_base_name="dj-meet-me",
        artifact_dir=tmp_path / "artifacts",
    )

    assert summary["resolved_rows"] == 1
    assert summary["existing_mp3_rows"] == 1
    assert summary["transcoded_rows"] == 0

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT dj_pool_path FROM files WHERE path = ?", (str(source_path),)).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == str(matched_mp3.resolve())

    playlist_path = Path(str(summary["playlist_path"]))
    text = playlist_path.read_text(encoding="utf-8")
    assert "Jonos, Mathame, Son Of Son - Meet Me" in text
    assert str(matched_mp3.resolve()) in text


class _Snapshot:
    def __init__(self) -> None:
        self.artist = "Artist"
        self.title = "Track"
        self.album = "Album"
        self.bpm = None
        self.musical_key = None
        self.energy_1_10 = None
        self.identity_id = 123

    def as_dict(self) -> dict[str, object]:
        return {
            "artist": self.artist,
            "title": self.title,
            "album": self.album,
            "identity_id": self.identity_id,
        }


def test_link_precheck_inventory_to_dj_transcodes_live_source_when_needed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "music.db"
    _init_db(db_path)
    source_path = tmp_path / "library" / "Track.flac"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"fake flac")

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO files (path, canonical_title, canonical_artist, canonical_album, canonical_isrc)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(source_path), "Track", "Artist", "Album", "ISRC-2"),
    )
    conn.commit()
    conn.close()

    decisions_csv = tmp_path / "precheck_decisions.csv"
    _write_decisions_csv(
        decisions_csv,
        rows=[
            {
                "playlist_index": "1",
                "title": "Track",
                "artist": "Artist",
                "album": "Album",
                "isrc": "ISRC-2",
                "db_path": str(source_path),
                "decision": "skip",
            }
        ],
    )

    def _fake_resolve_snapshot(*_args, **_kwargs):
        return _Snapshot()

    def _fake_transcode(source: Path, dest_dir: Path, snapshot: _Snapshot, **_kwargs) -> Path:
        dest_path = dest_dir / "Artist - Track.mp3"
        _write_dummy_mp3(dest_path, title=snapshot.title, artist=snapshot.artist, album=snapshot.album)
        return dest_path

    monkeypatch.setattr(precheck_inventory_dj, "resolve_dj_tag_snapshot_for_path", _fake_resolve_snapshot)
    monkeypatch.setattr(precheck_inventory_dj, "transcode_to_mp3_from_snapshot", _fake_transcode)

    dj_root = tmp_path / "DJ_LIBRARY"
    summary = precheck_inventory_dj.link_precheck_inventory_to_dj(
        db_path=db_path,
        decisions_csv=decisions_csv,
        dj_root=dj_root,
        playlist_dir=dj_root,
        playlist_base_name="dj-track",
        artifact_dir=tmp_path / "artifacts",
    )

    assert summary["resolved_rows"] == 1
    assert summary["existing_mp3_rows"] == 0
    assert summary["transcoded_rows"] == 1

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT dj_pool_path FROM files WHERE path = ?", (str(source_path),)).fetchone()
    prov = conn.execute(
        "SELECT event_type, source_path, dest_path FROM provenance_event ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] is not None
    assert row[0].endswith("Artist - Track.mp3")
    assert prov is not None
    assert prov[0] == "dj_export"
    assert prov[1] == str(source_path.resolve())
    assert prov[2].endswith("Artist - Track.mp3")

    playlist_path = Path(str(summary["playlist_path"]))
    tags = EasyID3(str(Path(row[0])))
    assert (tags.get("title") or [""])[0] == "Track"
    assert str(Path(row[0]).resolve()) in playlist_path.read_text(encoding="utf-8")
