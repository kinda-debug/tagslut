from __future__ import annotations

import csv
import json
import re
import shutil
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import yaml  # type: ignore  # TODO: mypy-strict


DEFAULT_OVERLAY_CONFIG_PATH = Path("config/gig_overlay_rules.yaml")
DEFAULT_ENERGY_COMMENT_PATTERN = r"(?i)(\d{1,2})\s+Energy\b"
DEFAULT_UTILITY_TITLE_MARKERS = ("tool", "dub", "instrumental", "acapella", "intro", "outro")
DEFAULT_RECOGNITION_TITLE_MARKERS = ("edit", "rework", "bootleg", "remix", "live")
_PEAK_GENRE_HINTS = ("peak time", "techno", "trance", "hard", "mainstage")
_TRANSITION_GENRE_HINTS = ("deep", "organic", "melodic", "afro", "house")
_ADVENTUROUS_GENRE_HINTS = ("leftfield", "indie dance", "electro", "breaks", "balearic", "acid")
_SAFETY_NET_GENRE_HINTS = ("classic", "disco", "funk", "soul", "pop", "throwback")
_HEURISTIC_MIN_SUPPORT_SIGNALS = 2


@dataclass(frozen=True)
class OverlayStateStyle:
    rating: int
    colour_name: str | None
    colour_value: str | None
    priority: int = 0


@dataclass(frozen=True)
class OverlayHeuristicsConfig:
    preserve_existing_overlay: bool = True
    duration_min_seconds: int | None = 90
    duration_max_seconds: int | None = 720
    energy_comment_pattern: str = DEFAULT_ENERGY_COMMENT_PATTERN
    utility_title_markers: tuple[str, ...] = field(default_factory=lambda: DEFAULT_UTILITY_TITLE_MARKERS)
    recognition_title_markers: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_RECOGNITION_TITLE_MARKERS
    )


@dataclass(frozen=True)
class OverlayManualOverride:
    source: str
    track_id: str | None = None
    location: str | None = None
    artist: str | None = None
    title: str | None = None
    canonical_identity: str | None = None
    force_rating_set: bool = False
    force_rating: int | None = None
    force_colour_set: bool = False
    force_colour_name: str | None = None
    force_colour_value: str | None = None
    disable_auto: bool = False
    notes: str | None = None


@dataclass(frozen=True)
class OverlayConfig:
    palette: dict[str, str | None]
    state_styles: dict[str, OverlayStateStyle]
    playlist_state_hints: dict[str, str]
    manual_overrides: tuple[OverlayManualOverride, ...]
    recognition_artists: frozenset[str]
    recognition_titles: frozenset[str]
    never_peak_artists: frozenset[str]
    never_peak_titles: frozenset[str]
    utility_only_titles: frozenset[str]
    heuristics: OverlayHeuristicsConfig


@dataclass
class RekordboxTrackContext:
    track_id: str
    node: ET.Element
    artist: str
    title: str
    mix: str
    location_uri: str
    location_path: str
    genre: str
    comments: str
    bpm: float | None
    duration_seconds: int | None
    energy_comment: int | None
    current_rating_raw: str
    current_rating_value: int | None
    current_colour_raw: str
    canonical_identity: str
    matched_playlists: tuple[str, ...]


@dataclass(frozen=True)
class BaseOverlayDecision:
    state: str | None
    rating_raw: str
    colour_name: str | None
    colour_raw: str
    reason: str
    override_source: str = ""
    preserved_existing: bool = False


@dataclass(frozen=True)
class FinalOverlayDecision:
    state: str | None
    rating_raw: str
    colour_name: str | None
    colour_raw: str
    reason: str
    override_source: str = ""
    manual_override_applied: bool = False
    preserved_existing: bool = False


@dataclass(frozen=True)
class OverlayAuditRow:
    TrackID: str
    Artist: str
    Title: str
    Location: str
    old_rating: str
    new_rating: str
    old_colour: str
    new_colour: str
    matched_playlists: str
    parsed_energy_comment: str
    bpm: str
    genre: str
    decision_reason: str
    override_source: str
    chosen_state: str


@dataclass
class OverlayRunResult:
    input_xml: str
    output_xml: str
    backup_path: str = ""
    audit_csv_path: str = ""
    audit_json_path: str = ""
    tracks_scanned: int = 0
    tracks_changed: int = 0
    rating_changed: int = 0
    colour_changed: int = 0
    preserved_existing: int = 0
    manual_overrides_applied: int = 0
    dry_run: bool = False
    audit_rows: list[OverlayAuditRow] = field(default_factory=list)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value or "")
    collapsed = " ".join(normalized.strip().casefold().split())
    return collapsed


