#!/usr/bin/env python3
"""Extract Beatport/Tidal tracklists from a list of URLs.

Input:
  - text file with one URL per line

Outputs:
  - CSV with one row per extracted track
  - CSV with one row per link (status + counts)
  - Markdown grouped report
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.providers.beatport import BeatportProvider

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


@dataclass
class TrackRow:
    source_link: str
    normalized_link: str
    domain: str
    link_type: str
    link_title: str
    track_index: int
    track_id: str
    title: str
    artist: str
    album: str
    isrc: str
    duration_ms: str
    status: str
    note: str


@dataclass
class LinkSummary:
    source_link: str
    normalized_link: str
    domain: str
    link_type: str
    link_title: str
    status: str
    track_count: int
    note: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract tracklists from Beatport/Tidal links."
    )
    parser.add_argument("--input", type=Path, required=True, help="Text file with links.")
    parser.add_argument(
        "--tracks-csv",
        type=Path,
        required=True,
        help="Output CSV: one row per track.",
    )
    parser.add_argument(
        "--summary-csv",
        type=Path,
        required=True,
        help="Output CSV: one row per link.",
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        required=True,
        help="Output Markdown grouped report.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout seconds (default: 30).",
    )
    return parser.parse_args()


def normalize_link(raw: str) -> str:
    link = raw.strip()
    link = link.rstrip("\\")
    link = link.rstrip(".,;:!?")
    if not link:
        return ""
    if not link.startswith(("http://", "https://")):
        link = f"https://{link}"
    return link


def is_tidal(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "tidal.com" in host


def is_beatport(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "beatport.com" in host


def _join_names(items: Any) -> str:
    if isinstance(items, list):
        names: list[str] = []
        for item in items:
            if isinstance(item, dict):
                name = item.get("name")
                if name:
                    names.append(str(name))
            elif isinstance(item, str):
                names.append(item)
        return ", ".join(names)
    return ""


def _beatport_get_next_data(client: httpx.Client, url: str) -> tuple[dict[str, Any] | None, str]:
    response = client.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0 Safari/537.36"
            )
        },
    )
    if response.status_code != 200:
        return None, f"http_{response.status_code}"
    match = NEXT_DATA_RE.search(response.text)
    if not match:
        return None, "next_data_not_found"
    try:
        payload = json.loads(match.group(1))
    except Exception as exc:  # pragma: no cover - defensive
        return None, f"next_data_json_error:{exc}"
    if not isinstance(payload, dict):
        return None, "next_data_invalid"
    return payload, ""


def _as_ms_from_seconds(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(int(round(float(value) * 1000)))
    except Exception:
        return ""


def _as_ms(value: Any) -> str:
    if value is None:
        return ""
    try:
        return str(int(round(float(value))))
    except Exception:
        return ""


def _beatport_pick_tracks_query(
    next_data: dict[str, Any],
    predicate,
) -> dict[str, Any] | None:
    queries = (
        next_data.get("props", {})
        .get("pageProps", {})
        .get("dehydratedState", {})
        .get("queries", [])
    )
    if not isinstance(queries, list):
        return None
    for query in queries:
        key = query.get("queryKey")
        if predicate(key):
            data = query.get("state", {}).get("data", {})
            if isinstance(data, dict):
                return data
    return None


def _beatport_track_from_payload(item: dict[str, Any]) -> dict[str, str]:
    track = item.get("track") if isinstance(item.get("track"), dict) else item
    if not isinstance(track, dict):
        return {}

    title = str(track.get("name") or track.get("track_name") or track.get("title") or "")
    mix_name = str(track.get("mix_name") or "").strip()
    if mix_name and mix_name.lower() not in {"original mix", "original"}:
        title = f"{title} ({mix_name})"

    artists = _join_names(track.get("artists"))
    if not artists:
        artists = str(track.get("artists_name") or track.get("artist_name") or "")

    release = track.get("release")
    album = ""
    if isinstance(release, dict):
        album = str(release.get("name") or "")
    if not album:
        album = str(track.get("release_name") or "")

    length_ms = track.get("length_ms") or track.get("duration_ms")
    return {
        "track_id": str(track.get("id") or track.get("track_id") or ""),
        "title": title,
        "artist": artists,
        "album": album,
        "isrc": str(track.get("isrc") or ""),
        "duration_ms": _as_ms(length_ms),
    }


def _to_rows_from_beatport_payloads(
    link: str,
    link_type: str,
    link_title: str,
    payloads: list[dict[str, Any]],
) -> list[TrackRow]:
    rows: list[TrackRow] = []
    seen: set[str] = set()
    idx = 1
    for payload in payloads:
        parsed = _beatport_track_from_payload(payload)
        if not parsed:
            continue
        identity = parsed["track_id"] or f"{parsed['artist']}::{parsed['title']}"
        if identity in seen:
            continue
        seen.add(identity)
        rows.append(
            TrackRow(
                source_link=link,
                normalized_link=link,
                domain="beatport",
                link_type=link_type,
                link_title=link_title,
                track_index=idx,
                track_id=parsed["track_id"],
                title=parsed["title"],
                artist=parsed["artist"],
                album=parsed["album"],
                isrc=parsed["isrc"],
                duration_ms=parsed["duration_ms"],
                status="ok",
                note="",
            )
        )
        idx += 1
    return rows


def _tidal_get(client: httpx.Client, endpoint: str, token: str, country: str, params: dict[str, Any] | None = None) -> httpx.Response:
    merged = dict(params or {})
    if "countryCode" not in merged:
        merged["countryCode"] = country
    return client.get(
        endpoint,
        params=merged,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )


def extract_from_tidal(
    link: str,
    client: httpx.Client,
    token: str | None,
    country_code: str,
) -> tuple[str, str, list[TrackRow], str]:
    parsed = urlparse(link)
    parts = [p for p in parsed.path.strip("/").split("/") if p and p.lower() != "u"]
    if len(parts) < 2:
        return "tidal", "unknown", [], "unsupported_path"
    if not token:
        return "tidal", parts[0], [], "tidal_token_missing"

    kind = parts[0].lower()
    entity_id = parts[1]
    tracks: list[TrackRow] = []

    if kind == "track":
        resp = _tidal_get(client, f"https://api.tidal.com/v1/tracks/{entity_id}", token, country_code)
        if resp.status_code != 200:
            return "tidal", "track", [], f"http_{resp.status_code}"
        data = resp.json()
        artists = _join_names(data.get("artists"))
        album = data.get("album", {}).get("title") if isinstance(data.get("album"), dict) else ""
        tracks.append(
            TrackRow(
                source_link=link,
                normalized_link=link,
                domain="tidal",
                link_type="track",
                link_title=str(data.get("title") or ""),
                track_index=1,
                track_id=str(data.get("id") or entity_id),
                title=str(data.get("title") or ""),
                artist=artists,
                album=str(album or ""),
                isrc=str(data.get("isrc") or ""),
                duration_ms=_as_ms_from_seconds(data.get("duration")),
                status="ok",
                note="",
            )
        )
        return "tidal", "track", tracks, ""

    if kind == "album":
        meta = _tidal_get(client, f"https://api.tidal.com/v1/albums/{entity_id}", token, country_code)
        if meta.status_code != 200:
            return "tidal", "album", [], f"http_{meta.status_code}"
        album_data = meta.json()
        album_title = str(album_data.get("title") or "")

        offset = 0
        index = 1
        while True:
            resp = _tidal_get(
                client,
                f"https://api.tidal.com/v1/albums/{entity_id}/tracks",
                token,
                country_code,
                {"limit": 100, "offset": offset},
            )
            if resp.status_code != 200:
                return "tidal", "album", tracks, f"http_{resp.status_code}"
            data = resp.json()
            items = data.get("items", []) if isinstance(data, dict) else []
            if not items:
                break
            for item in items:
                tracks.append(
                    TrackRow(
                        source_link=link,
                        normalized_link=link,
                        domain="tidal",
                        link_type="album",
                        link_title=album_title,
                        track_index=index,
                        track_id=str(item.get("id") or ""),
                        title=str(item.get("title") or ""),
                        artist=_join_names(item.get("artists")),
                        album=album_title,
                        isrc=str(item.get("isrc") or ""),
                        duration_ms=_as_ms_from_seconds(item.get("duration")),
                        status="ok",
                        note="",
                    )
                )
                index += 1
            if len(items) < 100:
                break
            offset += 100
        return "tidal", "album", tracks, ""

    if kind == "playlist":
        meta = _tidal_get(client, f"https://api.tidal.com/v1/playlists/{entity_id}", token, country_code)
        if meta.status_code != 200:
            return "tidal", "playlist", [], f"http_{meta.status_code}"
        playlist_title = str(meta.json().get("title") or "")

        offset = 0
        index = 1
        while True:
            resp = _tidal_get(
                client,
                f"https://api.tidal.com/v1/playlists/{entity_id}/tracks",
                token,
                country_code,
                {"limit": 100, "offset": offset},
            )
            if resp.status_code != 200:
                return "tidal", "playlist", tracks, f"http_{resp.status_code}"
            data = resp.json()
            items = data.get("items", []) if isinstance(data, dict) else []
            if not items:
                break
            for item in items:
                tracks.append(
                    TrackRow(
                        source_link=link,
                        normalized_link=link,
                        domain="tidal",
                        link_type="playlist",
                        link_title=playlist_title,
                        track_index=index,
                        track_id=str(item.get("id") or ""),
                        title=str(item.get("title") or ""),
                        artist=_join_names(item.get("artists")),
                        album=str(item.get("album", {}).get("title") or ""),
                        isrc=str(item.get("isrc") or ""),
                        duration_ms=_as_ms_from_seconds(item.get("duration")),
                        status="ok",
                        note="",
                    )
                )
                index += 1
            if len(items) < 100:
                break
            offset += 100
        return "tidal", "playlist", tracks, ""

    if kind == "artist":
        # Artist pages are unbounded; return top tracks to provide a practical list.
        meta = _tidal_get(client, f"https://api.tidal.com/v1/artists/{entity_id}", token, country_code)
        if meta.status_code != 200:
            return "tidal", "artist", [], f"http_{meta.status_code}"
        artist_name = str(meta.json().get("name") or "")
        resp = _tidal_get(client, f"https://api.tidal.com/v1/artists/{entity_id}/toptracks", token, country_code, {"limit": 100, "offset": 0})
        if resp.status_code != 200:
            return "tidal", "artist", [], f"http_{resp.status_code}"
        items = resp.json().get("items", [])
        index = 1
        for item in items:
            tracks.append(
                TrackRow(
                    source_link=link,
                    normalized_link=link,
                    domain="tidal",
                    link_type="artist_toptracks",
                    link_title=artist_name,
                    track_index=index,
                    track_id=str(item.get("id") or ""),
                    title=str(item.get("title") or ""),
                    artist=_join_names(item.get("artists")) or artist_name,
                    album=str(item.get("album", {}).get("title") or ""),
                    isrc=str(item.get("isrc") or ""),
                    duration_ms=_as_ms_from_seconds(item.get("duration")),
                    status="ok",
                    note="artist_toptracks",
                )
            )
            index += 1
        return "tidal", "artist_toptracks", tracks, ""

    return "tidal", kind, [], "unsupported_tidal_kind"


def extract_from_beatport(
    link: str,
    client: httpx.Client,
    provider: BeatportProvider,
) -> tuple[str, str, list[TrackRow], str]:
    parsed = urlparse(link)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    tracks: list[TrackRow] = []
    if not parts:
        return "beatport", "unknown", tracks, "unsupported_path"

    if parts[0] == "release" and len(parts) >= 3:
        slug, release_id = parts[1], parts[2]
        if not release_id.isdigit():
            return "beatport", "release", tracks, "invalid_release_id"
        next_data, note = _beatport_get_next_data(client, link)
        if next_data:
            data = _beatport_pick_tracks_query(
                next_data,
                lambda key: isinstance(key, list)
                and len(key) >= 2
                and key[0] == "tracks"
                and isinstance(key[1], dict)
                and str(key[1].get("release_id")) == release_id,
            )
            if data and isinstance(data.get("results"), list):
                rows = _to_rows_from_beatport_payloads(
                    link=link,
                    link_type="release",
                    link_title=f"{slug} ({release_id})",
                    payloads=data.get("results", []),
                )
                if rows:
                    return "beatport", "release", rows, ""
        # fallback to provider helper
        results = provider.fetch_release_tracks(release_id, slug=slug)
        rows: list[TrackRow] = []
        idx = 1
        for item in results:
            rows.append(
                TrackRow(
                    source_link=link,
                    normalized_link=link,
                    domain="beatport",
                    link_type="release",
                    link_title=f"{slug} ({release_id})",
                    track_index=idx,
                    track_id=str(item.service_track_id or ""),
                    title=str(item.title or ""),
                    artist=str(item.artist or ""),
                    album=str(item.album or ""),
                    isrc=str(item.isrc or ""),
                    duration_ms=_as_ms(item.duration_ms),
                    status="ok",
                    note="",
                )
            )
            idx += 1
        if rows:
            return "beatport", "release", rows, ""
        return "beatport", "release", tracks, note or "no_tracks_found"

    if parts[0] == "track" and len(parts) >= 3:
        track_id = parts[2]
        if not track_id.isdigit():
            return "beatport", "track", tracks, "invalid_track_id"
        item = provider.fetch_by_id(track_id)
        if item is None:
            return "beatport", "track", tracks, "track_not_found"
        tracks.append(
            TrackRow(
                source_link=link,
                normalized_link=link,
                domain="beatport",
                link_type="track",
                link_title=str(item.title or ""),
                track_index=1,
                track_id=str(item.service_track_id or track_id),
                title=str(item.title or ""),
                artist=str(item.artist or ""),
                album=str(item.album or ""),
                isrc=str(item.isrc or ""),
                duration_ms=_as_ms(item.duration_ms),
                status="ok",
                note="",
            )
        )
        return "beatport", "track", tracks, ""

    if parts[0] == "v4" and len(parts) >= 3 and parts[1] == "catalog" and parts[2] == "tracks":
        query = parse_qs(parsed.query)
        isrc = (query.get("isrc") or [""])[0].strip()
        if isrc:
            results = provider.search_by_isrc(isrc)
            idx = 1
            for item in results:
                tracks.append(
                    TrackRow(
                        source_link=link,
                        normalized_link=link,
                        domain="beatport",
                        link_type="v4_isrc",
                        link_title=isrc,
                        track_index=idx,
                        track_id=str(item.service_track_id or ""),
                        title=str(item.title or ""),
                        artist=str(item.artist or ""),
                        album=str(item.album or ""),
                        isrc=str(item.isrc or ""),
                        duration_ms=_as_ms(item.duration_ms),
                        status="ok",
                        note="",
                    )
                )
                idx += 1
            return "beatport", "v4_isrc", tracks, "" if tracks else "no_tracks_found"
        if len(parts) >= 4 and parts[3].isdigit():
            # /v4/catalog/tracks/<id>/stream...
            track_id = parts[3]
            if track_id.isdigit():
                item = provider.fetch_by_id(track_id)
                if item is None:
                    return "beatport", "v4_track", tracks, "track_not_found"
                tracks.append(
                    TrackRow(
                        source_link=link,
                        normalized_link=link,
                        domain="beatport",
                        link_type="v4_track",
                        link_title=str(item.title or ""),
                        track_index=1,
                        track_id=str(item.service_track_id or track_id),
                        title=str(item.title or ""),
                        artist=str(item.artist or ""),
                        album=str(item.album or ""),
                        isrc=str(item.isrc or ""),
                        duration_ms=_as_ms(item.duration_ms),
                        status="ok",
                        note="",
                    )
                )
                return "beatport", "v4_track", tracks, ""
        return "beatport", "v4_tracks", tracks, "unsupported_v4_tracks_url"

    if parts[0] == "chart" and len(parts) >= 3:
        chart_id_raw = parts[2]
        match = re.match(r"^(\d+)", chart_id_raw)
        if not match:
            return "beatport", "chart", tracks, "invalid_chart_id"
        chart_id = match.group(1)
        if chart_id != chart_id_raw:
            fixed = parsed._replace(path=f"/chart/{parts[1]}/{chart_id}").geturl()
            link = fixed
        next_data, note = _beatport_get_next_data(client, link)
        if not next_data:
            return "beatport", "chart", tracks, note
        data = _beatport_pick_tracks_query(
            next_data,
            lambda key: isinstance(key, list)
            and any(f"chart-{chart_id}-tracks" in str(item) for item in key),
        )
        if not data or not isinstance(data.get("results"), list):
            return "beatport", "chart", tracks, "chart_tracks_not_found"
        rows = _to_rows_from_beatport_payloads(
            link=link,
            link_type="chart",
            link_title=f"{parts[1]} ({chart_id})",
            payloads=data.get("results", []),
        )
        return "beatport", "chart", rows, "" if rows else "no_tracks_found"

    if parts[0] == "playlists" and len(parts) >= 3 and parts[1] == "share":
        playlist_id = parts[2]
        next_data, note = _beatport_get_next_data(client, link)
        if not next_data:
            return "beatport", "playlist_share", tracks, note
        data = _beatport_pick_tracks_query(
            next_data,
            lambda key: isinstance(key, list)
            and any(f"catalog-playlist-{playlist_id}-page=" in str(item) for item in key),
        )
        if not data or not isinstance(data.get("results"), list):
            return "beatport", "playlist_share", tracks, "playlist_tracks_not_found"
        rows = _to_rows_from_beatport_payloads(
            link=link,
            link_type="playlist_share",
            link_title=f"playlist_share ({playlist_id})",
            payloads=data.get("results", []),
        )
        return "beatport", "playlist_share", rows, "" if rows else "no_tracks_found"

    if parts[0] == "library" and len(parts) >= 3 and parts[1] == "playlists":
        playlist_id = parts[2]
        # Library playlist links are often private in direct form; try share URL fallback.
        share_link = f"https://www.beatport.com/playlists/share/{playlist_id}"
        next_data, note = _beatport_get_next_data(client, share_link)
        if not next_data:
            return "beatport", "library_playlist", tracks, note
        data = _beatport_pick_tracks_query(
            next_data,
            lambda key: isinstance(key, list)
            and any(f"catalog-playlist-{playlist_id}-page=" in str(item) for item in key),
        )
        if not data:
            return "beatport", "library_playlist", tracks, "library_playlist_private_or_unavailable"
        rows = _to_rows_from_beatport_payloads(
            link=link,
            link_type="library_playlist",
            link_title=f"library_playlist ({playlist_id})",
            payloads=data.get("results", []),
        )
        return "beatport", "library_playlist", rows, "" if rows else "no_tracks_found"

    return "beatport", parts[0], tracks, "unsupported_beatport_kind"


def write_tracks_csv(path: Path, rows: list[TrackRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "source_link",
                "normalized_link",
                "domain",
                "link_type",
                "link_title",
                "track_index",
                "track_id",
                "title",
                "artist",
                "album",
                "isrc",
                "duration_ms",
                "status",
                "note",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.source_link,
                    row.normalized_link,
                    row.domain,
                    row.link_type,
                    row.link_title,
                    row.track_index,
                    row.track_id,
                    row.title,
                    row.artist,
                    row.album,
                    row.isrc,
                    row.duration_ms,
                    row.status,
                    row.note,
                ]
            )


def write_summary_csv(path: Path, rows: list[LinkSummary]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "source_link",
                "normalized_link",
                "domain",
                "link_type",
                "link_title",
                "status",
                "track_count",
                "note",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.source_link,
                    row.normalized_link,
                    row.domain,
                    row.link_type,
                    row.link_title,
                    row.status,
                    row.track_count,
                    row.note,
                ]
            )


def write_report_md(path: Path, summary_rows: list[LinkSummary], track_rows: list[TrackRow]) -> None:
    by_link: dict[str, list[TrackRow]] = {}
    for row in track_rows:
        by_link.setdefault(row.normalized_link, []).append(row)

    lines: list[str] = ["# Tracklists by Link", ""]
    for summary in summary_rows:
        lines.append(f"## {summary.normalized_link}")
        lines.append(f"- Domain: `{summary.domain}`")
        lines.append(f"- Type: `{summary.link_type}`")
        lines.append(f"- Status: `{summary.status}`")
        lines.append(f"- Tracks: `{summary.track_count}`")
        if summary.note:
            lines.append(f"- Note: `{summary.note}`")
        tracks = sorted(by_link.get(summary.normalized_link, []), key=lambda r: r.track_index)
        if tracks:
            lines.append("")
            for item in tracks:
                artist_prefix = f"{item.artist} - " if item.artist else ""
                album_suffix = f" [{item.album}]" if item.album else ""
                lines.append(f"{item.track_index}. {artist_prefix}{item.title}{album_suffix}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    if not args.input.exists():
        raise SystemExit(f"Input file not found: {args.input}")

    raw_links = [line.rstrip("\n") for line in args.input.read_text(encoding="utf-8").splitlines()]
    links_seen: set[str] = set()
    links: list[str] = []
    source_by_link: dict[str, str] = {}
    for raw in raw_links:
        norm = normalize_link(raw)
        if not norm:
            continue
        if norm in links_seen:
            continue
        links_seen.add(norm)
        links.append(norm)
        source_by_link[norm] = raw

    tm = TokenManager()
    tidal_token = tm.ensure_valid_token("tidal")
    tidal_token_value = tidal_token.access_token if tidal_token and tidal_token.access_token else None
    tidal_country = "US"
    try:
        country = tm._tokens.get("tidal", {}).get("country_code")  # type: ignore[attr-defined]
        if isinstance(country, str) and country.strip():
            tidal_country = country.strip().upper()
    except Exception:
        pass

    track_rows: list[TrackRow] = []
    summary_rows: list[LinkSummary] = []

    client = httpx.Client(timeout=args.timeout, follow_redirects=True)
    beatport = BeatportProvider(tm)
    try:
        for idx, link in enumerate(links, start=1):
            print(f"[{idx}/{len(links)}] {link}")
            domain = "unknown"
            link_type = "unknown"
            extracted: list[TrackRow] = []
            note = ""
            status = "ok"
            link_title = ""
            try:
                if is_tidal(link):
                    domain, link_type, extracted, note = extract_from_tidal(
                        link=link,
                        client=client,
                        token=tidal_token_value,
                        country_code=tidal_country,
                    )
                elif is_beatport(link):
                    domain, link_type, extracted, note = extract_from_beatport(
                        link=link,
                        client=client,
                        provider=beatport,
                    )
                else:
                    status = "error"
                    note = "unsupported_domain"

                if extracted:
                    link_title = extracted[0].link_title
                    track_rows.extend(extracted)
                    status = "ok"
                else:
                    status = "empty" if not note else "error"
            except Exception as exc:
                status = "error"
                note = f"exception:{exc}"

            summary_rows.append(
                LinkSummary(
                    source_link=source_by_link.get(link, link),
                    normalized_link=link,
                    domain=domain,
                    link_type=link_type,
                    link_title=link_title,
                    status=status,
                    track_count=len(extracted),
                    note=note,
                )
            )

        write_tracks_csv(args.tracks_csv, track_rows)
        write_summary_csv(args.summary_csv, summary_rows)
        write_report_md(args.report_md, summary_rows, track_rows)

        ok = sum(1 for row in summary_rows if row.status == "ok")
        err = sum(1 for row in summary_rows if row.status != "ok")
        print("Done.")
        print(f"  links_total: {len(summary_rows)}")
        print(f"  links_ok:    {ok}")
        print(f"  links_error: {err}")
        print(f"  tracks_total:{len(track_rows)}")
        print(f"  tracks_csv:  {args.tracks_csv}")
        print(f"  summary_csv: {args.summary_csv}")
        print(f"  report_md:   {args.report_md}")
        return 0
    finally:
        beatport.close()
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
