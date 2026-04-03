from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import httpx
from mutagen.flac import FLAC, Picture
from mutagen.id3 import PictureType
from mutagen.mp4 import MP4, MP4Cover

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.providers.qobuz import QobuzProvider
from tagslut.metadata.providers.tidal import TidalProvider

_SPOTIFY_CLIENT_ID_B64 = "ODNlNDQzMGI0NzAwNDM0YmFhMjEyMjhhOWM3ZDExYzU="
_SPOTIFY_CLIENT_SECRET_B64 = "OWJiOWUxMzFmZjI4NDI0Y2I2YTQyMGFmZGY0MWQ0NGE="
_SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
_SPOTIFY_API_BASE = "https://api.spotify.com/v1"
_QOBUZ_DOWNLOAD_APIS = (
    "https://dab.yeet.su/api/stream?trackId=",
    "https://dabmusic.xyz/api/stream?trackId=",
    "https://qbz.afkarxyz.fun/api/track/",
)
_AUDIO_EXTENSIONS = {".flac", ".m4a", ".mp4", ".mp3", ".wav", ".aif", ".aiff"}
_DEFAULT_SERVICES = ("qobuz", "tidal", "amazon")
_DEFAULT_FOLDER_TEMPLATE = "{artist}/[{year}] {album}"
_DEFAULT_FILENAME_TEMPLATE = "{disc}-{track}. {title} - {artist}"


class SpotifyIntakeError(RuntimeError):
    pass


@dataclass
class SpotifyTrack:
    spotify_id: str
    spotify_url: str
    title: str
    artist: str
    album: str
    album_artist: str
    release_date: str
    duration_ms: int | None
    isrc: str
    track_number: int
    total_tracks: int
    disc_number: int
    total_discs: int
    cover_url: str
    copyright: str
    publisher: str
    collection_type: str
    collection_title: str
    playlist_index: int

    @property
    def year(self) -> str:
        return self.release_date[:4] if self.release_date else ""


@dataclass
class SpotifyCollection:
    url: str
    kind: str
    title: str
    tracks: list[SpotifyTrack]


@dataclass
class DownloadRecord:
    spotify_id: str
    spotify_url: str
    title: str
    artist: str
    album: str
    isrc: str
    service: str | None
    provider_track_id: str | None
    resolved_url: str | None
    output_path: str | None
    status: str
    error: str | None


def _decode_cred(value: str) -> str:
    return base64.b64decode(value).decode("utf-8")


def _sanitize_component(value: str, *, fallback: str = "Unknown") -> str:
    text = (value or "").strip()
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback


def _format_track_number(value: int | None) -> str:
    if not value:
        return "00"
    return f"{int(value):02d}"


def _write_picture_flac(audio: FLAC, image_data: bytes) -> None:
    pic = Picture()
    pic.data = image_data
    pic.type = PictureType.COVER_FRONT
    pic.mime = "image/jpeg"
    audio.add_picture(pic)


def _maybe_download_cover(client: httpx.Client, cover_url: str) -> bytes | None:
    if not cover_url:
        return None
    try:
        response = client.get(cover_url, timeout=20.0)
        response.raise_for_status()
    except Exception:
        return None
    return response.content


def _audio_files(root: Path) -> set[Path]:
    if not root.exists():
        return set()
    return {
        path.resolve()
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS
    }


def _first_new_audio_file(before: set[Path], after_root: Path) -> Path | None:
    candidates = sorted(_audio_files(after_root) - before, key=lambda path: path.stat().st_mtime)
    if candidates:
        return candidates[-1]
    existing = sorted(_audio_files(after_root), key=lambda path: path.stat().st_mtime)
    return existing[-1] if existing else None


def is_spotify_url(url: str) -> bool:
    host = urlparse((url or "").strip()).netloc.lower()
    return "spotify.com" in host or (url or "").strip().startswith("spotify:")


