from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from tagslut.storage.v3 import record_provenance_event, resolve_asset_id_by_path
from tagslut.storage.v3.analysis_service import resolve_dj_tag_snapshot


def apply_dj_export_manifest(
    db_path: str | Path,
    manifest_path: str | Path,
    playlist_inputs_path: str | Path,
    *,
    tool_version: str = "build_pool_v3",
) -> int:
    db_file = Path(db_path).expanduser().resolve()
    manifest_file = Path(manifest_path).expanduser().resolve()
    playlist_file = Path(playlist_inputs_path).expanduser().resolve()

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        has_files_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='files'"
        ).fetchone() is not None
        playlist_rows: list[str] = []
        with manifest_file.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                dest_text = (row.get("dest_path") or "").strip()
                if not dest_text:
                    continue
                dest_path = Path(dest_text).expanduser().resolve()
                if not dest_path.exists():
                    continue

                identity_text = (row.get("identity_id") or "").strip()
                if not identity_text:
                    continue
                identity_id = int(identity_text)

                snapshot = resolve_dj_tag_snapshot(conn, identity_id, run_essentia=False, dry_run=True)
                source_text = (row.get("source_path") or "").strip()
                source_path = Path(source_text).expanduser().resolve() if source_text else None
                asset_id = resolve_asset_id_by_path(conn, source_path) if source_path is not None else None

                partial_metadata = any(
                    value is None
                    for value in (snapshot.bpm, snapshot.musical_key, snapshot.energy_1_10)
                )
                record_provenance_event(
                    conn,
                    event_type="dj_export",
                    status="success",
                    asset_id=asset_id,
                    identity_id=identity_id,
                    source_path=str(source_path) if source_path is not None else None,
                    dest_path=str(dest_path),
                    details={
                        "tag_snapshot": snapshot.as_dict(),
                        "bpm_source": snapshot.bpm_source,
                        "key_source": snapshot.key_source,
                        "energy_source": snapshot.energy_source,
                        "format": "mp3",
                        "bitrate": 320,
                        "tool_version": tool_version,
                        "action": (row.get("action") or "").strip().lower(),
                        "reason": (row.get("reason") or "").strip(),
                        "partial_metadata": partial_metadata,
                    },
                )
                if has_files_table and source_path is not None:
                    conn.execute(
                        "UPDATE files SET dj_pool_path = ? WHERE path = ?",
                        (str(dest_path), str(source_path)),
                    )
                playlist_rows.append(str(dest_path))

        conn.commit()
    finally:
        conn.close()

    playlist_file.write_text(
        "\n".join(playlist_rows) + ("\n" if playlist_rows else ""),
        encoding="utf-8",
    )
    return len(playlist_rows)
