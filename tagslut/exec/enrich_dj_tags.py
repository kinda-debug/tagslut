"""Enrich DJ-oriented FLAC tags from v3 identity data and Essentia fallback."""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from mutagen.flac import FLAC

from tagslut.storage.v3.dual_write import resolve_asset_id_by_path
from tagslut.storage.v3.identity_service import resolve_active_identity

logger = logging.getLogger(__name__)

__all__ = ["enrich_dj_tags"]


def _normalize_bpm(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        text = str(value).strip()
        return text or None


def _normalize_key_value(key_name: Any, key_scale: Any = None) -> str | None:
    key_text = str(key_name).strip() if key_name is not None else ""
    scale_text = str(key_scale).strip().lower() if key_scale is not None else ""
    if not key_text:
        return None

    key_text = re.sub(r"\s+", " ", key_text)
    lowered = key_text.lower()
    is_minor = scale_text.startswith("min") or "minor" in lowered or lowered.endswith("m")
    key_text = re.sub(r"\s*(major|minor|maj|min)\s*$", "", key_text, flags=re.IGNORECASE).strip()
    if not key_text:
        return None
    return f"{key_text}m" if is_minor and not key_text.endswith("m") else key_text


def _normalize_energy(value: Any) -> str | None:
    if value is None:
        return None
    try:
        loudness = float(value)
    except (TypeError, ValueError):
        return None
    normalized = max(1, min(10, int(round(loudness * 9)) + 1))
    return str(normalized)


def _write_flac_tags(
    flac_path: Path,
    *,
    bpm: str | None,
    key: str | None,
    energy: str | None,
) -> None:
    audio = FLAC(flac_path)
    if bpm is not None:
        audio["bpm"] = [bpm]
    if key is not None:
        audio["initialkey"] = [key]
    if energy is not None:
        audio["energy"] = [energy]
    audio.save()


def _resolve_identity_row(conn: sqlite3.Connection, asset_id: int) -> sqlite3.Row | None:
    link_row = conn.execute(
        """
        SELECT identity_id
        FROM asset_link
        WHERE asset_id = ? AND active = 1
        ORDER BY id ASC
        LIMIT 1
        """,
        (int(asset_id),),
    ).fetchone()
    if link_row is None:
        return None
    return resolve_active_identity(conn, int(link_row["identity_id"]))


def _run_essentia(
    flac_path: Path,
    *,
    essentia_binary: str,
) -> dict[str, Any] | None:
    binary_path = shutil.which(essentia_binary)
    if binary_path is None and Path(essentia_binary).exists():
        binary_path = str(Path(essentia_binary))
    if binary_path is None:
        raise FileNotFoundError(
            f"Essentia binary '{essentia_binary}' not found. Install Essentia and ensure "
            "essentia_streaming_extractor_music is on PATH."
        )

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

        try:
            return json.loads(tmp_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to parse Essentia JSON for %s: %s", flac_path, exc)
            return None
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            logger.debug("Failed to clean up Essentia sidecar %s", tmp_path)


def enrich_dj_tags(
    conn: sqlite3.Connection,
    flac_path: str | Path,
    *,
    dry_run: bool = False,
    essentia_binary: str = "essentia_streaming_extractor_music",
) -> dict[str, str | None]:
    """Fill DJ-oriented FLAC tags from v3 identity data or Essentia analysis."""
    flac_path_obj = Path(flac_path)
    asset_id = resolve_asset_id_by_path(conn, flac_path_obj)
    if asset_id is None:
        logger.warning("asset not found in v3 for %s, skipping DJ tag enrichment", flac_path_obj)
        return {}

    identity_row = _resolve_identity_row(conn, asset_id)
    if identity_row is None:
        logger.warning("no identity link for %s, skipping enrichment", flac_path_obj)
        return {}

    cached_bpm = _normalize_bpm(identity_row["canonical_bpm"])
    cached_key = _normalize_key_value(identity_row["canonical_key"])
    if cached_bpm is not None and cached_key is not None:
        if dry_run:
            logger.info(
                "dry-run: would write bpm=%s initialkey=%s for %s",
                cached_bpm,
                cached_key,
                flac_path_obj,
            )
        else:
            _write_flac_tags(flac_path_obj, bpm=cached_bpm, key=cached_key, energy=None)
        return {"bpm": cached_bpm, "key": cached_key, "energy": None}

    payload = _run_essentia(flac_path_obj, essentia_binary=essentia_binary)
    if payload is None:
        return {}

    rhythm = payload.get("rhythm", {}) if isinstance(payload, dict) else {}
    tonal = payload.get("tonal", {}) if isinstance(payload, dict) else {}
    lowlevel = payload.get("lowlevel", {}) if isinstance(payload, dict) else {}

    derived_bpm = _normalize_bpm(rhythm.get("bpm"))
    derived_key = _normalize_key_value(tonal.get("key_key"), tonal.get("key_scale"))
    derived_energy = _normalize_energy(lowlevel.get("average_loudness"))

    final_bpm = cached_bpm or derived_bpm
    final_key = cached_key or derived_key
    result = {"bpm": final_bpm, "key": final_key, "energy": derived_energy}

    if dry_run:
        logger.info(
            "dry-run: would write bpm=%s initialkey=%s energy=%s for %s",
            final_bpm,
            final_key,
            derived_energy,
            flac_path_obj,
        )
        return result

    if final_bpm is not None or final_key is not None or derived_energy is not None:
        _write_flac_tags(
            flac_path_obj,
            bpm=final_bpm,
            key=final_key,
            energy=derived_energy,
        )

    if final_bpm is not None or final_key is not None:
        conn.execute(
            """
            UPDATE track_identity
            SET canonical_bpm = ?, canonical_key = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (final_bpm, final_key, int(identity_row["id"])),
        )

    return result