def parse_spotify_url(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    if parsed.netloc == "embed.spotify.com":
        qs = parse_qs(parsed.query)
        embedded = (qs.get("uri") or [""])[0]
        if not embedded:
            raise SpotifyIntakeError(f"Unsupported Spotify URL: {url}")
        return parse_spotify_url(embedded)

    if parsed.scheme == "spotify":
        parts = url.split(":")
        if len(parts) == 3 and parts[1] in {"track", "album", "playlist"}:
            return {"type": parts[1], "id": parts[2]}
        raise SpotifyIntakeError(f"Unsupported Spotify URL: {url}")

    host = parsed.netloc.lower()
    if host not in {"open.spotify.com", "play.spotify.com"}:
        raise SpotifyIntakeError(f"Unsupported Spotify URL: {url}")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) > 1 and parts[0].startswith("intl-"):
        parts = parts[1:]
    if len(parts) >= 2 and parts[0] in {"track", "album", "playlist"}:
        return {"type": parts[0], "id": parts[1]}
    raise SpotifyIntakeError(f"Unsupported Spotify URL: {url}")


class SpotifyMetadataClient:
    def __init__(self, *, timeout: float = 30.0) -> None:
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)
        self._access_token: str | None = None

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> SpotifyMetadataClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        auth = f"{_decode_cred(_SPOTIFY_CLIENT_ID_B64)}:{_decode_cred(_SPOTIFY_CLIENT_SECRET_B64)}"
        headers = {
            "Authorization": f"Basic {base64.b64encode(auth.encode('utf-8')).decode('utf-8')}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        response = self.client.post(
            _SPOTIFY_TOKEN_URL,
            headers=headers,
            data={"grant_type": "client_credentials"},
        )
        if response.status_code != 200:
            raise SpotifyIntakeError(
                f"Spotify token request failed: http_{response.status_code}"
            )
        payload = response.json()
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise SpotifyIntakeError("Spotify token request returned no access token")
        self._access_token = token
        return token

    def _request(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.client.get(
            f"{_SPOTIFY_API_BASE}{path}",
            params=params or {},
            headers={"Authorization": f"Bearer {self._get_access_token()}"},
        )
        if response.status_code == 429:
            raise SpotifyIntakeError("spotify_rate_limited")
        if response.status_code != 200:
            raise SpotifyIntakeError(f"spotify_http_{response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise SpotifyIntakeError("spotify_invalid_payload")
        return payload

    def _track_details_map(self, ids: list[str]) -> dict[str, dict[str, Any]]:
        details: dict[str, dict[str, Any]] = {}
        unique_ids = [track_id for track_id in ids if track_id]
        for start in range(0, len(unique_ids), 50):
            batch_ids = unique_ids[start : start + 50]
            payload = self._request("/tracks", params={"ids": ",".join(batch_ids)})
            tracks = payload.get("tracks")
            if not isinstance(tracks, list):
                continue
            for track in tracks:
                if not isinstance(track, dict):
                    continue
                track_id = str(track.get("id") or "").strip()
                if track_id:
                    details[track_id] = track
        return details

    def _track_from_payload(
        self,
        payload: dict[str, Any],
        *,
        collection_type: str,
        collection_title: str,
        playlist_index: int,
    ) -> SpotifyTrack:
        album = payload.get("album") if isinstance(payload.get("album"), dict) else {}
        artists = payload.get("artists") if isinstance(payload.get("artists"), list) else []
        artist_names = [str(item.get("name") or "").strip() for item in artists if isinstance(item, dict)]
        artist = ", ".join([name for name in artist_names if name]) or "Unknown Artist"
        album_artists = album.get("artists") if isinstance(album.get("artists"), list) else artists
        album_artist_names = [
            str(item.get("name") or "").strip()
            for item in album_artists
            if isinstance(item, dict)
        ]
        cover_images = album.get("images") if isinstance(album.get("images"), list) else []
        cover_url = ""
        for image in cover_images:
            if isinstance(image, dict) and image.get("url"):
                cover_url = str(image["url"])
                break
        copyrights = album.get("copyrights") if isinstance(album.get("copyrights"), list) else []
        copyright_text = ""
        for item in copyrights:
            if isinstance(item, dict) and item.get("text"):
                copyright_text = str(item["text"])
                break
        return SpotifyTrack(
            spotify_id=str(payload.get("id") or ""),
            spotify_url=str(
                (
                    payload.get("external_urls")
                    if isinstance(payload.get("external_urls"), dict)
                    else {}
                ).get("spotify")
                or ""
            ),
            title=str(payload.get("name") or ""),
            artist=artist,
            album=str(album.get("name") or ""),
            album_artist=", ".join([name for name in album_artist_names if name]) or artist,
            release_date=str(album.get("release_date") or ""),
            duration_ms=int(payload["duration_ms"]) if payload.get("duration_ms") is not None else None,
            isrc=str(
                (
                    payload.get("external_ids")
                    if isinstance(payload.get("external_ids"), dict)
                    else {}
                ).get("isrc")
                or ""
            ),
            track_number=int(payload.get("track_number") or 0),
            total_tracks=int(album.get("total_tracks") or 0),
            disc_number=int(payload.get("disc_number") or 0),
            total_discs=int(album.get("total_discs") or 0),
            cover_url=cover_url,
            copyright=copyright_text,
            publisher="",
            collection_type=collection_type,
            collection_title=collection_title,
            playlist_index=playlist_index,
        )

    def fetch_collection(self, url: str) -> SpotifyCollection:
        info = parse_spotify_url(url)
        kind = info["type"]
        entity_id = info["id"]

        if kind == "track":
            payload = self._request(f"/tracks/{entity_id}")
            track = self._track_from_payload(
                payload,
                collection_type="track",
                collection_title=str(payload.get("name") or ""),
                playlist_index=1,
            )
            return SpotifyCollection(url=url, kind="track", title=track.title, tracks=[track])

        if kind == "album":
            album_payload = self._request(f"/albums/{entity_id}")
            album_title = str(album_payload.get("name") or "")
            items = list(
                (
                    album_payload.get("tracks")
                    if isinstance(album_payload.get("tracks"), dict)
                    else {}
                ).get("items")
                or []
            )
            next_url = (
                (album_payload.get("tracks") if isinstance(album_payload.get("tracks"), dict) else {}).get("next")
                or None
            )
            while next_url:
                response = self.client.get(
                    str(next_url),
                    headers={"Authorization": f"Bearer {self._get_access_token()}"},
                )
                if response.status_code != 200:
                    raise SpotifyIntakeError(f"spotify_http_{response.status_code}")
                page = response.json()
                if not isinstance(page, dict):
                    raise SpotifyIntakeError("spotify_invalid_payload")
                items.extend(page.get("items") or [])
                next_url = page.get("next") or None
            track_ids = [str(item.get("id") or "") for item in items if isinstance(item, dict)]
            details = self._track_details_map(track_ids)
            tracks: list[SpotifyTrack] = []
            for index, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue
                track_id = str(item.get("id") or "")
                payload = details.get(track_id, item)
                if isinstance(payload, dict) and payload.get("album") is None:
                    payload = dict(payload)
                    payload["album"] = {
                        "name": album_title,
                        "release_date": album_payload.get("release_date"),
                        "total_tracks": album_payload.get("total_tracks"),
                        "total_discs": album_payload.get("total_discs"),
                        "artists": album_payload.get("artists"),
                        "images": album_payload.get("images"),
                        "copyrights": album_payload.get("copyrights"),
                    }
                tracks.append(
                    self._track_from_payload(
                        payload if isinstance(payload, dict) else item,
                        collection_type="album",
                        collection_title=album_title,
                        playlist_index=index,
                    )
                )
            return SpotifyCollection(url=url, kind="album", title=album_title, tracks=tracks)

        if kind == "playlist":
            playlist_payload = self._request(f"/playlists/{entity_id}")
            playlist_title = str(playlist_payload.get("name") or "")
            items = list(
                (
                    playlist_payload.get("tracks")
                    if isinstance(playlist_payload.get("tracks"), dict)
                    else {}
                ).get("items")
                or []
            )
            next_url = (
                (playlist_payload.get("tracks") if isinstance(playlist_payload.get("tracks"), dict) else {}).get("next")
                or None
            )
            while next_url:
                response = self.client.get(
                    str(next_url),
                    headers={"Authorization": f"Bearer {self._get_access_token()}"},
                )
                if response.status_code != 200:
                    raise SpotifyIntakeError(f"spotify_http_{response.status_code}")
                page = response.json()
                if not isinstance(page, dict):
                    raise SpotifyIntakeError("spotify_invalid_payload")
                items.extend(page.get("items") or [])
                next_url = page.get("next") or None
            track_ids = [
                str((item.get("track") if isinstance(item, dict) else {}).get("id") or "")
                for item in items
                if isinstance(item, dict) and isinstance(item.get("track"), dict)
            ]
            details = self._track_details_map(track_ids)
            tracks: list[SpotifyTrack] = []
            for index, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue
                track_ref = item.get("track")
                if not isinstance(track_ref, dict):
                    continue
                track_id = str(track_ref.get("id") or "")
                payload = details.get(track_id, track_ref)
                tracks.append(
                    self._track_from_payload(
                        payload,
                        collection_type="playlist",
                        collection_title=playlist_title,
                        playlist_index=index,
                    )
                )
            return SpotifyCollection(url=url, kind="playlist", title=playlist_title, tracks=tracks)

        raise SpotifyIntakeError(f"Unsupported Spotify URL type: {kind}")


def _parse_qobuz_track_id(url: str) -> str | None:
    match = re.search(r"/track/([A-Za-z0-9]+)", url or "")
    return match.group(1) if match else None


def _parse_tidal_track_id(url: str) -> str | None:
    match = re.search(r"/track/([0-9]+)", url or "")
    return match.group(1) if match else None


def _parse_amazon_track_id(url: str) -> str | None:
    match = re.search(r"/tracks/([A-Z0-9]{10})", url or "")
    return match.group(1) if match else None


def resolve_songlink_urls(
    client: httpx.Client,
    spotify_url: str,
) -> dict[str, str]:
    encoded = quote(spotify_url, safe="")
    urls: dict[str, str] = {}
    try:
        response = client.get(
            f"https://api.song.link/v1-alpha.1/links?url={encoded}",
            timeout=20.0,
        )
        if response.status_code == 200:
            payload = response.json()
            links = payload.get("linksByPlatform") if isinstance(payload, dict) else {}
            if isinstance(links, dict):
                mapping = {
                    "qobuz": "qobuz",
                    "tidal": "tidal",
                    "amazon": "amazonMusic",
                }
                for key, platform_key in mapping.items():
                    platform = links.get(platform_key)
                    if isinstance(platform, dict) and platform.get("url"):
                        urls[key] = str(platform["url"])
                if urls:
                    return urls
        if response.status_code not in {200, 404, 429}:
            response.raise_for_status()
    except Exception:
        pass

    try:
        spotify_id = parse_spotify_url(spotify_url)["id"]
        response = client.get(
            f"https://song.link/s/{spotify_id}",
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"},
            timeout=20.0,
        )
        response.raise_for_status()
        html = response.text
    except Exception:
        return urls

    patterns = {
        "qobuz": r"https://(?:open|play)\.qobuz\.com/track/[A-Za-z0-9]+",
        "tidal": r"https://(?:listen\.)?tidal\.com/(?:browse/)?track/[0-9]+",
        "amazon": r"https://music\.amazon\.com/tracks/[A-Z0-9]{10}(?:\?[^\"'\s<]*)?",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, html)
        if match:
            urls[key] = match.group(0)
    return urls


def _render_folder(track: SpotifyTrack, template: str) -> Path:
    rendered = template
    replacements = {
        "artist": _sanitize_component(track.artist),
        "album": _sanitize_component(track.album),
        "year": _sanitize_component(track.year, fallback="Unknown"),
    }
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{key}}}", value)
    parts = [part for part in rendered.split("/") if part and part != "."]
    return Path(*parts) if parts else Path()