def _normalize_identifier(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _parse_location(location: str) -> str:
    if not location:
        return ""
    parsed = urlparse(location)
    if parsed.scheme != "file":
        return unquote(location)
    if parsed.netloc and parsed.netloc != "localhost":
        return unquote(f"//{parsed.netloc}{parsed.path}")
    return unquote(parsed.path)


def _normalize_pathlike(value: str) -> str:
    parsed = _parse_location(value)
    text = parsed if parsed else value
    return unicodedata.normalize("NFC", text).casefold().strip()


def _parse_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _canonical_rating_raw(value: object) -> str:
    parsed = _parse_int(value)
    if parsed is not None:
        return str(parsed)
    return str(value or "").strip()


def _normalize_colour_literal(value: object) -> str | None:
    if isinstance(value, int):
        if value < 0 or value > 0xFFFFFF:
            raise ValueError(f"Invalid Rekordbox colour value: {value!r}. Expected 0xRRGGBB or none.")
        return f"0x{value:06X}"

    text = str(value or "").strip()
    if not text or text.casefold() in {"none", "null"}:
        return None
    match = re.fullmatch(r"0x([0-9a-fA-F]{6})", text)
    if match is None:
        raise ValueError(f"Invalid Rekordbox colour value: {value!r}. Expected 0xRRGGBB or none.")
    return f"0x{match.group(1).upper()}"


def _resolve_colour_token(
    token: object,
    palette: dict[str, str | None],
) -> tuple[str | None, str | None]:
    if token is None:
        return None, None

    raw_text = str(token).strip()
    if not raw_text:
        return None, None

    normalized_text = _normalize_text(raw_text)
    if normalized_text in {"none", "null"}:
        return "none", None
    if normalized_text in palette:
        return normalized_text, palette[normalized_text]
    colour_value = _normalize_colour_literal(raw_text)
    return raw_text, colour_value


def _coerce_rating(value: object, *, label: str) -> int:
    parsed = _parse_int(value)
    if parsed is None or parsed < 0 or parsed > 5:
        raise ValueError(f"{label} must be an integer between 0 and 5.")
    return parsed


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    parsed = _parse_int(value)
    return parsed


def _canonical_identity(artist: str, title: str, mix: str) -> str:
    parts = [_normalize_text(artist), _normalize_text(title), _normalize_text(mix)]
    return "|".join(part for part in parts if part)


def _has_existing_overlay(track: RekordboxTrackContext) -> bool:
    return bool(track.current_colour_raw) or (track.current_rating_value is not None and track.current_rating_value > 0)


def _title_markers(title: str, markers: tuple[str, ...]) -> list[str]:
    normalized_title = _normalize_text(title)
    return [marker for marker in markers if marker in normalized_title]


def _matches_artist_list(artist: str, values: frozenset[str]) -> bool:
    normalized_artist = _normalize_text(artist)
    if not normalized_artist:
        return False
    return any(value in normalized_artist for value in values)


def _matches_title_list(title: str, values: frozenset[str]) -> bool:
    normalized_title = _normalize_text(title)
    if not normalized_title:
        return False
    return normalized_title in values


def _state_style(config: OverlayConfig, state: str) -> OverlayStateStyle:
    normalized_state = _normalize_text(state)
    style = config.state_styles.get(normalized_state)
    if style is None:
        raise ValueError(f"Overlay config references unknown state: {state!r}")
    return style


def _build_palette(raw_palette: object) -> dict[str, str | None]:
    palette: dict[str, str | None] = {"none": None}
    if not isinstance(raw_palette, dict):
        return palette
    for key, value in raw_palette.items():
        normalized_key = _normalize_text(str(key))
        palette[normalized_key] = _normalize_colour_literal(value)
    return palette


def load_gig_overlay_config(path: Path) -> OverlayConfig:
    raw_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_data, dict):
        raise ValueError(f"Overlay config must be a mapping: {path}")

    palette = _build_palette(raw_data.get("colour_palette"))

    raw_states = raw_data.get("state_defaults") or {}
    if not isinstance(raw_states, dict) or not raw_states:
        raise ValueError("Overlay config requires a non-empty state_defaults mapping.")

    state_styles: dict[str, OverlayStateStyle] = {}
    for raw_state, raw_style in raw_states.items():
        if not isinstance(raw_style, dict):
            raise ValueError(f"state_defaults.{raw_state} must be a mapping.")
        state_name = _normalize_text(str(raw_state))
        colour_name, colour_value = _resolve_colour_token(raw_style.get("colour"), palette)
        state_styles[state_name] = OverlayStateStyle(
            rating=_coerce_rating(raw_style.get("rating"), label=f"state_defaults.{raw_state}.rating"),
            colour_name=colour_name,
            colour_value=colour_value,
            priority=int(raw_style.get("priority", 0)),
        )

    raw_hints = raw_data.get("playlist_state_hints") or {}
    if not isinstance(raw_hints, dict):
        raise ValueError("playlist_state_hints must be a mapping.")
    playlist_state_hints: dict[str, str] = {}
    for raw_name, raw_state in raw_hints.items():
        normalized_name = _normalize_text(str(raw_name))
        normalized_state = _normalize_text(str(raw_state))
        if normalized_state not in state_styles:
            raise ValueError(f"playlist_state_hints references undefined state: {raw_state!r}")
        playlist_state_hints[normalized_name] = normalized_state

    raw_heuristics = raw_data.get("heuristics") or {}
    if not isinstance(raw_heuristics, dict):
        raise ValueError("heuristics must be a mapping if provided.")
    heuristics = OverlayHeuristicsConfig(
        preserve_existing_overlay=bool(raw_heuristics.get("preserve_existing_overlay", True)),
        duration_min_seconds=_coerce_optional_int(raw_heuristics.get("duration_min_seconds", 90)),
        duration_max_seconds=_coerce_optional_int(raw_heuristics.get("duration_max_seconds", 720)),
        energy_comment_pattern=str(
            raw_heuristics.get("energy_comment_pattern", DEFAULT_ENERGY_COMMENT_PATTERN)
        ),
        utility_title_markers=tuple(
            str(item).strip().casefold()
            for item in raw_heuristics.get("utility_title_markers", DEFAULT_UTILITY_TITLE_MARKERS)
            if str(item).strip()
        ),
        recognition_title_markers=tuple(
            str(item).strip().casefold()
            for item in raw_heuristics.get("recognition_title_markers", DEFAULT_RECOGNITION_TITLE_MARKERS)
            if str(item).strip()
        ),
    )

    raw_overrides = raw_data.get("manual_overrides") or []
    if not isinstance(raw_overrides, list):
        raise ValueError("manual_overrides must be a list if provided.")
    manual_overrides: list[OverlayManualOverride] = []
    for index, raw_override in enumerate(raw_overrides):
        if not isinstance(raw_override, dict):
            raise ValueError(f"manual_overrides[{index}] must be a mapping.")
        match_data = raw_override.get("match") or {}
        if not isinstance(match_data, dict):
            raise ValueError(f"manual_overrides[{index}].match must be a mapping.")

        track_id = _normalize_identifier(match_data.get("track_id") or raw_override.get("track_id"))
        location = _normalize_identifier(match_data.get("location") or raw_override.get("location"))
        artist = _normalize_text(str(match_data.get("artist") or raw_override.get("artist") or ""))
        title = _normalize_text(str(match_data.get("title") or raw_override.get("title") or ""))
        canonical_identity = _normalize_text(
            str(match_data.get("canonical_identity") or raw_override.get("canonical_identity") or "")
        )

        if not any((track_id, location, artist, title, canonical_identity)):
            raise ValueError(f"manual_overrides[{index}] requires at least one match field.")

        force_rating_set = "force_rating" in raw_override
        force_rating = (
            _coerce_rating(raw_override.get("force_rating"), label=f"manual_overrides[{index}].force_rating")
            if force_rating_set
            else None
        )
        force_colour_set = "force_colour" in raw_override
        force_colour_name, force_colour_value = (
            _resolve_colour_token(raw_override.get("force_colour"), palette)
            if force_colour_set
            else (None, None)
        )

        manual_overrides.append(
            OverlayManualOverride(
                source=f"manual_overrides[{index}]",
                track_id=track_id,
                location=location,
                artist=artist or None,
                title=title or None,
                canonical_identity=canonical_identity or None,
                force_rating_set=force_rating_set,
                force_rating=force_rating,
                force_colour_set=force_colour_set,
                force_colour_name=force_colour_name,
                force_colour_value=force_colour_value,
                disable_auto=bool(raw_override.get("disable_auto", False)),
                notes=_normalize_identifier(raw_override.get("notes")),
            )
        )

    def _load_string_set(key: str) -> frozenset[str]:
        values = raw_data.get(key) or []
        if not isinstance(values, list):
            raise ValueError(f"{key} must be a list if provided.")
        return frozenset(_normalize_text(str(item)) for item in values if str(item).strip())

    return OverlayConfig(
        palette=palette,
        state_styles=state_styles,
        playlist_state_hints=playlist_state_hints,
        manual_overrides=tuple(manual_overrides),
        recognition_artists=_load_string_set("recognition_artists"),
        recognition_titles=_load_string_set("recognition_titles"),
        never_peak_artists=_load_string_set("never_peak_artists"),
        never_peak_titles=_load_string_set("never_peak_titles"),
        utility_only_titles=_load_string_set("utility_only_titles"),
        heuristics=heuristics,
    )


