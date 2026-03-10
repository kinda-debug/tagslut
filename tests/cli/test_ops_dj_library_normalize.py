from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tagslut.cli.main import cli
from tagslut.cli.commands import ops as ops_commands
from tagslut.exec.dj_library_normalize import RelinkStats


def test_ops_plan_dj_library_normalize_invokes_planner(tmp_path, monkeypatch) -> None:
    root = tmp_path / "DJ_LIBRARY"
    master_root = tmp_path / "MASTER_LIBRARY"
    out_dir = tmp_path / "artifacts"
    db_path = tmp_path / "music.db"
    root.mkdir()
    master_root.mkdir()
    db_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("TAGSLUT_DB", str(db_path))

    captured: dict[str, Path | float] = {}

    def fake_plan(*, root: Path, master_root: Path, conn, out_dir: Path, unresolved_root: Path, duration_tol: float):  # type: ignore[no-untyped-def]
        captured["root"] = root
        captured["master_root"] = master_root
        captured["out_dir"] = out_dir
        captured["unresolved_root"] = unresolved_root
        captured["duration_tol"] = duration_tol
        return {
            "total_mp3": 10,
            "already_canonical": 2,
            "move_plan_rows": 3,
            "repair_master_rows": 1,
            "repair_db_rows": 1,
            "unresolved_rows": 3,
            "playlist_rewrite_rows": 2,
            "outputs": {
                "summary_json": str(out_dir / "summary.json"),
                "move_plan_csv": str(out_dir / "move_plan.csv"),
            },
        }

    monkeypatch.setattr(ops_commands, "plan_dj_library_normalize", fake_plan)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "ops",
            "plan-dj-library-normalize",
            "--root",
            str(root),
            "--master-root",
            str(master_root),
            "--out-dir",
            str(out_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["root"] == root.resolve()
    assert captured["master_root"] == master_root.resolve()
    assert captured["unresolved_root"] == (root / "_UNRESOLVED").resolve()
    assert captured["duration_tol"] == 2.0
    assert "Move plan rows: 3" in result.output
    assert "repair_db_rows" not in result.output


def test_ops_relink_dj_pool_dry_run_reports_counts(tmp_path, monkeypatch) -> None:
    manifest = tmp_path / "relink.csv"
    manifest.write_text("source_path,old_dj_pool_path,new_dj_pool_path,identity_id,reason\n", encoding="utf-8")
    playlist_manifest = tmp_path / "playlist.csv"
    playlist_manifest.write_text("playlist_path,line_number,old_path,new_path,action,reason\n", encoding="utf-8")
    db_path = tmp_path / "music.db"
    db_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("TAGSLUT_DB", str(db_path))

    monkeypatch.setattr(
        ops_commands,
        "apply_dj_pool_relink",
        lambda conn, manifest_path, execute: RelinkStats(rows=4, updated=3, skipped=1, errors=0),
    )
    monkeypatch.setattr(ops_commands, "apply_playlist_rewrite_manifest", lambda manifest_path, execute: 2)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "ops",
            "relink-dj-pool",
            "--manifest",
            str(manifest),
            "--playlist-rewrite-manifest",
            str(playlist_manifest),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Rows: 4" in result.output
    assert "Updated: 3" in result.output
    assert "Playlist rewrites: 2" in result.output
    assert "DRY-RUN" in result.output