def _render_filename(track: SpotifyTrack, template: str, ext: str) -> str:
    rendered = template
    replacements = {
        "artist": _sanitize_component(track.artist),
        "title": _sanitize_component(track.title),
        "album": _sanitize_component(track.album),
        "disc": _format_track_number(track.disc_number),
        "track": _format_track_number(track.track_number or track.playlist_index),
        "year": _sanitize_component(track.year, fallback="Unknown"),
    }
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{key}}}", value)
    rendered = _sanitize_component(rendered, fallback=f"{track.spotify_id}{ext}")
    if not rendered.lower().endswith(ext.lower()):
        rendered = f"{rendered}{ext}"
    return rendered


def _embed_flac_metadata(
    filepath: Path,
    track: SpotifyTrack,
    client: httpx.Client,
) -> None:
    audio = FLAC(str(filepath))
    audio.delete()
    audio["TITLE"] = track.title
    audio["ARTIST"] = track.artist
    audio["ALBUM"] = track.album
    audio["ALBUMARTIST"] = track.album_artist or track.artist
    if track.year:
        audio["DATE"] = track.year
    audio["TRACKNUMBER"] = str(track.track_number or track.playlist_index or 1)
    if track.total_tracks:
        audio["TRACKTOTAL"] = str(track.total_tracks)
    audio["DISCNUMBER"] = str(track.disc_number or 1)
    if track.total_discs:
        audio["DISCTOTAL"] = str(track.total_discs)
    if track.isrc:
        audio["ISRC"] = track.isrc
    audio["SPOTIFY_ID"] = track.spotify_id
    audio["URL"] = track.spotify_url
    cover = _maybe_download_cover(client, track.cover_url)
    if cover:
        _write_picture_flac(audio, cover)
    audio.save()