def _collect_playlist_membership(root: ET.Element) -> dict[str, tuple[str, ...]]:
    membership: dict[str, list[str]] = defaultdict(list)
    playlists_node = root.find("PLAYLISTS")
    if playlists_node is None:
        return {}

    root_node = playlists_node.find("NODE")
    if root_node is None:
        return {}

    def _walk(node: ET.Element, prefix: tuple[str, ...]) -> None:
        node_type = str(node.attrib.get("Type") or "").strip()
        node_name = str(node.attrib.get("Name") or "").strip()
        next_prefix = prefix
        if node_name and node_name != "ROOT":
            next_prefix = prefix + (node_name,)

        if node_type == "1":
            playlist_name = "/".join(next_prefix) if next_prefix else node_name
            for track_ref in node.findall("TRACK"):
                track_id = str(track_ref.attrib.get("Key") or track_ref.attrib.get("TrackID") or "").strip()
                if track_id:
                    membership[track_id].append(playlist_name)
            return

        for child in node.findall("NODE"):
            _walk(child, next_prefix)

    _walk(root_node, ())
    return {track_id: tuple(paths) for track_id, paths in membership.items()}


def _energy_from_comments(comments: str, pattern: str) -> int | None:
    if not comments:
        return None
    match = re.search(pattern, comments)
    if match is None:
        return None
    return _parse_int(match.group(1))


