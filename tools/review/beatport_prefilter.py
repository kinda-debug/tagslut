#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import sqlite3
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


API_BASE = "https://api.beatport.com/v4"
BEATPORT_WEB_BASE = "https://www.beatport.com"
CLIENT_ID = "ryZ8LuyQVPqbK2mBX2Hwt4qSMtnWuTYSqBPO92yQ"


def _build_ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


SSL_CONTEXT = _build_ssl_context()


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value if str(v).strip())
    text = str(value).strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _norm_isrc(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9]", "", text)


def _norm_id(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = re.sub(r"\.0+$", "", text)
    digits = re.sub(r"[^0-9]", "", text)
    return digits


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    text = str(value).strip()
    if text.lower() in {"none", "null", "nan"}:
        return ""
    return text


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _as_text(value)
        if text:
            return text
    return ""


def _json_get(meta: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in meta:
            value = meta[key]
            if isinstance(value, list):
                if value:
                    return value
            elif value not in (None, "", []):
                return value
    return None


def _http_json(
    method: str,
    url: str,
    token: str | None = None,
    form_data: dict[str, str] | None = None,
    timeout: int = 40,
) -> tuple[int, dict[str, Any]]:
    headers = {
        "accept": "application/json",
        "user-agent": "tagslut-beatport-prefilter/1.0",
    }
    data = None
    if token:
        headers["authorization"] = f"Bearer {token}"
    if form_data is not None:
        data = urlencode(form_data).encode("utf-8")
        headers["content-type"] = "application/x-www-form-urlencoded"

    req = Request(url=url, data=data, method=method.upper(), headers=headers)
    try:
        with urlopen(req, timeout=timeout, context=SSL_CONTEXT) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(payload)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except Exception:
            payload = {"error": body}
        return error.code, payload
    except URLError as error:
        raise RuntimeError(f"HTTP request failed: {error}") from error


@dataclass
class BeatportLink:
    url: str
    link_type: str
    link_id: int


def _parse_link_id(raw_segment: str) -> tuple[int, str | None]:
    segment = raw_segment.strip()
    try:
        return int(segment), None
    except ValueError:
        # Be forgiving for copy/paste typos such as "878433x".
        match = re.match(r"^(\d+)", segment)
        if match:
            return int(match.group(1)), f"Sanitized Beatport ID '{segment}' -> '{match.group(1)}'"
        raise ValueError(f"Invalid Beatport entity ID: {raw_segment}")


def parse_beatport_url(url: str) -> BeatportLink:
    parsed = urlparse(url)
    if parsed.netloc not in {"www.beatport.com", "api.beatport.com"}:
        raise ValueError(f"Unsupported Beatport host: {parsed.netloc}")

    segments = [seg for seg in parsed.path.split("/") if seg]
    if not segments:
        raise ValueError("Invalid Beatport URL path")

    if len(segments) > 1 and len(segments[0]) == 2:
        segments = segments[1:]
        if segments and segments[0] == "catalog":
            segments = segments[1:]

    if not segments:
        raise ValueError("Invalid Beatport URL path")

    first = segments[0]
    link_type = ""
    id_idx = 0

    if first == "track":
        link_type = "tracks"
        id_idx = 2
    elif first == "release":
        link_type = "releases"
        id_idx = 2
    elif first == "chart":
        link_type = "charts"
        id_idx = 2
    elif first in {"playlists", "playlist"}:
        link_type = "playlists"
        id_idx = 2
    elif first == "library" and len(segments) > 2 and segments[1] in {"playlists", "playlist"}:
        link_type = "playlists"
        id_idx = 2
    elif first in {"tracks", "releases"}:
        link_type = first
        id_idx = 1
    else:
        raise ValueError(f"Unsupported Beatport URL type: {first}")

    if len(segments) <= id_idx:
        raise ValueError("Missing Beatport entity ID in URL")

    link_id, warning = _parse_link_id(segments[id_idx])
    if warning:
        print(f"WARNING: {warning}", file=sys.stderr)

    return BeatportLink(url=url, link_type=link_type, link_id=link_id)


class BeatportClient:
    def __init__(self, credentials_file: Path):
        self.credentials_file = credentials_file
        with credentials_file.open("r", encoding="utf-8") as handle:
            self.credentials = json.load(handle)
        self.token = _as_text(self.credentials.get("access_token"))
        self.refresh_token = _as_text(self.credentials.get("refresh_token"))
        if not self.token:
            raise RuntimeError(f"Missing access_token in {credentials_file}")

    def _refresh(self) -> None:
        if not self.refresh_token:
            raise RuntimeError("Missing refresh_token; cannot refresh Beatport token")
        status, payload = _http_json(
            "POST",
            f"{API_BASE}/auth/o/token/",
            form_data={
                "client_id": CLIENT_ID,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if status != 200:
            raise RuntimeError(f"Token refresh failed ({status}): {payload}")

        self.credentials["access_token"] = payload.get("access_token", "")
        self.credentials["refresh_token"] = payload.get("refresh_token", self.refresh_token)
        self.credentials["expires_in"] = payload.get("expires_in")
        self.credentials["token_type"] = payload.get("token_type")
        self.credentials["scope"] = payload.get("scope")
        self.credentials["issued_at"] = int(time.time())
        with self.credentials_file.open("w", encoding="utf-8") as handle:
            json.dump(self.credentials, handle, indent=1)
            handle.write("\n")
        self.token = _as_text(self.credentials.get("access_token"))
        self.refresh_token = _as_text(self.credentials.get("refresh_token"))
        if not self.token:
            raise RuntimeError("Token refresh returned empty access token")

    def get_json(self, endpoint: str, retry_on_auth: bool = True) -> dict[str, Any]:
        status, payload = _http_json("GET", f"{API_BASE}{endpoint}", token=self.token)
        if status in {401, 403} and retry_on_auth:
            self._refresh()
            return self.get_json(endpoint, retry_on_auth=False)
        if status != 200:
            raise RuntimeError(f"Beatport API request failed ({status}) for {endpoint}: {payload}")
        return payload


def _track_web_url(track_payload: dict[str, Any]) -> str:
    raw = _as_text(track_payload.get("url"))
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("/"):
        return f"{BEATPORT_WEB_BASE}{raw}"
    track_id = _norm_id(track_payload.get("id"))
    slug = _as_text(track_payload.get("slug"))
    if track_id and slug:
        return f"{BEATPORT_WEB_BASE}/track/{slug}/{track_id}"
    if track_id:
        return f"{BEATPORT_WEB_BASE}/tracks/{track_id}"
    return ""


def fetch_tracks(client: BeatportClient, link: BeatportLink) -> list[dict[str, Any]]:
    if link.link_type == "tracks":
        payload = client.get_json(f"/catalog/tracks/{link.link_id}/")
        return [payload]

    if link.link_type in {"charts", "releases", "playlists"}:
        tracks: list[dict[str, Any]] = []
        page = 1
        while True:
            if link.link_type == "playlists":
                payload = client.get_json(f"/catalog/playlists/{link.link_id}/tracks/?page={page}")
                page_results = payload.get("results", [])
                for item in page_results:
                    track = item.get("track") if isinstance(item, dict) else None
                    if isinstance(track, dict):
                        tracks.append(track)
            else:
                payload = client.get_json(f"/catalog/{link.link_type}/{link.link_id}/tracks/?page={page}")
                page_results = payload.get("results", [])
                for item in page_results:
                    if isinstance(item, dict):
                        tracks.append(item)
            if not payload.get("next"):
                break
            page += 1
        return tracks

    raise RuntimeError(f"Unsupported Beatport link type for prefilter: {link.link_type}")


@dataclass
class DbRecord:
    path: str
    artist_tokens: set[str]
    duration_ms: int | None


def load_db_indexes(db_path: Path, library_root: Path) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[DbRecord]]]:
    beatport_index: dict[str, list[str]] = {}
    isrc_index: dict[str, list[str]] = {}
    title_index: dict[str, list[DbRecord]] = {}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        like_pattern = f"{str(library_root).rstrip('/')}/%"
        rows = conn.execute(
            """
            SELECT
                path,
                beatport_id,
                canonical_isrc,
                duration,
                canonical_artist,
                canonical_title,
                metadata_json
            FROM files
            WHERE path LIKE ?
            """,
            (like_pattern,),
        )

        for row in rows:
            path = _as_text(row["path"])
            if not path:
                continue

            metadata: dict[str, Any] = {}
            raw_meta = row["metadata_json"]
            if isinstance(raw_meta, str) and raw_meta.strip():
                try:
                    metadata = json.loads(raw_meta)
                except Exception:
                    metadata = {}

            beatport_id = _norm_id(
                _first_non_empty(
                    row["beatport_id"],
                    _json_get(metadata, "beatport_track_id", "track_id", "beatport_id"),
                )
            )
            if beatport_id:
                beatport_index.setdefault(beatport_id, []).append(path)

            isrc = _norm_isrc(
                _first_non_empty(
                    row["canonical_isrc"],
                    _json_get(metadata, "isrc", "ISRC", "tsrc", "TSRC"),
                )
            )
            if isrc:
                isrc_index.setdefault(isrc, []).append(path)

            artist = _first_non_empty(
                row["canonical_artist"],
                _json_get(metadata, "artist", "albumartist", "artists"),
            )
            title = _first_non_empty(
                row["canonical_title"],
                _json_get(metadata, "title", "name", "track", "track_title"),
            )
            artist_norm = _norm_text(artist)
            title_norm = _norm_text(title)
            if title_norm:
                duration_ms = None
                try:
                    duration_val = row["duration"]
                    if duration_val is not None and str(duration_val).strip() != "":
                        duration_ms = int(round(float(duration_val) * 1000.0))
                except Exception:
                    duration_ms = None
                title_index.setdefault(title_norm, []).append(
                    DbRecord(
                        path=path,
                        artist_tokens=set(artist_norm.split()) if artist_norm else set(),
                        duration_ms=duration_ms,
                    )
                )
    finally:
        conn.close()

    return beatport_index, isrc_index, title_index


def candidate_title_variants(name: str, mix_name: str) -> set[str]:
    variants = set()
    name_norm = _norm_text(name)
    mix_norm = _norm_text(mix_name)
    if name_norm:
        variants.add(name_norm)
    if name_norm and mix_name.strip():
        variants.add(_norm_text(f"{name} ({mix_name})"))
        variants.add(_norm_text(f"{name} {mix_name}"))
    if name_norm and mix_norm in {"original mix", "original", "extended mix"}:
        variants.add(_norm_text(name))
    return {variant for variant in variants if variant}


def decide_track_action(
    track: dict[str, Any],
    beatport_index: dict[str, list[str]],
    isrc_index: dict[str, list[str]],
    title_index: dict[str, list[DbRecord]],
    duration_margin_ms: int,
) -> tuple[str, str, str]:
    track_id = _norm_id(track.get("id"))
    isrc = _norm_isrc(track.get("isrc"))
    name = _as_text(track.get("name"))
    mix_name = _as_text(track.get("mix_name"))
    duration_ms = track.get("length_ms")
    try:
        duration_ms_int = int(duration_ms) if duration_ms is not None else None
    except Exception:
        duration_ms_int = None

    if track_id and track_id in beatport_index:
        return "skip", "beatport_id", beatport_index[track_id][0]

    if isrc and isrc in isrc_index:
        return "skip", "isrc", isrc_index[isrc][0]

    artist_values = track.get("artists") or []
    artist_name = ""
    if isinstance(artist_values, list):
        names = []
        for artist in artist_values:
            if isinstance(artist, dict):
                value = _as_text(artist.get("name"))
                if value:
                    names.append(value)
        artist_name = ", ".join(names)
    artist_tokens = set(_norm_text(artist_name).split()) if artist_name else set()

    for variant in candidate_title_variants(name=name, mix_name=mix_name):
        for db_record in title_index.get(variant, []):
            artist_ok = True
            if artist_tokens and db_record.artist_tokens:
                artist_ok = bool(artist_tokens & db_record.artist_tokens)

            duration_ok = True
            if duration_ms_int is not None and db_record.duration_ms is not None:
                duration_ok = abs(duration_ms_int - db_record.duration_ms) <= duration_margin_ms

            if artist_ok and duration_ok:
                return "skip", "artist_title_duration", db_record.path

    return "keep", "none", ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fast Beatport pre-download filter against canonical library DB.",
    )
    parser.add_argument("--db", required=True, help="Path to tagslut SQLite DB")
    parser.add_argument("--url", required=True, help="Beatport URL (chart/release/playlist/track)")
    parser.add_argument("--library-root", default="/Volumes/MUSIC/LIBRARY", help="Library root to compare against")
    parser.add_argument(
        "--credentials",
        default=os.environ.get(
            "BEATPORTDL_CREDENTIALS",
            "/Users/georgeskhawam/Projects/beatportdl/bin/beatportdl-credentials.json",
        ),
        help="BeatportDL credentials JSON path",
    )
    parser.add_argument("--duration-margin-ms", type=int, default=4000, help="Duration tolerance for title+artist matches")
    parser.add_argument("--out-dir", default="artifacts/compare", help="Directory for output files")
    parser.add_argument("--verbose", action="store_true", help="Verbose decision output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    db_path = Path(args.db).expanduser().resolve()
    library_root = Path(args.library_root).expanduser().resolve()
    credentials = Path(args.credentials).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        return 2
    if not credentials.exists():
        print(f"ERROR: Beatport credentials not found: {credentials}", file=sys.stderr)
        return 2

    try:
        link = parse_beatport_url(args.url)
        client = BeatportClient(credentials)
        tracks = fetch_tracks(client, link)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    beatport_index, isrc_index, title_index = load_db_indexes(db_path, library_root)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    decisions_csv = out_dir / f"beatport_prefilter_decisions_{timestamp}.csv"
    keep_urls_txt = out_dir / f"beatport_prefilter_keep_urls_{timestamp}.txt"
    summary_json = out_dir / f"beatport_prefilter_summary_{timestamp}.json"

    decisions: list[dict[str, Any]] = []
    keep_urls: list[str] = []
    skip_reasons: dict[str, int] = {}

    for track in tracks:
        action, reason, matched_path = decide_track_action(
            track=track,
            beatport_index=beatport_index,
            isrc_index=isrc_index,
            title_index=title_index,
            duration_margin_ms=args.duration_margin_ms,
        )
        track_url = _track_web_url(track)
        if action == "keep" and track_url:
            keep_urls.append(track_url)
        if action == "skip":
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

        artist = ""
        artists = track.get("artists") or []
        if isinstance(artists, list):
            artist = ", ".join(
                _as_text(artist_obj.get("name"))
                for artist_obj in artists
                if isinstance(artist_obj, dict) and _as_text(artist_obj.get("name"))
            )

        row = {
            "action": action,
            "reason": reason,
            "track_id": _norm_id(track.get("id")),
            "isrc": _norm_isrc(track.get("isrc")),
            "artist": artist,
            "title": _as_text(track.get("name")),
            "mix_name": _as_text(track.get("mix_name")),
            "length_ms": _as_text(track.get("length_ms")),
            "url": track_url,
            "matched_path": matched_path,
        }
        decisions.append(row)
        if args.verbose:
            marker = "SKIP" if action == "skip" else "KEEP"
            print(f"{marker}: {row['artist']} - {row['title']} [{reason}]")

    with decisions_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "action",
                "reason",
                "track_id",
                "isrc",
                "artist",
                "title",
                "mix_name",
                "length_ms",
                "url",
                "matched_path",
            ],
        )
        writer.writeheader()
        writer.writerows(decisions)

    keep_urls_unique = list(dict.fromkeys(url for url in keep_urls if url))
    with keep_urls_txt.open("w", encoding="utf-8") as handle:
        for url in keep_urls_unique:
            handle.write(f"{url}\n")

    summary = {
        "url": args.url,
        "link_type": link.link_type,
        "link_id": link.link_id,
        "library_root": str(library_root),
        "db_path": str(db_path),
        "total_candidates": len(decisions),
        "keep_count": len(keep_urls_unique),
        "skip_count": len(decisions) - len(keep_urls_unique),
        "skip_reasons": skip_reasons,
        "outputs": {
            "decisions_csv": str(decisions_csv),
            "keep_urls_txt": str(keep_urls_txt),
            "summary_json": str(summary_json),
        },
    }
    with summary_json.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    print(f"Prefilter candidates: {summary['total_candidates']}")
    print(f"Keep: {summary['keep_count']}")
    print(f"Skip: {summary['skip_count']}")
    if skip_reasons:
        for reason, count in sorted(skip_reasons.items()):
            print(f"  - {reason}: {count}")
    print(f"Wrote: {decisions_csv}")
    print(f"Wrote: {keep_urls_txt}")
    print(f"Wrote: {summary_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
