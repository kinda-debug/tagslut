from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from tagslut.exec.dj_tag_snapshot import DjTagSnapshot
from tagslut.storage.v3.dual_write import resolve_asset_id_by_path

logger = logging.getLogger(__name__)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_bpm_tag(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        text = str(value).strip()
        return text or None


def _normalize_key(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    return text


def _normalize_energy_tag(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_analysis_energy(value: Any) -> int | None:
    if value is None:
        return None
    try:
        loudness = float(value)
    except (TypeError, ValueError):
        return None
    return max(1, min(10, int(round(loudness * 9)) + 1))


def _resolve_export_row(conn: sqlite3.Connection, identity_id: int) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT *
        FROM v_dj_export_metadata_v1
        WHERE identity_id = ?
        """,
        (int(identity_id),),
    ).fetchone()


def _snapshot_from_row(
    row: sqlite3.Row,
    *,
    analysis_bpm: Any = None,
    analysis_key: Any = None,
    analysis_energy: Any = None,
) -> DjTagSnapshot:
    export_bpm = row["export_bpm"]
    export_key = row["export_key"]
    export_energy = row["export_energy"]
    bpm_source = row["bpm_source"]
    key_source = row["key_source"]
    energy_source = row["energy_source"]

    if export_bpm is None and analysis_bpm is not None:
        export_bpm = analysis_bpm
        bpm_source = "analysis"
    if export_key is None and analysis_key is not None:
        export_key = analysis_key
        key_source = "analysis"
    if export_energy is None and analysis_energy is not None:
        export_energy = analysis_energy
        energy_source = "analysis"

    year = row["year"]
    return DjTagSnapshot(
        artist=_normalize_text(row["artist"]),
        title=_normalize_text(row["title"]),
        album=_normalize_text(row["album"]),
        genre=_normalize_text(row["genre"]),
        label=_normalize_text(row["label"]),
        year=int(year) if year is not None else None,
        isrc=_normalize_text(row["isrc"]),
        bpm=_normalize_bpm_tag(export_bpm),
        musical_key=_normalize_key(export_key),
        energy_1_10=_normalize_energy_tag(export_energy),
        bpm_source=_normalize_text(bpm_source),
        key_source=_normalize_text(key_source),
        energy_source=_normalize_text(energy_source),
        identity_id=int(row["identity_id"]) if row["identity_id"] is not None else None,
        preferred_asset_id=(
            int(row["preferred_asset_id"]) if row["preferred_asset_id"] is not None else None
        ),
        preferred_path=_normalize_text(row["preferred_path"]),
    )


def _all_export_fields_present(row: sqlite3.Row) -> bool:
    return row["export_bpm"] is not None and row["export_key"] is not None and row["export_energy"] is not None


def _resolve_essentia_binary(binary_name: str) -> str:
    binary_path = shutil.which(binary_name)
    if binary_path is None and Path(binary_name).exists():
        binary_path = str(Path(binary_name))
    if binary_path is None:
        raise FileNotFoundError(
            f"Essentia binary '{binary_name}' not found. Install Essentia and ensure "
            "essentia_streaming_extractor_music is on PATH."
        )
    return binary_path


def _extract_analyzer_version(payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata") if isinstance(payload, dict) else None
    if isinstance(metadata, dict):
        version = metadata.get("version")
        if isinstance(version, dict):
            text = _normalize_text(version.get("essentia"))
            if text:
                return text
        text = _normalize_text(metadata.get("essentia_version"))
        if text:
            return text
    return "unknown"


def _run_essentia(flac_path: Path, *, essentia_binary: str) -> tuple[dict[str, Any], str] | None:
    binary_path = _resolve_essentia_binary(essentia_binary)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        result = subprocess.run(
            [binary_path, str(flac_path), str(tmp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr_lines = (result.stderr or "").strip().splitlines()
            stderr_tail = "\n".join(stderr_lines[-10:]) if stderr_lines else "(no stderr)"
            logger.warning(
                "Essentia failed for %s (exit=%s): %s",
                flac_path,
                result.returncode,
                stderr_tail,
            )
            return None

        payload = json.loads(tmp_path.read_text(encoding="utf-8"))
        return payload, binary_path
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse Essentia JSON for %s: %s", flac_path, exc)
        return None
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            logger.debug("Failed to clean up Essentia sidecar %s", tmp_path)


def _analysis_values_from_payload(payload: dict[str, Any]) -> tuple[float | None, str | None, int | None]:
    rhythm = payload.get("rhythm", {}) if isinstance(payload, dict) else {}
    tonal = payload.get("tonal", {}) if isinstance(payload, dict) else {}
    lowlevel = payload.get("lowlevel", {}) if isinstance(payload, dict) else {}

    bpm_value = rhythm.get("bpm") if isinstance(rhythm, dict) else None
    try:
        bpm = float(bpm_value) if bpm_value is not None else None
    except (TypeError, ValueError):
        bpm = None

    key = _normalize_text(tonal.get("key_key")) if isinstance(tonal, dict) else None
    scale = _normalize_text(tonal.get("key_scale")) if isinstance(tonal, dict) else None
    if key and scale:
        if scale.lower().startswith("min") and not key.endswith("m"):
            key = f"{key}m"

    energy = _normalize_analysis_energy(lowlevel.get("average_loudness") if isinstance(lowlevel, dict) else None)
    return bpm, key, energy


def _identity_id_for_asset_path(conn: sqlite3.Connection, asset_path: str | Path) -> int | None:
    asset_id = resolve_asset_id_by_path(conn, asset_path)
    if asset_id is None:
        return None
    active_where = "AND active = 1" if _column_exists(conn, "asset_link", "active") else ""
    row = conn.execute(
        f"""
        SELECT identity_id
        FROM asset_link
        WHERE asset_id = ?
        {active_where}
        ORDER BY id ASC
        LIMIT 1
        """,
        (int(asset_id),),
    ).fetchone()
    return int(row[0]) if row is not None else None


def resolve_dj_tag_snapshot(
    conn: sqlite3.Connection,
    identity_id: int,
    *,
    run_essentia: bool = True,
    essentia_binary: str = "essentia_streaming_extractor_music",
    dry_run: bool = False,
) -> DjTagSnapshot:
    row = _resolve_export_row(conn, identity_id)
    if row is None:
        raise RuntimeError(f"identity not found in v_dj_export_metadata_v1: {identity_id}")

    if _all_export_fields_present(row):
        return _snapshot_from_row(row)

    preferred_path_text = _normalize_text(row["preferred_path"])
    preferred_asset_id = row["preferred_asset_id"]
    if not run_essentia or not preferred_path_text or preferred_asset_id is None:
        return _snapshot_from_row(row)

    payload_and_binary = _run_essentia(Path(preferred_path_text), essentia_binary=essentia_binary)
    if payload_and_binary is None:
        return _snapshot_from_row(row)

    payload, _binary_path = payload_and_binary
    bpm, key, energy = _analysis_values_from_payload(payload)
    if not dry_run:
        conn.execute(
            """
            INSERT OR REPLACE INTO asset_analysis (
                asset_id,
                analyzer,
                analyzer_version,
                analysis_scope,
                bpm,
                musical_key,
                analysis_energy_1_10,
                confidence,
                raw_payload_json
            ) VALUES (?, ?, ?, 'dj', ?, ?, ?, ?, ?)
            """,
            (
                int(preferred_asset_id),
                "essentia",
                _extract_analyzer_version(payload),
                bpm,
                key,
                energy,
                None,
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ),
        )
        refreshed = _resolve_export_row(conn, identity_id)
        if refreshed is None:
            raise RuntimeError(f"identity disappeared during dj snapshot resolve: {identity_id}")
        return _snapshot_from_row(refreshed)

    return _snapshot_from_row(row, analysis_bpm=bpm, analysis_key=key, analysis_energy=energy)


def resolve_dj_tag_snapshot_for_path(
    conn: sqlite3.Connection,
    asset_path: str | Path,
    *,
    run_essentia: bool = True,
    essentia_binary: str = "essentia_streaming_extractor_music",
    dry_run: bool = False,
) -> DjTagSnapshot | None:
    identity_id = _identity_id_for_asset_path(conn, asset_path)
    if identity_id is None:
        return None
    return resolve_dj_tag_snapshot(
        conn,
        identity_id,
        run_essentia=run_essentia,
        essentia_binary=essentia_binary,
        dry_run=dry_run,
    )
