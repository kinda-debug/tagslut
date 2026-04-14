from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import string
from typing import Literal

ProviderName = Literal["tidal", "qobuz", "amazon", "apple", "deezer", "unknown"]


@dataclass
class SpotiflacTrack:
    display_title: str  # "Track - Artists" as logged by SpotiFLAC
    isrc: str | None  # from qobuz error line
    provider: ProviderName  # which provider delivered the file
    file_path: Path | None  # resolved absolute path from M3U8
    failed: bool
    failure_reason: str | None
    spotify_id: str | None = None
    qobuz_album_id: str | None = None
    tidal_album_id: str | None = None
    album_source_url: str | None = None


_LOG_LINE_RE = re.compile(r"^\[(?P<ts>\d{2}:\d{2}:\d{2})\]\s+\[(?P<level>\w+)\]\s+(?P<msg>.*)$")
_TRYING_RE = re.compile(r"^(?:direct\s+link:\s*)?trying\s+(?P<provider>\w+)\s+for:\s+(?P<title>.+)$", re.IGNORECASE)
_DOWNLOADED_RE = re.compile(r"^downloaded:\s+(?P<title>.+)$", re.IGNORECASE)
_FAILED_RE = re.compile(r"^failed:\s+(?P<title>.+)$", re.IGNORECASE)
_PROVIDER_SUCCESS_RE = re.compile(
    r"^(?:direct\s+link\s+)?(?P<provider>tidal|qobuz|amazon|apple|deezer):\s+(?P<title>.+)$",
    re.IGNORECASE,
)
_PROVIDER_ERROR_RE = re.compile(r"^(?P<provider>tidal|qobuz|amazon|apple|deezer)\s+error:\s+(?P<reason>.+)$", re.IGNORECASE)
_QOBUZ_ISRC_RE = re.compile(r"\bISRC:\s*(?P<isrc>[A-Z]{2}[A-Z0-9]{3}\d{2}\d{5})\b", re.IGNORECASE)
_NEXT_SUCCESS_RE = re.compile(r"^\[SUCCESS\]\s+(?P<title>.+)$")
_NEXT_FAILED_HEADER_RE = re.compile(r"^\d+\.\s+(?P<title>.+)$")
_NEXT_ERROR_RE = re.compile(r"^Error:\s*(?P<err>.+)$")
_NEXT_ID_RE = re.compile(r"^ID:\s*(?P<id>\S+)\s*$")
_NEXT_PROVIDER_TOKEN_RE = re.compile(r"^\[(?P<label>[^\]]+)\]\s*(?P<reason>.+)$")
_SPOTIFY_ALBUM_URL_RE = re.compile(r"https?://open\.spotify\.com/album/(?P<id>[A-Za-z0-9]+)", re.IGNORECASE)
_QOBUZ_ALBUM_URL_RE = re.compile(r"https?://open\.qobuz\.com/album/(?P<id>[A-Za-z0-9]+)", re.IGNORECASE)
_TIDAL_ALBUM_URL_RE = re.compile(r"https?://(?:listen\.)?tidal\.com/album/(?P<id>\d+)", re.IGNORECASE)


def _coerce_provider(value: str | None) -> ProviderName:
    lowered = (value or "").strip().lower()
    if lowered in ("tidal", "qobuz", "amazon", "apple", "deezer"):
        return lowered  # type: ignore[return-value]
    return "unknown"


