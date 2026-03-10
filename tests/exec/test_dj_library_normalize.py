from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from tagslut.exec.dj_library_normalize import (
    AudioMetadata,
    DjPoolLookupRow,
    apply_dj_pool_relink,
    apply_playlist_rewrite_manifest,
    build_canonical_mp3_destination,
    plan_dj_library_normalize,
)
from tagslut.exec.dj_tag_snapshot import DjTagSnapshot
from tagslut.storage.schema import init_db
from tagslut.storage.v3 import create_schema_v3


def _meta(path: Path, **fields: str) -> AudioMetadata:
    tags = {key: [value] for key, value in fields.items() if value}
    return AudioMetadata(path=path.resolve(), tags=tags, duration_s=float(fields.pop("duration_s", 0.0) or 0.0) or None)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_plan_dj_library_normalize_buckets_files_and_writes_manifests(tmp_path, monkeypatch) -> None:
    from tagslut.exec import dj_library_normalize as module

    root = (tmp_path / "DJ_LIBRARY").resolve()
    master_root = (tmp_path / "MASTER_LIBRARY").resolve()
    out_dir = (tmp_path / "artifacts").resolve()
    unresolved_root = (root / "_UNRESOLVED").resolve()
    root.mkdir()
    master_root.mkdir()

    canonical_tags = {
        "title": ["Song"],
        "artist": ["Artist"],
        "album": ["Album"],
        "albumartist": ["Artist"],
        "date": ["2024"],
        "tracknumber": ["01"],
    }
    canonical_path = build_canonical_mp3_destination(canonical_tags, root)
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_bytes(b"mp3")

    rename_path = root / "2 Unlimited" / "(1994) Let the Beat Control Your Body" / "Unlimited – (1994) Let the Beat Control Your Body – 01 Let the Beat Control Your Body.mp3"
    rename_path.parent.mkdir(parents=True, exist_ok=True)
    rename_path.write_bytes(b"mp3")

    various_path = root / "Collab Dump" / "(2023) Label Sampler" / "Track Artist – (2023) Label Sampler – 01 Club Mix.mp3"
    various_path.parent.mkdir(parents=True, exist_ok=True)
    various_path.write_bytes(b"mp3")

    flac_ext_path = root / "Kölsch" / "(2025) KINEMA" / "Kölsch – (2025) KINEMA – 07 All Week.flac.mp3"
    flac_ext_path.parent.mkdir(parents=True, exist_ok=True)
    flac_ext_path.write_bytes(b"mp3")

    db_unknown = root / "Unknown Artist - Unknown Title [101].mp3"
    db_unknown.write_bytes(b"mp3")

    master_missing_track = root / "Master Artist" / "(2024) Master Album" / "Master Artist – (2024) Master Album – Missing Track.mp3"
    master_missing_track.parent.mkdir(parents=True, exist_ok=True)
    master_missing_track.write_bytes(b"mp3")

    unresolved_path = root / "Unknown Artist - Unknown Title [999].mp3"
    unresolved_path.write_bytes(b"mp3")

    playlist = root / "set.m3u"
    playlist.write_text(f"{rename_path}\n{unresolved_path}\n", encoding="utf-8")

    db_source = master_root / "Managed Artist" / "(2024) Managed Album" / "Managed Artist – (2024) Managed Album – 03 Managed Tune.flac"
    db_source.parent.mkdir(parents=True, exist_ok=True)
    db_source.write_bytes(b"flac")

    master_source = master_root / "Master Artist" / "(2024) Master Album" / "Master Artist – (2024) Master Album – 06 Missing Track.flac"
    master_source.parent.mkdir(parents=True, exist_ok=True)
    master_source.write_bytes(b"flac")

    metadata_map = {
        canonical_path.resolve(): AudioMetadata(path=canonical_path.resolve(), tags=canonical_tags, duration_s=245.0),
        rename_path.resolve(): AudioMetadata(
            path=rename_path.resolve(),
            tags={
                "title": ["Let the Beat Control Your Body"],
                "artist": ["Unlimited"],
                "album": ["Let the Beat Control Your Body"],
                "albumartist": ["2 Unlimited"],
                "date": ["1994"],
                "tracknumber": ["01"],
            },
            duration_s=230.0,
        ),
        various_path.resolve(): AudioMetadata(
            path=various_path.resolve(),
            tags={
                "title": ["Club Mix"],
                "artist": ["Track Artist"],
                "album": ["Label Sampler"],
                "albumartist": ["Artist A, Artist B, Artist C, Artist D"],
                "date": ["2023"],
                "tracknumber": ["01"],
            },
            duration_s=300.0,
        ),
        flac_ext_path.resolve(): AudioMetadata(
            path=flac_ext_path.resolve(),
            tags={
                "title": ["All Week.flac"],
                "artist": ["Kölsch"],
                "album": ["KINEMA"],
                "albumartist": ["Kölsch"],
                "date": ["2025"],
                "tracknumber": ["07"],
            },
            duration_s=280.0,
        ),
        db_unknown.resolve(): AudioMetadata(
            path=db_unknown.resolve(),
            tags={"bpm": ["124"], "initialkey": ["9M"]},
            duration_s=280.0,
        ),
        master_missing_track.resolve(): AudioMetadata(
            path=master_missing_track.resolve(),
            tags={
                "title": ["Missing Track"],
                "artist": ["Master Artist"],
                "album": ["Master Album"],
                "albumartist": ["Master Artist"],
                "date": ["2024"],
            },
            duration_s=211.0,
        ),
        unresolved_path.resolve(): AudioMetadata(
            path=unresolved_path.resolve(),
            tags={"bpm": ["123"]},
            duration_s=200.0,
        ),
        db_source.resolve(): AudioMetadata(
            path=db_source.resolve(),
            tags={
                "title": ["Managed Tune"],
                "artist": ["Managed Artist"],
                "album": ["Managed Album"],
                "albumartist": ["Managed Artist"],
                "date": ["2024"],
                "tracknumber": ["03"],
            },
            duration_s=280.0,
        ),
        master_source.resolve(): AudioMetadata(
            path=master_source.resolve(),
            tags={
                "title": ["Missing Track"],
                "artist": ["Master Artist"],
                "album": ["Master Album"],
                "albumartist": ["Master Artist"],
                "date": ["2024"],
                "tracknumber": ["06"],
            },
            duration_s=211.0,
        ),
    }

    monkeypatch.setattr(module, "read_audio_metadata", lambda path: metadata_map.get(path.resolve()))
    monkeypatch.setattr(
        module,
        "load_db_dj_pool_lookup",
        lambda conn, _root: {
            db_unknown.resolve(): DjPoolLookupRow(
                dj_pool_path=db_unknown.resolve(),
                source_path=db_source.resolve(),
                identity_id=101,
                snapshot=DjTagSnapshot(
                    artist="Managed Artist",
                    title="Managed Tune",
                    album="Managed Album",
                    genre="Techno",
                    label="Label",
                    year=2024,
                    isrc="ISRC123",
                    bpm="124",
                    musical_key="9M",
                    energy_1_10=5,
                    bpm_source="identity",
                    key_source="identity",
                    energy_source="identity",
                    identity_id=101,
                    preferred_asset_id=11,
                    preferred_path=str(db_source.resolve()),
                ),
                source_metadata=metadata_map[db_source.resolve()],
            )
        },
    )

    with sqlite3.connect(":memory:") as conn:
        summary = plan_dj_library_normalize(
            root=root,
            master_root=master_root,
            conn=conn,
            out_dir=out_dir,
            unresolved_root=unresolved_root,
            duration_tol=2.0,
        )

    assert summary["total_mp3"] == 7
    assert summary["already_canonical"] == 1
    assert summary["move_plan_rows"] == 3
    assert summary["repair_db_rows"] == 1
    assert summary["repair_master_rows"] == 1
    assert summary["unresolved_rows"] == 1
    assert summary["playlist_rewrite_rows"] == 2

    move_rows = _read_csv(out_dir / "move_plan.csv")
    dests = {row["dest_path"] for row in move_rows}
    assert any("/Various Artists/" in dest for dest in dests)
    assert any(dest.endswith("All Week.mp3") for dest in dests)
    assert any(dest.endswith("2 Unlimited – (1994) Let the Beat Control Your Body – 01 Let the Beat Control Your Body.mp3") for dest in dests)

    repair_db_rows = _read_csv(out_dir / "repair_db.csv")
    assert repair_db_rows[0]["path"] == str(db_unknown.resolve())
    assert repair_db_rows[0]["match_source"] == "db_dj_pool_path"
    assert repair_db_rows[0]["expected_dest_path"].endswith("Managed Tune.mp3")

    repair_master_rows = _read_csv(out_dir / "repair_master.csv")
    assert repair_master_rows[0]["path"] == str(master_missing_track.resolve())
    assert repair_master_rows[0]["flac_path"] == str(master_source.resolve())

    unresolved_rows = _read_csv(out_dir / "unresolved.csv")
    assert unresolved_rows[0]["source_path"] == str(unresolved_path.resolve())
    assert "/_UNRESOLVED/missing_title_artist/" in unresolved_rows[0]["dest_path"]

    playlist_rows = _read_csv(out_dir / "playlist_rewrite.csv")
    by_old = {row["old_path"]: row for row in playlist_rows}
    assert by_old[str(rename_path.resolve())]["action"] == "rewrite"
    assert by_old[str(unresolved_path.resolve())]["action"] == "comment"