def _load_track_contexts(root: ET.Element, config: OverlayConfig) -> list[RekordboxTrackContext]:
    collection = root.find("COLLECTION")
    if collection is None:
        raise ValueError("Rekordbox XML missing COLLECTION node.")

    membership = _collect_playlist_membership(root)
    contexts: list[RekordboxTrackContext] = []
    for track_node in collection.findall("TRACK"):
        track_id = _normalize_identifier(
            track_node.attrib.get("TrackID") or track_node.attrib.get("ID") or track_node.attrib.get("Key")
        )
        if track_id is None:
            raise ValueError("Encountered Rekordbox TRACK without TrackID/ID/Key.")

        artist = str(track_node.attrib.get("Artist") or "").strip()
        title = str(track_node.attrib.get("Name") or "").strip()
        mix = str(track_node.attrib.get("Mix") or track_node.attrib.get("Remix") or "").strip()
        location_uri = str(track_node.attrib.get("Location") or "").strip()
        location_path = _parse_location(location_uri)
        genre = str(track_node.attrib.get("Genre") or "").strip()
        comments = str(track_node.attrib.get("Comments") or "").strip()
        bpm = _parse_float(track_node.attrib.get("AverageBpm"))
        duration_seconds = _parse_int(track_node.attrib.get("TotalTime"))
        current_rating_raw = _canonical_rating_raw(track_node.attrib.get("Rating"))
        current_rating_value = _parse_int(current_rating_raw)
        if current_rating_value is not None and current_rating_value <= 0:
            current_rating_value = None
        current_colour_raw = _normalize_colour_literal(track_node.attrib.get("Colour")) or ""

        contexts.append(
            RekordboxTrackContext(
                track_id=track_id,
                node=track_node,
                artist=artist,
                title=title,
                mix=mix,
                location_uri=location_uri,
                location_path=location_path,
                genre=genre,
                comments=comments,
                bpm=bpm,
                duration_seconds=duration_seconds,
                energy_comment=_energy_from_comments(comments, config.heuristics.energy_comment_pattern),
                current_rating_raw=current_rating_raw,
                current_rating_value=current_rating_value,
                current_colour_raw=current_colour_raw,
                canonical_identity=_canonical_identity(artist, title, mix),
                matched_playlists=membership.get(track_id, ()),
            )
        )
    return contexts


