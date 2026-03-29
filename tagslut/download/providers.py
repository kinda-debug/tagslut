from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from tagslut.download.models import DownloadResult


class DownloadProvider(ABC):
    provider: str

    @abstractmethod
    def download_track(self, isrc: str, dest_dir: Path) -> DownloadResult:
        raise NotImplementedError

    @abstractmethod
    def download_release(self, release_id: str, dest_dir: Path) -> list[DownloadResult]:
        raise NotImplementedError


class TidalWrapperDownloadProvider(DownloadProvider):
    provider = "tidal"
    download_source = "tidal_wrapper"

    def __init__(self, wrapper_path: Optional[Path] = None) -> None:
        self.wrapper_path = wrapper_path or (Path(__file__).resolve().parents[2] / "tools" / "tiddl")

    def download_track(self, isrc: str, dest_dir: Path) -> DownloadResult:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if not self.wrapper_path.exists():
            raise RuntimeError(f"tiddl wrapper not found at {self.wrapper_path}")
        # We intentionally keep invocation minimal here; tools/get-intake remains the primary orchestrator.
        # This adapter is a thin subprocess wrapper to enable routing and policy checks.
        proc = subprocess.run(
            [str(self.wrapper_path), isrc],
            cwd=str(dest_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"tiddl wrapper failed ({proc.returncode}): {proc.stderr.strip()}")
        # Wrapper output structure is not stable; adapter does not attempt to discover the downloaded file.
        raise NotImplementedError("TidalWrapperDownloadProvider download result discovery is not implemented")

    def download_release(self, release_id: str, dest_dir: Path) -> list[DownloadResult]:
        _ = release_id
        _ = dest_dir
        raise NotImplementedError("Tidal wrapper release download is not implemented")


class BeatportStoreDownloadProvider(DownloadProvider):
    provider = "beatport"
    download_source = "beatport_store"

    def download_track(self, isrc: str, dest_dir: Path) -> DownloadResult:
        _ = isrc
        _ = dest_dir
        raise NotImplementedError("Beatport store download workflow is not implemented in this repo")

    def download_release(self, release_id: str, dest_dir: Path) -> list[DownloadResult]:
        _ = release_id
        _ = dest_dir
        raise NotImplementedError("Beatport store release download workflow is not implemented in this repo")


class QobuzPurchaseDownloadProvider(DownloadProvider):
    provider = "qobuz"
    download_source = "qobuz_purchase"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        app_id: str | None = None,
        user_auth_token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url or os.getenv("QOBUZ_API_BASE_URL", "https://www.qobuz.com/api.json/0.2")
        self.app_id = app_id or os.getenv("QOBUZ_APP_ID")
        self.user_auth_token = user_auth_token or os.getenv("QOBUZ_USER_AUTH_TOKEN")
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)
        return self._client

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.app_id or not self.user_auth_token:
            raise RuntimeError("Qobuz credentials missing: set QOBUZ_APP_ID and QOBUZ_USER_AUTH_TOKEN")
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        merged = dict(params)
        merged.setdefault("app_id", self.app_id)
        merged.setdefault("user_auth_token", self.user_auth_token)
        resp = self.client.get(url, params=merged)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected Qobuz response payload")
        return data

    def _resolve_track_id_for_isrc(self, isrc: str) -> str:
        data = self._request("track/search", {"query": isrc, "limit": 5})
        tracks = data.get("tracks", {})
        items = tracks.get("items") if isinstance(tracks, dict) else None
        if not isinstance(items, list):
            raise RuntimeError("Qobuz search returned no items")
        normalized = (isrc or "").strip().upper()
        for item in items:
            if not isinstance(item, dict):
                continue
            item_isrc = str(item.get("isrc") or "").strip().upper()
            if item_isrc == normalized:
                track_id = str(item.get("id") or "").strip()
                if track_id:
                    return track_id
        raise RuntimeError("Qobuz search did not return an exact ISRC match")

    def _get_download_url(self, track_id: str) -> tuple[str, str]:
        format_id = os.getenv("QOBUZ_FORMAT_ID", "27")
        data = self._request("track/getFileUrl", {"track_id": track_id, "format_id": format_id})
        url = str(data.get("url") or "").strip()
        if not url:
            raise RuntimeError("Qobuz did not return a download URL (track not purchased or unavailable)")
        if data.get("drm") is True or str(data.get("format") or "").lower() == "drm":
            raise RuntimeError("Qobuz returned a DRM-encumbered download; refusing")
        return url, str(data.get("mime_type") or "")

    def _download_to_file(self, url: str, dest_path: Path) -> None:
        with self.client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest_path, "wb") as handle:
                for chunk in resp.iter_bytes():
                    if chunk:
                        handle.write(chunk)

    def download_track(self, isrc: str, dest_dir: Path) -> DownloadResult:
        dest_dir.mkdir(parents=True, exist_ok=True)
        track_id = self._resolve_track_id_for_isrc(isrc)
        url, mime = self._get_download_url(track_id)
        ext = "flac" if "flac" in (mime or "").lower() else "bin"
        dest_path = dest_dir / f"qobuz_{track_id}.{ext}"
        self._download_to_file(url, dest_path)
        return DownloadResult(
            file_path=dest_path,
            provider=self.provider,
            provider_track_id=track_id,
            format=ext,
            download_source=self.download_source,
        )

    def download_release(self, release_id: str, dest_dir: Path) -> list[DownloadResult]:
        _ = release_id
        _ = dest_dir
        raise NotImplementedError("Qobuz purchase release download is not implemented in this PR")