def test_apply_dj_pool_relink_updates_dj_pool_path_without_mutating_files_path(tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    master_path = (tmp_path / "master" / "track.flac").resolve()
    old_mp3 = (tmp_path / "dj" / "old.mp3").resolve()
    new_mp3 = (tmp_path / "dj" / "new.mp3").resolve()
    master_path.parent.mkdir(parents=True, exist_ok=True)
    old_mp3.parent.mkdir(parents=True, exist_ok=True)
    new_mp3.parent.mkdir(parents=True, exist_ok=True)
    master_path.write_bytes(b"flac")
    old_mp3.write_bytes(b"old")
    new_mp3.write_bytes(b"new")

    conn = sqlite3.connect(str(db_path))
    create_schema_v3(conn)
    init_db(conn)
    conn.execute("INSERT INTO asset_file (path) VALUES (?)", (str(master_path),))
    conn.execute("INSERT INTO files (path, dj_pool_path) VALUES (?, ?)", (str(master_path), str(old_mp3)))
    conn.commit()
    conn.close()

    manifest = tmp_path / "relink.csv"
    manifest.write_text(
        "source_path,old_dj_pool_path,new_dj_pool_path,identity_id,reason\n"
        f"{master_path},{old_mp3},{new_mp3},101,path_mismatch\n",
        encoding="utf-8",
    )

    with sqlite3.connect(str(db_path)) as conn2:
        dry_stats = apply_dj_pool_relink(conn2, manifest, execute=False)
    assert dry_stats.updated == 1

    with sqlite3.connect(str(db_path)) as conn3:
        exec_stats = apply_dj_pool_relink(conn3, manifest, execute=True)
        row = conn3.execute("SELECT path, dj_pool_path FROM files").fetchone()
        assert row == (str(master_path), str(new_mp3))
        event = conn3.execute(
            "SELECT event_type, source_path, dest_path FROM provenance_event ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert event == ("dj_pool_relink", str(master_path), str(new_mp3))
    assert exec_stats.updated == 1


def test_apply_playlist_rewrite_manifest_rewrites_and_comments(tmp_path: Path) -> None:
    playlist = tmp_path / "set.m3u"
    old_path = "/tmp/old-track.mp3"
    unresolved_old = "/tmp/unresolved-track.mp3"
    playlist.write_text(f"{old_path}\n{unresolved_old}\n", encoding="utf-8")

    manifest = tmp_path / "playlist_rewrite.csv"
    manifest.write_text(
        "playlist_path,line_number,old_path,new_path,action,reason\n"
        f"{playlist},1,{old_path},/tmp/new-track.mp3,rewrite,path_mismatch\n"
        f"{playlist},2,{unresolved_old},/tmp/_UNRESOLVED/unresolved-track.mp3,comment,missing_title_artist\n",
        encoding="utf-8",
    )

    dry_count = apply_playlist_rewrite_manifest(manifest, execute=False)
    assert dry_count == 2
    assert playlist.read_text(encoding="utf-8") == f"{old_path}\n{unresolved_old}\n"

    exec_count = apply_playlist_rewrite_manifest(manifest, execute=True)
    assert exec_count == 2
    assert playlist.read_text(encoding="utf-8") == "/tmp/new-track.mp3\n# unresolved: /tmp/unresolved-track.mp3 (missing_title_artist)\n"