def _select_manual_override(
    track: RekordboxTrackContext,
    config: OverlayConfig,
) -> OverlayManualOverride | None:
    track_artist = _normalize_text(track.artist)
    track_title = _normalize_text(track.title)
    raw_location = _normalize_pathlike(track.location_uri)
    file_location = _normalize_pathlike(track.location_path)

    for override in config.manual_overrides:
        if override.track_id is not None and override.track_id != track.track_id:
            continue
        if override.location is not None:
            override_location = _normalize_pathlike(override.location)
            if override_location not in {raw_location, file_location}:
                continue
        if override.artist is not None and override.artist != track_artist:
            continue
        if override.title is not None and override.title != track_title:
            continue
        if override.canonical_identity is not None and override.canonical_identity != track.canonical_identity:
            continue
        return override
    return None


def _base_decision_from_state(
    config: OverlayConfig,
    *,
    state: str,
    reason: str,
    override_source: str = "",
    preserved_existing: bool = False,
) -> BaseOverlayDecision:
    style = _state_style(config, state)
    return BaseOverlayDecision(
        state=_normalize_text(state),
        rating_raw=str(style.rating),
        colour_name=style.colour_name,
        colour_raw=style.colour_value or "",
        reason=reason,
        override_source=override_source,
        preserved_existing=preserved_existing,
    )


def _decide_curated_exception(
    track: RekordboxTrackContext,
    config: OverlayConfig,
) -> BaseOverlayDecision | None:
    if _matches_title_list(track.title, config.utility_only_titles):
        return _base_decision_from_state(
            config,
            state="utility",
            reason=f"curated exception: utility_only_titles matched {track.title!r}",
            override_source="utility_only_titles",
        )

    recognition_artist = _matches_artist_list(track.artist, config.recognition_artists)
    recognition_title = _matches_title_list(track.title, config.recognition_titles)
    if recognition_artist or recognition_title:
        reasons: list[str] = []
        if recognition_artist:
            reasons.append(f"recognition artist {track.artist!r}")
        if recognition_title:
            reasons.append(f"recognition title {track.title!r}")
        return _base_decision_from_state(
            config,
            state="wants_recognition",
            reason="curated exception: " + ", ".join(reasons),
            override_source="recognition_lists",
        )

    never_peak_artist = _matches_artist_list(track.artist, config.never_peak_artists)
    never_peak_title = _matches_title_list(track.title, config.never_peak_titles)
    if never_peak_artist or never_peak_title:
        reasons = []
        if never_peak_artist:
            reasons.append(f"never_peak artist {track.artist!r}")
        if never_peak_title:
            reasons.append(f"never_peak title {track.title!r}")
        return _base_decision_from_state(
            config,
            state="safety_net",
            reason="curated exception: " + ", ".join(reasons),
            override_source="never_peak_lists",
        )

    return None


def _playlist_hint_candidates(
    track: RekordboxTrackContext,
    config: OverlayConfig,
) -> list[tuple[str, str, OverlayStateStyle]]:
    candidates: list[tuple[str, str, OverlayStateStyle]] = []
    for playlist_path in track.matched_playlists:
        full_key = _normalize_text(playlist_path)
        leaf_key = _normalize_text(playlist_path.split("/")[-1])
        matched_state = config.playlist_state_hints.get(full_key)
        matched_name = playlist_path
        if matched_state is None:
            matched_state = config.playlist_state_hints.get(leaf_key)
            matched_name = playlist_path.split("/")[-1]
        if matched_state is None:
            continue
        candidates.append((playlist_path, matched_state, _state_style(config, matched_state)))
    return candidates


def _decide_playlist_hint(
    track: RekordboxTrackContext,
    config: OverlayConfig,
) -> BaseOverlayDecision | None:
    candidates = _playlist_hint_candidates(track, config)
    if not candidates:
        return None
    ordered = sorted(
        candidates,
        key=lambda item: (-item[2].priority, -item[2].rating, item[0].casefold()),
    )
    chosen_playlist, chosen_state, chosen_style = ordered[0]
    candidate_summary = ", ".join(
        f"{playlist}->{state}" for playlist, state, _style in ordered
    )
    return BaseOverlayDecision(
        state=chosen_state,
        rating_raw=str(chosen_style.rating),
        colour_name=chosen_style.colour_name,
        colour_raw=chosen_style.colour_value or "",
        reason=f"playlist hint: {chosen_playlist} -> {chosen_state} (candidates: {candidate_summary})",
        override_source="playlist_state_hints",
    )


