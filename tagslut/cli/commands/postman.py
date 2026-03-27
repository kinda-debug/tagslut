from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import click

from tagslut.storage.v3 import record_provenance_event


_ISRC_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{3}[0-9]{2}[0-9]{5}\b")


def _normalize_isrc(value: str | None) -> str:
    text = (value or "").strip().upper()
    if not text:
        return ""
    text = re.sub(r"[\s-]+", "", text)
    m = _ISRC_RE.search(text)
    return m.group(0) if m else ""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _as_bytes(stream: Any) -> bytes:
    if stream is None:
        return b""
    if isinstance(stream, (bytes, bytearray)):
        return bytes(stream)
    if isinstance(stream, str):
        return stream.encode("utf-8", errors="replace")
    if isinstance(stream, list) and all(isinstance(x, int) for x in stream):
        try:
            return bytes(stream)
        except Exception:
            return b""
    return b""


def _try_parse_json(data: bytes) -> dict[str, Any] | list[Any] | None:
    text = data.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _walk_values(obj: Any) -> Iterable[Any]:
    if isinstance(obj, dict):
        for v in obj.values():
            yield v
            yield from _walk_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield v
            yield from _walk_values(v)


def _extract_isrc_from_json(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in {"isrc", "tsrc"} and isinstance(v, str):
                norm = _normalize_isrc(v)
                if norm:
                    return norm
    for v in _walk_values(obj):
        if isinstance(v, str):
            norm = _normalize_isrc(v)
            if norm:
                return norm
    return ""


def _extract_provider_ids(host: str, obj: Any) -> tuple[str, str]:
    """Return (beatport_id, tidal_id) when possible."""
    beatport_id = ""
    tidal_id = ""
    if not isinstance(obj, (dict, list)):
        return beatport_id, tidal_id

    lowered = (host or "").lower()
    if "tidal" in lowered:
        if isinstance(obj, dict):
            data = obj.get("data")
            if isinstance(data, dict):
                tidal_id = str(data.get("id") or "").strip()
            elif isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict):
                    tidal_id = str(first.get("id") or "").strip()
    if "beatport" in lowered:
        if isinstance(obj, dict):
            for k in ("id", "track_id", "beatport_id"):
                if k in obj and obj.get(k) is not None:
                    beatport_id = str(obj.get(k)).strip()
                    break
    return beatport_id, tidal_id


@dataclass(frozen=True)
class _ExecutionRow:
    name: str
    method: str
    url: str
    status_code: int | None
    duration_ms: int | None
    request_hash: str
    response_hash: str
    response_bytes: bytes


def _iter_newman_executions(report: dict[str, Any]) -> Iterable[_ExecutionRow]:
    executions = (report.get("run") or {}).get("executions") or []
    if not isinstance(executions, list):
        return
    for ex in executions:
        if not isinstance(ex, dict):
            continue
        item = ex.get("item") or {}
        name = str(item.get("name") or "").strip() or "unnamed"
        req = ex.get("request") or {}
        method = str(req.get("method") or "").strip().upper() or "GET"
        url = str((req.get("url") or {}).get("raw") or req.get("url") or "").strip()
        if not url:
            continue

        request_material = json.dumps(
            {"method": method, "url": url, "headers": req.get("headers"), "body": req.get("body")},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8", errors="replace")
        request_hash = _sha256_bytes(request_material)

        resp = ex.get("response") or {}
        status_code = None
        if resp.get("code") is not None:
            try:
                status_code = int(resp.get("code"))
            except Exception:
                status_code = None

        duration_ms = None
        if resp.get("responseTime") is not None:
            try:
                duration_ms = int(resp.get("responseTime"))
            except Exception:
                duration_ms = None

        response_bytes = _as_bytes(resp.get("stream") or resp.get("body") or b"")
        response_hash = _sha256_bytes(response_bytes) if response_bytes else ""

        yield _ExecutionRow(
            name=name,
            method=method,
            url=url,
            status_code=status_code,
            duration_ms=duration_ms,
            request_hash=request_hash,
            response_hash=response_hash,
            response_bytes=response_bytes,
        )


def _resolve_identity_id(
    conn: sqlite3.Connection,
    *,
    isrc: str,
    beatport_id: str,
    tidal_id: str,
) -> int | None:
    if isrc:
        row = conn.execute(
            """
            SELECT id
            FROM track_identity
            WHERE upper(replace(replace(isrc, '-', ''), ' ', '')) = ?
            LIMIT 1
            """,
            (isrc,),
        ).fetchone()
        if row:
            return int(row[0])
    if beatport_id:
        row = conn.execute(
            "SELECT id FROM track_identity WHERE beatport_id = ? LIMIT 1",
            (beatport_id,),
        ).fetchone()
        if row:
            return int(row[0])
    if tidal_id:
        row = conn.execute(
            "SELECT id FROM track_identity WHERE tidal_id = ? LIMIT 1",
            (tidal_id,),
        ).fetchone()
        if row:
            return int(row[0])
    return None


def register_postman_group(cli: click.Group) -> None:
    @cli.group()
    def postman():  # type: ignore  # TODO: mypy-strict
        """Postman/Newman integration helpers."""

    @postman.command("ingest")
    @click.option("--db", "db_path", required=True, type=click.Path(exists=True), help="tagslut v3 DB path")
    @click.option(
        "--newman-report",
        "report_path",
        required=True,
        type=click.Path(exists=True),
        help="Newman JSON report file",
    )
    def ingest(db_path: str, report_path: str) -> None:  # type: ignore  # TODO: mypy-strict
        """Ingest Newman JSON report into v3 provenance_event rows."""
        report = json.loads(Path(report_path).expanduser().resolve().read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise click.ClickException("Invalid Newman report: expected JSON object at top level")

        conn = sqlite3.connect(str(Path(db_path).expanduser().resolve()))
        try:
            inserted = 0
            for row in _iter_newman_executions(report):
                parsed = urlparse(row.url)
                host = (parsed.hostname or "").lower()
                provider = "unknown"
                if "tidal" in host:
                    provider = "tidal"
                elif "beatport" in host:
                    provider = "beatport"
                elif "spotify" in host:
                    provider = "spotify"

                parsed_json = _try_parse_json(row.response_bytes)
                isrc = _extract_isrc_from_json(parsed_json)
                beatport_id, tidal_id = _extract_provider_ids(host, parsed_json)
                identity_id = _resolve_identity_id(
                    conn,
                    isrc=isrc,
                    beatport_id=beatport_id,
                    tidal_id=tidal_id,
                )

                status = "ok"
                if row.status_code is None:
                    status = "unknown"
                elif row.status_code >= 400:
                    status = f"http_{row.status_code}"

                details: dict[str, Any] = {
                    "provider": provider,
                    "request_name": row.name,
                    "method": row.method,
                    "url": row.url,
                    "status_code": row.status_code,
                    "duration_ms": row.duration_ms,
                    "request_hash": row.request_hash,
                    "response_hash": row.response_hash,
                }
                if isrc:
                    details["isrc"] = isrc
                if beatport_id:
                    details["beatport_id"] = beatport_id
                if tidal_id:
                    details["tidal_id"] = tidal_id

                record_provenance_event(
                    conn,
                    event_type="postman_api_call",
                    status=status,
                    identity_id=identity_id,
                    details=details,
                )
                inserted += 1

            conn.commit()
            click.echo(f"Inserted {inserted} provenance_event row(s).")
        finally:
            conn.close()

