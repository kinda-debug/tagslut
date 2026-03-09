from __future__ import annotations

from pathlib import Path

from tagslut.cli.commands.execute import run_execute_move_plan


def test_run_execute_move_plan_moves_track_sidecars(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    dest_root = tmp_path / "dest"
    src_root.mkdir(parents=True)
    dest_root.mkdir(parents=True)

    src_file = src_root / "track.flac"
    src_lyrics = src_root / "track.lrc"
    src_cover = src_root / "track.cover.jpg"
    src_file.write_bytes(b"audio")
    src_lyrics.write_text("[00:00.00] hello\n", encoding="utf-8")
    src_cover.write_bytes(b"cover")

    dest_file = dest_root / "final name.flac"
    plan_path = tmp_path / "plan.csv"
    plan_path.write_text(
        "action,path,dest_path\nMOVE,"
        + str(src_file)
        + ","
        + str(dest_file)
        + "\n",
        encoding="utf-8",
    )

    result = run_execute_move_plan(
        plan_path=plan_path,
        db=None,
        dry_run=False,
        verify=False,
        echo=lambda _msg: None,
    )

    assert result.counts["moved"] == 1
    assert dest_file.exists()
    assert (dest_root / "final name.lrc").exists()
    assert (dest_root / "final name.cover.jpg").exists()
    assert not src_lyrics.exists()
    assert not src_cover.exists()