def _genre_support(track: RekordboxTrackContext) -> tuple[str | None, str | None]:
    normalized_genre = _normalize_text(track.genre)
    if not normalized_genre:
        return None, None
    if any(marker in normalized_genre for marker in _PEAK_GENRE_HINTS):
        return "ready_for_peak", f"genre={track.genre!r}"
    if any(marker in normalized_genre for marker in _SAFETY_NET_GENRE_HINTS):
        return "safety_net", f"genre={track.genre!r}"
    if any(marker in normalized_genre for marker in _ADVENTUROUS_GENRE_HINTS):
        return "adventurous", f"genre={track.genre!r}"
    if any(marker in normalized_genre for marker in _TRANSITION_GENRE_HINTS):
        return "transition", f"genre={track.genre!r}"
    return None, None


def _add_state_support(
    score_map: dict[str, int],
    support_map: dict[str, set[str]],
    reason_map: dict[str, list[str]],
    *,
    state: str | None,
    signal_name: str,
    points: int,
    detail: str | None,
) -> None:
    if not state or points <= 0:
        return
    normalized_state = _normalize_text(state)
    score_map[normalized_state] = score_map.get(normalized_state, 0) + points
    support_map.setdefault(normalized_state, set()).add(signal_name)
    if detail:
        reason_map.setdefault(normalized_state, []).append(detail)


def _decide_heuristic_state(
    track: RekordboxTrackContext,
    config: OverlayConfig,
) -> BaseOverlayDecision | None:
    min_duration = config.heuristics.duration_min_seconds
    max_duration = config.heuristics.duration_max_seconds
    if track.duration_seconds is not None:
        if min_duration is not None and track.duration_seconds < min_duration:
            return None
        if max_duration is not None and track.duration_seconds > max_duration:
            return None

    score_map: dict[str, int] = {}
    support_map: dict[str, set[str]] = {}
    reason_map: dict[str, list[str]] = {}

    if track.energy_comment is not None:
        if track.energy_comment >= 11:
            _add_state_support(
                score_map,
                support_map,
                reason_map,
                state="late_night_open",
                signal_name="comment_energy",
                points=2,
                detail=f"comment_energy={track.energy_comment}",
            )
        elif track.energy_comment >= 9:
            _add_state_support(
                score_map,
                support_map,
                reason_map,
                state="ready_for_peak",
                signal_name="comment_energy",
                points=2,
                detail=f"comment_energy={track.energy_comment}",
            )
        elif track.energy_comment >= 7:
            _add_state_support(
                score_map,
                support_map,
                reason_map,
                state="locked_in",
                signal_name="comment_energy",
                points=2,
                detail=f"comment_energy={track.energy_comment}",
            )
        elif track.energy_comment >= 5:
            _add_state_support(
                score_map,
                support_map,
                reason_map,
                state="transition",
                signal_name="comment_energy",
                points=2,
                detail=f"comment_energy={track.energy_comment}",
            )
        else:
            _add_state_support(
                score_map,
                support_map,
                reason_map,
                state="arriving",
                signal_name="comment_energy",
                points=2,
                detail=f"comment_energy={track.energy_comment}",
            )

    if track.bpm is not None:
        if track.bpm >= 128:
            _add_state_support(
                score_map,
                support_map,
                reason_map,
                state="late_night_open",
                signal_name="bpm",
                points=1,
                detail=f"bpm={track.bpm:g}",
            )
        elif track.bpm >= 124:
            _add_state_support(
                score_map,
                support_map,
                reason_map,
                state="ready_for_peak",
                signal_name="bpm",
                points=1,
                detail=f"bpm={track.bpm:g}",
            )
        elif track.bpm >= 118:
            _add_state_support(
                score_map,
                support_map,
                reason_map,
                state="locked_in",
                signal_name="bpm",
                points=1,
                detail=f"bpm={track.bpm:g}",
            )
        elif track.bpm <= 112:
            _add_state_support(
                score_map,
                support_map,
                reason_map,
                state="arriving",
                signal_name="bpm",
                points=1,
                detail=f"bpm={track.bpm:g}",
            )
        else:
            _add_state_support(
                score_map,
                support_map,
                reason_map,
                state="transition",
                signal_name="bpm",
                points=1,
                detail=f"bpm={track.bpm:g}",
            )

    genre_state, genre_reason = _genre_support(track)
    _add_state_support(
        score_map,
        support_map,
        reason_map,
        state=genre_state,
        signal_name="genre",
        points=1,
        detail=genre_reason,
    )

    utility_markers = _title_markers(track.title, config.heuristics.utility_title_markers)
    if utility_markers:
        _add_state_support(
            score_map,
            support_map,
            reason_map,
            state="utility",
            signal_name="title_marker",
            points=2,
            detail=f"title_markers={','.join(utility_markers)}",
        )

    recognition_markers = _title_markers(track.title, config.heuristics.recognition_title_markers)
    if recognition_markers:
        _add_state_support(
            score_map,
            support_map,
            reason_map,
            state="wants_recognition",
            signal_name="title_marker",
            points=1,
            detail=f"title_markers={','.join(recognition_markers)}",
        )

    candidates: list[tuple[int, int, int, int, str]] = []
    for state_name, score in score_map.items():
        support_count = len(support_map.get(state_name, set()))
        if support_count < _HEURISTIC_MIN_SUPPORT_SIGNALS:
            continue
        style = _state_style(config, state_name)
        candidates.append((score, support_count, style.priority, style.rating, state_name))

    if not candidates:
        return None

    score, support_count, _priority, _rating, chosen_state = sorted(
        candidates,
        key=lambda item: (-item[0], -item[1], -item[2], -item[3], item[4]),
    )[0]
    return _base_decision_from_state(
        config,
        state=chosen_state,
        reason=(
            f"heuristic state: {chosen_state} from "
            f"{', '.join(reason_map.get(chosen_state, []))} "
            f"(score={score}, signals={support_count})"
        ),
        override_source="heuristics",
    )