def _embed_mp4_metadata(
    filepath: Path,
    track: SpotifyTrack,
    client: httpx.Client,
) -> None:
    audio = MP4(str(filepath))
    audio.delete()
    audio["\xa9nam"] = [track.title]
    audio["\xa9ART"] = [track.artist]
    audio["\xa9alb"] = [track.album]
    audio["aART"] = [track.album_artist or track.artist]
    if track.year:
        audio["\xa9day"] = [track.year]
    audio["trkn"] = [(track.track_number or track.playlist_index or 1, track.total_tracks or 0)]
    audio["disk"] = [(track.disc_number or 1, track.total_discs or 0)]
    cover = _maybe_download_cover(client, track.cover_url)
    if cover:
        audio["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


def _embed_metadata(filepath: Path, track: SpotifyTrack, client: httpx.Client) -> None:
    suffix = filepath.suffix.lower()
    if suffix == ".flac":
        _embed_flac_metadata(filepath, track, client)
    elif suffix in {".m4a", ".mp4"}:
        _embed_mp4_metadata(filepath, track, client)


def _download_qobuz(
    *,
    client: httpx.Client,
    track: SpotifyTrack,
    provider_track_id: str,
    destination: Path,
) -> None:
    last_error: Exception | None = None
    for quality in ("27", "7", "6"):
        for api_base in _QOBUZ_DOWNLOAD_APIS:
            try:
                if "qbz.afkarxyz.fun" in api_base:
                    api_url = f"{api_base}{provider_track_id}?quality={quality}"
                else:
                    api_url = f"{api_base}{provider_track_id}&quality={quality}"
                response = client.get(api_url, timeout=60.0)
                response.raise_for_status()
                payload = response.json()
                download_url = ""
                if isinstance(payload, dict):
                    download_url = str(payload.get("url") or "")
                    if not download_url and isinstance(payload.get("data"), dict):
                        download_url = str(payload["data"].get("url") or "")
                if not download_url:
                    raise SpotifyIntakeError("qobuz_missing_download_url")
                with client.stream("GET", download_url, timeout=300.0) as stream:
                    stream.raise_for_status()
                    with destination.open("wb") as handle:
                        for chunk in stream.iter_bytes():
                            if chunk:
                                handle.write(chunk)
                return
            except Exception as exc:
                last_error = exc
    raise SpotifyIntakeError(str(last_error or "qobuz_download_failed"))


def _download_amazon(
    *,
    client: httpx.Client,
    provider_track_id: str,
    destination_base: Path,
) -> Path:
    api_url = f"https://amzn.afkarxyz.fun/api/track/{provider_track_id}"
    response = client.get(api_url, timeout=60.0)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise SpotifyIntakeError("amazon_invalid_payload")
    stream_url = str(payload.get("streamUrl") or "").strip()
    if not stream_url:
        raise SpotifyIntakeError("amazon_missing_stream_url")
    decryption_key = str(payload.get("decryptionKey") or "").strip()
    encrypted_path = destination_base.with_suffix(".enc")
    with client.stream("GET", stream_url, timeout=300.0) as stream:
        stream.raise_for_status()
        with encrypted_path.open("wb") as handle:
            for chunk in stream.iter_bytes():
                if chunk:
                    handle.write(chunk)
    if not decryption_key:
        final_path = destination_base.with_suffix(".m4a")
        encrypted_path.replace(final_path)
        return final_path

    codec_probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", str(encrypted_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    codec = codec_probe.stdout.strip().lower()
    suffix = ".flac" if codec == "flac" else ".m4a"
    final_path = destination_base.with_suffix(suffix)
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-decryption_key",
            decryption_key,
            "-i",
            str(encrypted_path),
            "-c",
            "copy",
            str(final_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        encrypted_path.unlink()
    except FileNotFoundError:
        pass
    if result.returncode != 0:
        raise SpotifyIntakeError(result.stderr.strip() or "amazon_decryption_failed")
    return final_path


def _download_tidal_with_wrapper(
    *,
    repo_root: Path,
    track: SpotifyTrack,
    tidal_url: str,
    destination_dir: Path,
) -> Path:
    wrapper = repo_root / "tools" / "tiddl"
    if not wrapper.exists():
        raise SpotifyIntakeError(f"Missing Tidal wrapper: {wrapper}")
    before = _audio_files(destination_dir)
    proc = subprocess.run(
        [
            str(wrapper),
            "--path",
            str(destination_dir),
            "--scan-path",
            str(destination_dir),
            "--skip-errors",
            tidal_url,
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        output = "\n".join(part for part in [proc.stdout.strip(), proc.stderr.strip()] if part)
        raise SpotifyIntakeError(output or f"tiddl exited with {proc.returncode}")
    downloaded = _first_new_audio_file(before, destination_dir)
    if downloaded is None:
        raise SpotifyIntakeError("tiddl produced no audio file")
    return downloaded


def _resolved_urls_for_track(
    *,
    client: httpx.Client,
    track: SpotifyTrack,
    tidal_provider: TidalProvider,
    qobuz_provider: QobuzProvider,
) -> dict[str, str]:
    resolved = resolve_songlink_urls(client, track.spotify_url)
    if "qobuz" not in resolved and track.isrc:
        qobuz_hits = qobuz_provider.search_by_isrc(track.isrc)
        if qobuz_hits:
            resolved_url = qobuz_hits[0].url
            if resolved_url:
                resolved["qobuz"] = resolved_url
    if "tidal" not in resolved and track.isrc:
        tidal_hits = tidal_provider.search_by_isrc(track.isrc)
        if tidal_hits:
            resolved_url = tidal_hits[0].url
            if resolved_url:
                resolved["tidal"] = resolved_url
    return resolved


def _download_track_via_service(
    *,
    repo_root: Path,
    client: httpx.Client,
    track: SpotifyTrack,
    service: str,
    destination_dir: Path,
    destination_name: str,
    resolved_urls: dict[str, str],
) -> tuple[Path, str | None, str | None]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    base_destination = destination_dir / destination_name

    if service == "qobuz":
        resolved_url = resolved_urls.get("qobuz") or ""
        provider_track_id = _parse_qobuz_track_id(resolved_url)
        if not provider_track_id and not track.isrc:
            raise SpotifyIntakeError("qobuz unavailable (missing ISRC and resolved URL)")
        if not provider_track_id:
            raise SpotifyIntakeError("qobuz unavailable (could not resolve track id)")
        final_path = base_destination.with_suffix(".flac")
        _download_qobuz(
            client=client,
            track=track,
            provider_track_id=provider_track_id,
            destination=final_path,
        )
        return final_path, resolved_url or None, provider_track_id

    if service == "tidal":
        resolved_url = resolved_urls.get("tidal") or ""
        if not resolved_url:
            raise SpotifyIntakeError("tidal unavailable (could not resolve URL)")
        downloaded = _download_tidal_with_wrapper(
            repo_root=repo_root,
            track=track,
            tidal_url=resolved_url,
            destination_dir=destination_dir,
        )
        return downloaded, resolved_url, _parse_tidal_track_id(resolved_url)

    if service == "amazon":
        resolved_url = resolved_urls.get("amazon") or ""
        provider_track_id = _parse_amazon_track_id(resolved_url)
        if not provider_track_id:
            raise SpotifyIntakeError("amazon unavailable (could not resolve ASIN)")
        downloaded = _download_amazon(
            client=client,
            provider_track_id=provider_track_id,
            destination_base=base_destination,
        )
        return downloaded, resolved_url or None, provider_track_id

    raise SpotifyIntakeError(f"Unsupported service: {service}")


def download_spotify_collection(
    *,
    url: str,
    batch_root: Path,
    repo_root: Path,
    out_dir: Path,
    manifest_path: Path | None = None,
    keep_track_ids: set[str] | None = None,
    services: tuple[str, ...] = _DEFAULT_SERVICES,
    folder_template: str = _DEFAULT_FOLDER_TEMPLATE,
    filename_template: str = _DEFAULT_FILENAME_TEMPLATE,
) -> tuple[Path, list[DownloadRecord]]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_root.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    with SpotifyMetadataClient() as spotify_client:
        collection = spotify_client.fetch_collection(url)
        selected_tracks = [
            track
            for track in collection.tracks
            if not keep_track_ids or track.spotify_id in keep_track_ids
        ]
        if not selected_tracks:
            raise SpotifyIntakeError("No Spotify tracks selected for download")

        collection_root = batch_root
        if collection.kind in {"album", "playlist"}:
            collection_root = batch_root / _sanitize_component(collection.title, fallback="spotify")
            collection_root.mkdir(parents=True, exist_ok=True)

        log_path = batch_root / f"SpotiFLAC_{stamp}.txt"
        failed_path = batch_root / f"SpotiFLAC_{stamp}_Failed.txt"
        m3u8_path = batch_root / f"{_sanitize_component(collection.title, fallback='spotify')}.m3u8"
        manifest = manifest_path or (out_dir / f"spotify_acquisition_manifest_{stamp}.json")

        tm = TokenManager()
        tidal_provider = TidalProvider(tm)
        qobuz_provider = QobuzProvider(tm)

        log_lines: list[str] = []
        failed_lines: list[str] = []
        records: list[DownloadRecord] = []
        playlist_entries: list[str] = []

        try:
            for index, track in enumerate(selected_tracks, start=1):
                line_prefix = f"[{index}/{len(selected_tracks)}] {track.artist} - {track.title}"
                log_lines.append(line_prefix)
                relative_dir = _render_folder(track, folder_template)
                destination_dir = collection_root / relative_dir
                destination_name = _render_filename(track, filename_template, "")
                resolved_urls = _resolved_urls_for_track(
                    client=spotify_client.client,
                    track=track,
                    tidal_provider=tidal_provider,
                    qobuz_provider=qobuz_provider,
                )
                downloaded_path: Path | None = None
                last_error: str | None = None
                winning_service: str | None = None
                winning_url: str | None = None
                provider_track_id: str | None = None

                for service in services:
                    log_lines.append(f"  trying: {service}")
                    try:
                        downloaded_path, winning_url, provider_track_id = _download_track_via_service(
                            repo_root=repo_root,
                            client=spotify_client.client,
                            track=track,
                            service=service,
                            destination_dir=destination_dir,
                            destination_name=destination_name,
                            resolved_urls=resolved_urls,
                        )
                        if not downloaded_path.exists():
                            raise SpotifyIntakeError("downloaded file missing")
                        _embed_metadata(downloaded_path, track, spotify_client.client)
                        log_lines.append(f"  downloaded: {service} -> {downloaded_path}")
                        playlist_entries.append(
                            os.path.relpath(downloaded_path, start=batch_root)
                        )
                        winning_service = service
                        break
                    except Exception as exc:
                        last_error = str(exc)
                        log_lines.append(f"  failed: {service} -> {last_error}")

                if winning_service is None or downloaded_path is None:
                    failed_lines.append(f"{track.artist} - {track.title} | {last_error or 'All services failed'}")
                    records.append(
                        DownloadRecord(
                            spotify_id=track.spotify_id,
                            spotify_url=track.spotify_url,
                            title=track.title,
                            artist=track.artist,
                            album=track.album,
                            isrc=track.isrc,
                            service=None,
                            provider_track_id=None,
                            resolved_url=None,
                            output_path=None,
                            status="failed",
                            error=last_error or "All services failed",
                        )
                    )
                    continue

                records.append(
                    DownloadRecord(
                        spotify_id=track.spotify_id,
                        spotify_url=track.spotify_url,
                        title=track.title,
                        artist=track.artist,
                        album=track.album,
                        isrc=track.isrc,
                        service=winning_service,
                        provider_track_id=provider_track_id,
                        resolved_url=winning_url,
                        output_path=str(downloaded_path),
                        status="downloaded",
                        error=None,
                    )
                )

        finally:
            tidal_provider.close()
            qobuz_provider.close()

        log_path.write_text("\n".join(log_lines) + ("\n" if log_lines else ""), encoding="utf-8")
        failed_path.write_text("\n".join(failed_lines) + ("\n" if failed_lines else ""), encoding="utf-8")
        if collection.kind in {"album", "playlist"} and playlist_entries:
            m3u8_path.write_text("\n".join(playlist_entries) + "\n", encoding="utf-8")

        manifest.write_text(
            json.dumps(
                {
                    "provider": "spotify",
                    "source_url": url,
                    "kind": collection.kind,
                    "title": collection.title,
                    "records": [asdict(record) for record in records],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        if not any(record.status == "downloaded" for record in records):
            raise SpotifyIntakeError(f"All Spotify downloads failed. See {failed_path}")
        return manifest, records


def _read_keep_track_ids(path: Path | None) -> set[str] | None:
    if path is None or not path.exists():
        return None
    keep_ids: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        value = raw.strip()
        if not value:
            continue
        try:
            info = parse_spotify_url(value)
        except SpotifyIntakeError:
            continue
        if info["type"] == "track" and info["id"]:
            keep_ids.add(info["id"])
    return keep_ids or None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download Spotify URLs via tagslut intake adapter.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--batch-root", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--keep-track-url-file", type=Path, default=None)
    parser.add_argument("--manifest-path", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    keep_track_ids = _read_keep_track_ids(args.keep_track_url_file)
    try:
        manifest, records = download_spotify_collection(
            url=args.url,
            batch_root=args.batch_root.expanduser().resolve(),
            repo_root=args.repo_root.expanduser().resolve(),
            out_dir=args.out_dir.expanduser().resolve(),
            manifest_path=args.manifest_path.expanduser().resolve() if args.manifest_path else None,
            keep_track_ids=keep_track_ids,
        )
    except SpotifyIntakeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    downloaded = sum(1 for record in records if record.status == "downloaded")
    failed = sum(1 for record in records if record.status != "downloaded")
    print(f"Spotify download manifest: {manifest}")
    print(f"Spotify downloaded: {downloaded}")
    print(f"Spotify failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
