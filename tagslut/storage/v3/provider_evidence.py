"""Provider evidence helpers for v3 library_track_sources."""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

from tagslut.metadata.provider_registry import ProviderActivationConfig, load_provider_activation_config

logger = logging.getLogger(__name__)


def write_library_track_source(
    conn: sqlite3.Connection,
    *,
    identity_key: str,
    provider: str,
    provider_track_id: str,
    source_url: str | None = None,
    raw_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    match_confidence: str | None = None,
) -> None:
    raw_payload_json = json.dumps(raw_payload, ensure_ascii=False, sort_keys=True) if raw_payload is not None else None
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True) if metadata is not None else None
    conn.execute(
        """
        INSERT OR REPLACE INTO library_track_sources (
            identity_key,
            provider,
            provider_track_id,
            source_url,
            match_confidence,
            raw_payload_json,
            metadata_json,
            fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            identity_key,
            provider,
            provider_track_id,
            source_url,
            match_confidence,
            raw_payload_json,
            metadata_json,
        ),
    )


def maybe_promote_qobuz_id(
    conn: sqlite3.Connection,
    *,
    identity_id: int,
    qobuz_id: str,
    isrc: str | None,
    corroborated_by: list[str],
    activation: ProviderActivationConfig | None = None,
) -> None:
    """
    Promote qobuz_id into track_identity.qobuz_id only when corroborated.

    Guard rails:
    - requires non-empty ISRC
    - requires at least one corroborating authoritative provider (beatport or tidal)
      with trust != do_not_use_for_canonical
    - logs and re-raises on uniqueness violations
    """
    qobuz_id_norm = (qobuz_id or "").strip()
    if not qobuz_id_norm:
        raise ValueError("qobuz_id is required")
    isrc_norm = (isrc or "").strip()
    if not isrc_norm:
        raise ValueError("qobuz_id promotion requires ISRC corroboration")

    cfg = activation or load_provider_activation_config()
    allowed_corrob: set[str] = set()
    if cfg.beatport.trust != "do_not_use_for_canonical":
        allowed_corrob.add("beatport")
    if cfg.tidal.trust != "do_not_use_for_canonical":
        allowed_corrob.add("tidal")

    corroborated = any(provider in allowed_corrob for provider in corroborated_by)
    if not corroborated:
        raise ValueError("qobuz_id promotion requires corroboration from a trusted provider")

    try:
        conn.execute(
            """
            UPDATE track_identity
            SET qobuz_id = ?
            WHERE id = ?
              AND (qobuz_id IS NULL OR TRIM(qobuz_id) = '')
            """,
            (qobuz_id_norm, int(identity_id)),
        )
    except sqlite3.IntegrityError as e:
        logger.warning("qobuz_id promotion failed due to uniqueness constraint: %s", e)
        raise