def _decide_base_overlay(
    track: RekordboxTrackContext,
    config: OverlayConfig,
    manual_override: OverlayManualOverride | None,
) -> BaseOverlayDecision | None:
    if manual_override is not None and manual_override.disable_auto:
        return None

    if config.heuristics.preserve_existing_overlay and _has_existing_overlay(track):
        return BaseOverlayDecision(
            state=None,
            rating_raw=track.current_rating_raw,
            colour_name=None,
            colour_raw=track.current_colour_raw,
            reason="preserve existing overlay",
            override_source="existing_overlay",
            preserved_existing=True,
        )

    return (
        _decide_curated_exception(track, config)
        or _decide_playlist_hint(track, config)
        or _decide_heuristic_state(track, config)
    )


def _apply_manual_override(
    track: RekordboxTrackContext,
    base: BaseOverlayDecision | None,
    manual_override: OverlayManualOverride | None,
) -> FinalOverlayDecision:
    rating_raw = base.rating_raw if base is not None else track.current_rating_raw
    colour_name = base.colour_name if base is not None else None
    colour_raw = base.colour_raw if base is not None else track.current_colour_raw
    state = base.state if base is not None else None
    reason_parts: list[str] = []
    override_source = base.override_source if base is not None else ""
    preserved_existing = base.preserved_existing if base is not None else False
    manual_override_applied = False

    if base is not None and base.reason:
        reason_parts.append(base.reason)

    if manual_override is not None:
        if manual_override.disable_auto:
            reason_parts.append(f"{manual_override.source}: disable_auto")
            override_source = manual_override.source
            manual_override_applied = True
        if manual_override.force_rating_set:
            rating_raw = str(manual_override.force_rating or 0)
            reason_parts.append(f"{manual_override.source}: force_rating={rating_raw}")
            override_source = manual_override.source
            manual_override_applied = True
        if manual_override.force_colour_set:
            colour_name = manual_override.force_colour_name
            colour_raw = manual_override.force_colour_value or ""
            rendered_colour = manual_override.force_colour_name or manual_override.force_colour_value or "none"
            reason_parts.append(f"{manual_override.source}: force_colour={rendered_colour}")
            override_source = manual_override.source
            manual_override_applied = True
        if manual_override.notes:
            reason_parts.append(f"{manual_override.source}: {manual_override.notes}")

    return FinalOverlayDecision(
        state=state,
        rating_raw=rating_raw,
        colour_name=colour_name,
        colour_raw=colour_raw,
        reason="; ".join(reason_parts),
        override_source=override_source,
        manual_override_applied=manual_override_applied,
        preserved_existing=preserved_existing,
    )


def _display_colour(raw_value: str, reverse_palette: dict[str, str]) -> str:
    if not raw_value:
        return ""
    label = reverse_palette.get(raw_value)
    if label is None:
        return raw_value
    return f"{label} ({raw_value})"