def _norm_match_key(text: str) -> str:
    lowered = (text or "").lower()
    lowered = lowered.translate(str.maketrans({ch: " " for ch in string.punctuation}))
    lowered = re.sub(r"[^a-z0-9\s]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _detect_format(log_path: Path) -> Literal["legacy", "next"]:
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Download Report"):
            return "next"
        return "legacy"
    return "legacy"


def _strip_next_playlist_suffix(title: str) -> str:
    stripped = title.rstrip()
    if not stripped.endswith(")"):
        return stripped

    depth = 0
    for idx in range(len(stripped) - 1, -1, -1):
        char = stripped[idx]
        if char == ")":
            depth += 1
            continue
        if char != "(":
            continue

        depth -= 1
        if depth != 0 or idx == 0 or stripped[idx - 1] != " ":
            continue

        suffix = stripped[idx + 1 : -1].strip()
        if suffix and suffix[0].isupper():
            return stripped[: idx - 1].rstrip()
        return stripped

    return stripped


def _coerce_next_provider(value: str | None) -> ProviderName:
    lowered = (value or "").strip().lower()
    if "apple" in lowered:
        return "apple"
    if "amazon" in lowered:
        return "amazon"
    if "deezer" in lowered:
        return "deezer"
    if "qobuz" in lowered:
        return "qobuz"
    if "tidal" in lowered:
        return "tidal"
    return "unknown"


def _provider_from_next_error(error: str) -> ProviderName:
    for token in error.split("|"):
        part = token.strip()
        if not part:
            continue
        match = _NEXT_PROVIDER_TOKEN_RE.match(part)
        if not match:
            continue
        reason = (match.group("reason") or "").strip().lower()
        if "track not found" in reason or "not available" in reason:
            continue
        return _coerce_next_provider(match.group("label"))
    return "unknown"


def parse_log_next(log_path: Path) -> list[SpotiflacTrack]:
    tracks: list[SpotiflacTrack] = []
    current_failed: SpotiflacTrack | None = None

    def _flush_failed() -> None:
        nonlocal current_failed
        if current_failed is not None:
            tracks.append(current_failed)
            current_failed = None

    for raw in log_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Download Report") or set(line) == {"-"}:
            continue

        success_m = _NEXT_SUCCESS_RE.match(line)
        if success_m:
            _flush_failed()
            title = (success_m.group("title") or "").strip()
            if not title:
                continue
            tracks.append(
                SpotiflacTrack(
                    display_title=title,
                    isrc=None,
                    provider="unknown",
                    file_path=None,
                    failed=False,
                    failure_reason=None,
                )
            )
            continue

        failed_m = _NEXT_FAILED_HEADER_RE.match(line)
        if failed_m:
            _flush_failed()
            title = _strip_next_playlist_suffix((failed_m.group("title") or "").strip())
            if not title:
                continue
            current_failed = SpotiflacTrack(
                display_title=title,
                isrc=None,
                provider="unknown",
                file_path=None,
                failed=True,
                failure_reason=None,
            )
            continue

        if current_failed is None:
            continue

        error_m = _NEXT_ERROR_RE.match(line)
        if error_m:
            error = (error_m.group("err") or "").strip()
            if not error:
                continue
            current_failed.failure_reason = error
            current_failed.provider = _provider_from_next_error(error)
            isrc_m = _QOBUZ_ISRC_RE.search(error)
            if isrc_m:
                current_failed.isrc = isrc_m.group("isrc").upper()
            continue

        id_m = _NEXT_ID_RE.match(line)
        if id_m:
            current_failed.spotify_id = (id_m.group("id") or "").strip() or None

    _flush_failed()
    return tracks


def _find_next_m3u8(log_path: Path) -> Path | None:
    candidates = sorted(
        path
        for path in log_path.parent.glob("*.m3u8")
        if not path.name.endswith("_converted.m3u8")
    )
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    norm_log_stem = _norm_match_key(log_path.stem)
    matches: list[tuple[int, str, Path]] = []
    for path in candidates:
        norm_stem = _norm_match_key(path.stem)
        if not norm_log_stem or not norm_stem:
            continue
        if norm_stem == norm_log_stem:
            return path
        if norm_stem in norm_log_stem or norm_log_stem in norm_stem:
            matches.append((abs(len(norm_log_stem) - len(norm_stem)), path.name, path))

    if matches:
        matches.sort()
        return matches[0][2]
    return candidates[0]


def parse_log(log_path: Path) -> list[SpotiflacTrack]:
    tracks: dict[str, SpotiflacTrack] = {}
    order: list[str] = []

    buffered_isrc: str | None = None
    current_title: str | None = None
    last_error_by_title: dict[str, str] = {}
    current_album_source_url: str | None = None
    current_spotify_album_id: str | None = None
    current_qobuz_album_id: str | None = None
    current_tidal_album_id: str | None = None

    for raw in log_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue

        m = _LOG_LINE_RE.match(line)
        if not m:
            continue
        msg = (m.group("msg") or "").strip()

        if msg.lower().startswith("url:"):
            url = msg.split(":", 1)[1].strip()
            current_album_source_url = url or None
            current_spotify_album_id = None
            current_qobuz_album_id = None
            current_tidal_album_id = None
            if current_album_source_url:
                spotify_m = _SPOTIFY_ALBUM_URL_RE.search(current_album_source_url)
                qobuz_m = _QOBUZ_ALBUM_URL_RE.search(current_album_source_url)
                tidal_m = _TIDAL_ALBUM_URL_RE.search(current_album_source_url)
                if spotify_m:
                    current_spotify_album_id = spotify_m.group("id")
                elif qobuz_m:
                    current_qobuz_album_id = qobuz_m.group("id")
                elif tidal_m:
                    current_tidal_album_id = tidal_m.group("id")
            continue

        isrc_m = _QOBUZ_ISRC_RE.search(msg)
        if isrc_m and "qobuz error" in msg.lower():
            buffered_isrc = isrc_m.group("isrc").upper()
            continue

        trying_m = _TRYING_RE.match(msg)
        if trying_m:
            provider = _coerce_provider(trying_m.group("provider"))
            title = (trying_m.group("title") or "").strip()
            if not title:
                continue
            current_title = title
            track = tracks.get(title)
            if track is None:
                track = SpotiflacTrack(
                    display_title=title,
                    isrc=buffered_isrc,
                    provider=provider,
                    file_path=None,
                    failed=False,
                    failure_reason=None,
                    spotify_id=current_spotify_album_id,
                    qobuz_album_id=current_qobuz_album_id,
                    tidal_album_id=current_tidal_album_id,
                    album_source_url=current_album_source_url,
                )
                tracks[title] = track
                order.append(title)
            else:
                track.provider = provider
                if buffered_isrc and not track.isrc:
                    track.isrc = buffered_isrc
            buffered_isrc = None
            continue

        provider_ok_m = _PROVIDER_SUCCESS_RE.match(msg)
        if provider_ok_m:
            provider = _coerce_provider(provider_ok_m.group("provider"))
            title = (provider_ok_m.group("title") or "").strip()
            if not title:
                continue
            track = tracks.get(title)
            if track is None:
                track = SpotiflacTrack(
                    display_title=title,
                    isrc=None,
                    provider=provider,
                    file_path=None,
                    failed=False,
                    failure_reason=None,
                    spotify_id=current_spotify_album_id,
                    qobuz_album_id=current_qobuz_album_id,
                    tidal_album_id=current_tidal_album_id,
                    album_source_url=current_album_source_url,
                )
                tracks[title] = track
                order.append(title)
            else:
                track.provider = provider
            continue

        downloaded_m = _DOWNLOADED_RE.match(msg)
        if downloaded_m:
            title = (downloaded_m.group("title") or "").strip()
            if not title:
                continue
            track = tracks.get(title)
            if track is None:
                track = SpotiflacTrack(
                    display_title=title,
                    isrc=None,
                    provider="unknown",
                    file_path=None,
                    failed=False,
                    failure_reason=None,
                    spotify_id=current_spotify_album_id,
                    qobuz_album_id=current_qobuz_album_id,
                    tidal_album_id=current_tidal_album_id,
                    album_source_url=current_album_source_url,
                )
                tracks[title] = track
                order.append(title)
            track.failed = False
            continue

        provider_err_m = _PROVIDER_ERROR_RE.match(msg)
        if provider_err_m and current_title:
            reason = (provider_err_m.group("reason") or "").strip()
            if reason:
                last_error_by_title[current_title] = reason
            continue

        failed_m = _FAILED_RE.match(msg)
        if failed_m:
            title = (failed_m.group("title") or "").strip()
            if not title:
                continue
            track = tracks.get(title)
            if track is None:
                track = SpotiflacTrack(
                    display_title=title,
                    isrc=None,
                    provider="unknown",
                    file_path=None,
                    failed=True,
                    failure_reason=None,
                    spotify_id=current_spotify_album_id,
                    qobuz_album_id=current_qobuz_album_id,
                    tidal_album_id=current_tidal_album_id,
                    album_source_url=current_album_source_url,
                )
                tracks[title] = track
                order.append(title)
            track.failed = True
            if title in last_error_by_title and not track.failure_reason:
                track.failure_reason = last_error_by_title[title]
            continue

    return [tracks[title] for title in order]


def parse_m3u8(m3u8_path: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    base = m3u8_path.parent

    for raw in m3u8_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rel = line
        while rel.startswith("../"):
            rel = rel[3:]
        resolved = base / rel
        try:
            resolved = resolved.resolve(strict=False)
        except TypeError:
            resolved = resolved.resolve()
        stem = Path(rel).stem
        if stem:
            out[stem] = resolved
    return out


def parse_failed_report(failed_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    current_title: str | None = None
    current_error: list[str] = []

    def _flush() -> None:
        nonlocal current_title, current_error
        if current_title and current_error:
            out[current_title] = " ".join(part.strip() for part in current_error if part.strip())
        current_title = None
        current_error = []

    for raw in failed_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue

        header_m = re.match(r"^\s*\d+\.\s+(?P<title>.+?)\s*$", line)
        if header_m:
            _flush()
            title = (header_m.group("title") or "").strip()
            title = re.sub(r"\s+\([^)]*\)\s*$", "", title).strip()
            current_title = title or None
            continue

        if current_title is None:
            continue

        err_m = re.match(r"^\s*Error:\s*(?P<err>.+?)\s*$", line)
        if err_m:
            current_error.append((err_m.group("err") or "").strip())
            continue

        if line.startswith(" "):
            current_error.append(line.strip())

    _flush()
    return out


def _resolve_file_paths(
    tracks: list[SpotiflacTrack],
    stem_map: dict[str, Path],
    norm_stem_map: dict[str, Path],
) -> None:
    """Mutate track.file_path in-place using exact then normalised stem matching."""
    for track in tracks:
        exact = stem_map.get(track.display_title)
        if exact is not None:
            track.file_path = exact
            continue

        norm_key = _norm_match_key(track.display_title)
        if norm_key in norm_stem_map:
            track.file_path = norm_stem_map[norm_key]


def build_manifest(
    log_path: Path,
    m3u8_path: Path | None = None,
    failed_path: Path | None = None,
) -> list[SpotiflacTrack]:
    log_path = Path(log_path).expanduser().resolve()
    log_format = _detect_format(log_path)

    if log_format == "next":
        if m3u8_path is None:
            m3u8_path = _find_next_m3u8(log_path)
        tracks = parse_log_next(log_path)
        failed_map: dict[str, str] = {}
    else:
        if failed_path is None:
            candidate_failed = log_path.with_name(f"{log_path.stem}_Failed{log_path.suffix}")
            if candidate_failed.exists():
                failed_path = candidate_failed

        if m3u8_path is None:
            candidate_m3u8 = log_path.with_suffix(".m3u8")
            if candidate_m3u8.exists():
                m3u8_path = candidate_m3u8
            else:
                siblings = list(log_path.parent.glob(f"{log_path.stem}*.m3u8"))
                if len(siblings) == 1:
                    m3u8_path = siblings[0]

        tracks = parse_log(log_path)
        failed_map = (
            parse_failed_report(failed_path) if failed_path and failed_path.exists() else {}
        )
        for track in tracks:
            if track.display_title in failed_map:
                track.failure_reason = failed_map[track.display_title]
                track.failed = True

    stem_map = parse_m3u8(m3u8_path) if m3u8_path and m3u8_path.exists() else {}

    norm_stem_map: dict[str, Path] = {}
    for stem, path in stem_map.items():
        key = _norm_match_key(stem)
        if key and key not in norm_stem_map:
            norm_stem_map[key] = path

    _resolve_file_paths(tracks, stem_map, norm_stem_map)
    return tracks


def classify_failure_reason(reason: str | None) -> Literal["retryable", "unavailable", "unknown"]:
    text = (reason or "").strip().lower()
    if not text:
        return "unknown"
    if "permission denied" in text or "input/output error" in text:
        return "retryable"
    if "track not found" in text:
        return "unavailable"
    return "unknown"
