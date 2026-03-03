"""Staleness checks for v3 scan/integrity/enrichment flows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

DEFAULT_ENRICHMENT_MAX_AGE_SECONDS = 7 * 24 * 3600


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _num_from_mapping(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in row and row[key] is not None:
            try:
                return float(row[key])
            except (TypeError, ValueError):
                return None
    return None


def is_integrity_stale(asset: Mapping[str, Any]) -> bool:
    """Return True when integrity data must be refreshed for an asset.

    Rule:
    - stale if file stat changed since last integrity check
    - stale when required fields are missing
    """
    checked_at = _parse_timestamp(asset.get("integrity_checked_at"))
    stored_mtime = _num_from_mapping(asset, "mtime")
    stored_size = _num_from_mapping(asset, "size_bytes", "size")
    current_mtime = _num_from_mapping(asset, "current_mtime")
    current_size = _num_from_mapping(asset, "current_size_bytes", "current_size")

    if checked_at is None:
        return True
    if stored_mtime is None or stored_size is None:
        return True
    if current_mtime is None or current_size is None:
        return True

    return bool(stored_mtime != current_mtime or stored_size != current_size)


def is_hash_stale(asset: Mapping[str, Any]) -> bool:
    """Return True when full-file hash data must be refreshed for an asset.

    Rule:
    - stale if file stat changed since last hash check
    - stale when required fields are missing
    """
    checked_at = _parse_timestamp(asset.get("sha256_checked_at"))
    stored_mtime = _num_from_mapping(asset, "mtime")
    stored_size = _num_from_mapping(asset, "size_bytes", "size")
    current_mtime = _num_from_mapping(asset, "current_mtime")
    current_size = _num_from_mapping(asset, "current_size_bytes", "current_size")

    if checked_at is None:
        return True
    if stored_mtime is None or stored_size is None:
        return True
    if current_mtime is None or current_size is None:
        return True

    return bool(stored_mtime != current_mtime or stored_size != current_size)


def is_enrichment_stale(
    identity: Mapping[str, Any],
    provider_snapshots: Sequence[Mapping[str, Any]] | None = None,
    *,
    max_snapshot_age_seconds: float = DEFAULT_ENRICHMENT_MAX_AGE_SECONDS,
    now: datetime | None = None,
) -> bool:
    """Return True when enrichment should be re-run for an identity.

    Rules:
    - stale if identity.enriched_at is missing
    - stale if provider snapshots are missing
    - stale if newest provider snapshot exceeds max age
    - stale when required fields are malformed/missing
    """
    if max_snapshot_age_seconds <= 0:
        return True

    enriched_at = _parse_timestamp(identity.get("enriched_at"))
    if enriched_at is None:
        return True

    if not provider_snapshots:
        return True

    newest_snapshot: datetime | None = None
    for snapshot in provider_snapshots:
        fetched_at = _parse_timestamp(snapshot.get("fetched_at"))
        if fetched_at is None:
            return True
        if newest_snapshot is None or fetched_at > newest_snapshot:
            newest_snapshot = fetched_at

    if newest_snapshot is None:
        return True

    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    age_seconds = (now_utc - newest_snapshot).total_seconds()
    return age_seconds > max_snapshot_age_seconds