def _format_bpm(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _apply_track_overlay(track: RekordboxTrackContext, decision: FinalOverlayDecision) -> None:
    if decision.rating_raw:
        track.node.attrib["Rating"] = decision.rating_raw
    elif "Rating" in track.node.attrib:
        del track.node.attrib["Rating"]

    if decision.colour_raw:
        track.node.attrib["Colour"] = decision.colour_raw
    elif "Colour" in track.node.attrib:
        del track.node.attrib["Colour"]


def _audit_row(
    track: RekordboxTrackContext,
    decision: FinalOverlayDecision,
    reverse_palette: dict[str, str],
) -> OverlayAuditRow:
    return OverlayAuditRow(
        TrackID=track.track_id,
        Artist=track.artist,
        Title=track.title,
        Location=track.location_path or track.location_uri,
        old_rating=track.current_rating_raw,
        new_rating=decision.rating_raw,
        old_colour=_display_colour(track.current_colour_raw, reverse_palette),
        new_colour=_display_colour(decision.colour_raw, reverse_palette),
        matched_playlists="; ".join(track.matched_playlists),
        parsed_energy_comment=str(track.energy_comment or ""),
        bpm=_format_bpm(track.bpm),
        genre=track.genre,
        decision_reason=decision.reason,
        override_source=decision.override_source,
        chosen_state=decision.state or "",
    )


def _indent(elem: ET.Element, level: int = 0) -> None:
    indent = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "  "
        for child in elem:
            _indent(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent + "  "
        if not elem[-1].tail or not elem[-1].tail.strip():
            elem[-1].tail = indent
    elif level and (not elem.tail or not elem.tail.strip()):
        elem.tail = indent


def _backup_output(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup_path = path.with_suffix(path.suffix + ".bak")
    counter = 1
    while backup_path.exists():
        backup_path = path.with_suffix(path.suffix + f".bak{counter}")
        counter += 1
    shutil.copy2(path, backup_path)
    return backup_path


def _write_audit_csv(path: Path, rows: list[OverlayAuditRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(OverlayAuditRow.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def _write_audit_json(path: Path, result: OverlayRunResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "input_xml": result.input_xml,
        "output_xml": result.output_xml,
        "backup_path": result.backup_path,
        "audit_csv_path": result.audit_csv_path,
        "audit_json_path": result.audit_json_path,
        "tracks_scanned": result.tracks_scanned,
        "tracks_changed": result.tracks_changed,
        "rating_changed": result.rating_changed,
        "colour_changed": result.colour_changed,
        "preserved_existing": result.preserved_existing,
        "manual_overrides_applied": result.manual_overrides_applied,
        "dry_run": result.dry_run,
        "changed_tracks": [asdict(row) for row in result.audit_rows],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def apply_rekordbox_overlay(
    *,
    input_xml: Path,
    output_xml: Path,
    config_path: Path = DEFAULT_OVERLAY_CONFIG_PATH,
    audit_csv_path: Path | None = None,
    audit_json_path: Path | None = None,
    backup_existing: bool = True,
    dry_run: bool = False,
) -> OverlayRunResult:
    config = load_gig_overlay_config(config_path)
    tree = ET.parse(input_xml)
    root = tree.getroot()
    tracks = _load_track_contexts(root, config)
    reverse_palette = {
        value: key for key, value in config.palette.items() if key != "none" and value is not None
    }

    result = OverlayRunResult(
        input_xml=str(input_xml),
        output_xml=str(output_xml),
        audit_csv_path=str(audit_csv_path) if audit_csv_path is not None else "",
        audit_json_path=str(audit_json_path) if audit_json_path is not None else "",
        tracks_scanned=len(tracks),
        dry_run=dry_run,
    )

    for track in tracks:
        manual_override = _select_manual_override(track, config)
        base = _decide_base_overlay(track, config, manual_override)
        decision = _apply_manual_override(track, base, manual_override)

        rating_changed = decision.rating_raw != track.current_rating_raw
        colour_changed = decision.colour_raw != track.current_colour_raw
        if not rating_changed and not colour_changed:
            if decision.preserved_existing:
                result.preserved_existing += 1
            continue

        _apply_track_overlay(track, decision)
        result.tracks_changed += 1
        if rating_changed:
            result.rating_changed += 1
        if colour_changed:
            result.colour_changed += 1
        if decision.preserved_existing:
            result.preserved_existing += 1
        if decision.manual_override_applied:
            result.manual_overrides_applied += 1
        result.audit_rows.append(_audit_row(track, decision, reverse_palette))

    if not dry_run:
        _indent(root)
        backup_path = _backup_output(output_xml) if backup_existing else None
        output_xml.parent.mkdir(parents=True, exist_ok=True)
        tree.write(output_xml, encoding="utf-8", xml_declaration=True)
        result.backup_path = str(backup_path) if backup_path is not None else ""

    if audit_csv_path is not None:
        _write_audit_csv(audit_csv_path, result.audit_rows)
    if audit_json_path is not None:
        _write_audit_json(audit_json_path, result)

    return result
