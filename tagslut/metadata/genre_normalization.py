"""
Shared genre/style normalization logic.

Centralizes genre tag extraction, normalization, and cascading rules
to ensure consistency across enrichment and tagging workflows.

This module provides a single source of truth for genre processing used by:
- normalize_genres.py: DB backfill workflow
- tag_normalized_genres.py: In-place tagging workflow
- Metadata enrichment pipeline (future integration)

Usage Example:
    >>> from pathlib import Path
    >>> from tagslut.metadata.genre_normalization import GenreNormalizer
    >>>
    >>> # Create normalizer with rules
    >>> normalizer = GenreNormalizer(Path("tools/rules/genre_normalization.json"))
    >>>
    >>> # Extract and normalize from tags
    >>> genre, style, dropped = normalizer.choose_normalized(audio.tags)
    >>>
    >>> # Apply to file
    >>> normalizer.apply_tags_to_file(audio, genre, style)
    >>> audio.save()

Tag Hierarchy (Cascade Priority):
    1. GENRE_PREFERRED (explicit preference signal)
    2. SUBGENRE (secondary hint)
    3. GENRE (primary tag)
    4. GENRE_FULL (full hierarchical tag like "House | Deep House")

Output Format (Beatport-compatible):
    - GENRE: Primary genre (e.g., "House")
    - SUBGENRE: Style/sub-genre (e.g., "Deep House")
    - GENRE_PREFERRED: Preferred for cascading (style if present, else genre)
    - GENRE_FULL: Hierarchical "genre | style"
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "tools" / "rules" / "genre_normalization.json"

DEFAULT_CANONICAL_GENRES = frozenset({
    "140 / Deep Dubstep / Grime",
    "Afro House",
    "African",
    "Alternative / Indie",
    "Amapiano",
    "Ambient / Experimental",
    "Bass / Club",
    "Bass House",
    "Blues",
    "Brazilian Funk",
    "Breaks / Breakbeat / UK Bass",
    "Caribbean",
    "Classical",
    "Country",
    "Dance / Pop",
    "Deep House",
    "Disco",
    "DJ Tools",
    "Downtempo",
    "Drum & Bass",
    "Dubstep",
    "Electro (Classic / Detroit / Modern)",
    "Electronica",
    "Funky House",
    "Hard Dance / Hardcore / Neo Rave",
    "Hard Techno",
    "Hip-Hop",
    "Holiday",
    "House",
    "Indie Dance",
    "Jackin House",
    "Jazz",
    "Latin",
    "Mainstage",
    "Melodic House & Techno",
    "Minimal / Deep Tech",
    "Nu Disco / Disco",
    "Organic House",
    "Other",
    "Pop",
    "Progressive House",
    "Psy-Trance",
    "R&B",
    "Rock",
    "Soul",
    "Soundtrack",
    "Tech House",
    "Techno",
    "Techno (Peak Time / Driving)",
    "Techno (Raw / Deep / Hypnotic)",
    "Trance",
    "Trance (Main Floor)",
    "Trance (Raw / Deep / Hypnotic)",
    "Trap / Future Bass",
    "UK Garage / Bassline",
    "World",
})

DEFAULT_STYLE_PARENT_MAP = {
    "2-Step": "UK Garage / Bassline",
    "3Step": "Afro House",
    "Acapellas": "DJ Tools",
    "Acid": "Techno (Raw / Deep / Hypnotic)",
    "Afro / Latin": "Afro House",
    "Afro Melodic": "Afro House",
    "Afrobeats": "African",
    "Bassline": "UK Garage / Bassline",
    "Battle Tools": "DJ Tools",
    "Big Room": "Mainstage",
    "Breakbeat": "Breaks / Breakbeat / UK Bass",
    "Broken": "Breaks / Breakbeat / UK Bass",
    "Dancehall": "Caribbean",
    "Dark & Forest": "Drum & Bass",
    "Dark Disco": "Indie Dance",
    "Deep": "Deep House",
    "Deep / Hypnotic": "Techno (Raw / Deep / Hypnotic)",
    "Deep House": "Deep House",
    "Deep Tech": "Minimal / Deep Tech",
    "Deep Trance": "Trance (Raw / Deep / Hypnotic)",
    "Disco": "Nu Disco / Disco",
    "Driving": "Techno (Peak Time / Driving)",
    "Dub": "Dubstep",
    "EBM": "Indie Dance",
    "Electro House": "Mainstage",
    "Electronica": "Electronica",
    "Frenchcore": "Hard Dance / Hardcore / Neo Rave",
    "Full-On": "Psy-Trance",
    "Funk": "Soul",
    "Future Bass": "Trap / Future Bass",
    "Future House": "House",
    "Future Rave": "Mainstage",
    "Glitch Hop": "Bass / Club",
    "Global": "World",
    "Global Club": "Bass / Club",
    "Goa Trance": "Psy-Trance",
    "Grime": "140 / Deep Dubstep / Grime",
    "Halftime": "Drum & Bass",
    "Hard House": "Hard Dance / Hardcore / Neo Rave",
    "Hard Trance": "Trance (Main Floor)",
    "Hardstyle": "Hard Dance / Hardcore / Neo Rave",
    "House": "House",
    "Hypnotic Trance": "Trance (Raw / Deep / Hypnotic)",
    "Indie": "Alternative / Indie",
    "Italo": "Nu Disco / Disco",
    "Jersey Club": "Bass / Club",
    "Juke / Footwork": "Bass / Club",
    "Jump Up": "Drum & Bass",
    "Jungle": "Drum & Bass",
    "Latin Dance": "Latin",
    "Latin House": "House",
    "Liquid": "Drum & Bass",
    "Loops": "DJ Tools",
    "Melodic Dubstep": "Dubstep",
    "Melodic House": "Melodic House & Techno",
    "Melodic House & Techno": "Melodic House & Techno",
    "Melodic Techno": "Melodic House & Techno",
    "Minimal / Deep Tech": "Minimal / Deep Tech",
    "Minimal House": "Minimal / Deep Tech",
    "Neo Rave": "Hard Dance / Hardcore / Neo Rave",
    "Nu Disco / Disco": "Nu Disco / Disco",
    "Peak Time": "Techno (Peak Time / Driving)",
    "Progressive Psy": "Psy-Trance",
    "Progressive Trance": "Trance (Main Floor)",
    "Psy-Techno": "Psy-Trance",
    "Psychedelic": "Psy-Trance",
    "Raw": "Techno (Raw / Deep / Hypnotic)",
    "Raw Trance": "Trance (Raw / Deep / Hypnotic)",
    "Reggae / Dancehall": "Caribbean",
    "Soulful": "House",
    "Speed Garage": "UK Garage / Bassline",
    "Speed House": "House",
    "Tech House": "Tech House",
    "Tech Trance": "Trance (Main Floor)",
    "Techno": "Techno",
    "Trap": "Trap / Future Bass",
    "UK Bass": "Breaks / Breakbeat / UK Bass",
    "UK Funky": "UK Garage / Bassline",
    "UK Garage": "UK Garage / Bassline",
    "Uplifting Trance": "Trance (Main Floor)",
    "Vocal Trance": "Trance (Main Floor)",
}

_DEFAULT_NORMALIZER: "GenreNormalizer | None" = None


def default_genre_normalizer() -> "GenreNormalizer":
    global _DEFAULT_NORMALIZER
    if _DEFAULT_NORMALIZER is None:
        rules_path = DEFAULT_RULES_PATH if DEFAULT_RULES_PATH.exists() else None
        _DEFAULT_NORMALIZER = GenreNormalizer(rules_path)
    return _DEFAULT_NORMALIZER


class GenreNormalizer:
    """
    Centralized genre/style normalization with support for multiple tag hierarchies.

    Supports cascading fallback order:
    1. GENRE_PREFERRED (explicit preference)
    2. SUBGENRE (secondary hint)
    3. GENRE (primary tag)
    4. GENRE_FULL (full hierarchical tag)

    Normalizes values via pluggable mapping rules JSON.
    """

    # Canonical tag keys by priority for genre selection
    GENRE_TAG_KEYS = ["GENRE_PREFERRED", "SUBGENRE", "GENRE", "GENRE_FULL"]
    STYLE_TAG_KEYS = ["STYLE"]

    PROTECTED_COMPOUND = {
        "140 / deep dubstep / grime",
        "ambient / experimental",
        "bass / club",
        "breaks / breakbeat / uk bass",
        "dance / pop",
        "drum & bass",
        "electro (classic / detroit / modern)",
        "hard dance / hardcore / neo rave",
        "melodic house & techno",
        "minimal / deep tech",
        "nu disco / disco",
        "psy-trance",
        "techno (peak time / driving)",
        "techno (raw / deep / hypnotic)",
        "trance (main floor)",
        "trance (raw / deep / hypnotic)",
        "trap / future bass",
        "uk garage / bassline",
    }

    def __init__(self, rules_path: Optional[Path] = None):
        """
        Initialize normalizer with optional rules file.

        Args:
            rules_path: Path to genre normalization rules JSON.
                       If None, no normalization is applied (pass-through).
        """
        self.rules = self._load_rules(rules_path) if rules_path else {}
        self.canonical_genres = set(DEFAULT_CANONICAL_GENRES)
        self.canonical_genres.update(self.rules.get("canonical_genres", []))
        self.style_parent_map = dict(DEFAULT_STYLE_PARENT_MAP)
        self.style_parent_map.update(self.rules.get("style_parent_map", {}))
        self.fallback_genre = str(self.rules.get("fallback_genre") or "Other")

    @staticmethod
    def _load_rules(path: Path) -> Dict[str, Any]:
        """Load genre/style mapping rules from JSON."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "genre_map": data.get("genre_map", {}),
                "style_map": data.get("style_map", {}),
                "canonical_genres": data.get("canonical_genres", []),
                "style_parent_map": data.get("style_parent_map", {}),
                "fallback_genre": data.get("fallback_genre", "Other"),
            }
        except Exception as e:
            raise ValueError(f"Failed to load rules from {path}: {e}") from e

    @staticmethod
    def get_tag(tags: Dict[str, Any], key: str) -> List[str]:
        """
        Extract tag values as normalized list of strings.

        Args:
            tags: Metadata tags dict (from mutagen or similar)
            key: Tag key to extract

        Returns:
            List of tag values (empty if not present or empty)
        """
        if key in tags:
            val = tags[key]
            if isinstance(val, (list, tuple)):
                return [str(v).strip() for v in val if str(v).strip()]
            return [str(val).strip()] if str(val).strip() else []
        return []

    def normalize_value(self, value: str, mapping_type: str = "genre") -> str:
        """
        Normalize a single value using rules.

        Args:
            value: Raw tag value
            mapping_type: "genre" or "style" to select which mapping to use

        Returns:
            Normalized value (or original if no mapping found)
        """
        if not self.rules:
            return value
        mapping = self.rules.get(f"{mapping_type}_map", {})
        mapped = self._lookup_mapping(mapping, value)
        return mapped if mapped is not None else value

    @staticmethod
    def _normalize_spacing(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip())

    @classmethod
    def _lookup_key(cls, value: str) -> str:
        return cls._normalize_spacing(value).casefold()

    @classmethod
    def _lookup_mapping(cls, mapping: Dict[str, str], value: str) -> Optional[str]:
        if value in mapping:
            return mapping[value]
        wanted = cls._lookup_key(value)
        for key, mapped in mapping.items():
            if cls._lookup_key(key) == wanted:
                return mapped
        return None

    def _is_canonical_genre(self, value: Optional[str]) -> bool:
        if not value:
            return False
        wanted = self._lookup_key(value)
        return any(self._lookup_key(genre) == wanted for genre in self.canonical_genres)

    def _parent_for_style(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        style = self.normalize_value(value, "style")
        parent = self._lookup_mapping(self.style_parent_map, style)
        if parent:
            return self.normalize_value(parent, "genre")
        return None

    def normalize_pair(
        self,
        genre: Optional[str],
        style: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Normalize a genre/subgenre pair into the controlled Beatport-hybrid model.

        The returned genre is always one of `canonical_genres` when rules are
        enabled. Known styles are resolved to their parent genre; unknown values
        fall back to the configured catch-all genre instead of leaking arbitrary
        tags into canonical output.
        """
        if not self.rules:
            return genre, style

        raw_genre = self._normalize_spacing(genre) if genre else None
        raw_style = self._normalize_spacing(style) if style else None

        if raw_genre and not raw_style:
            split_genre, split_style = self._split_parenthetical(raw_genre)
            raw_genre = split_genre
            raw_style = split_style

        if raw_genre:
            parts = self._split_compound(raw_genre)
            if parts:
                raw_genre = parts[0]
                if not raw_style and len(parts) >= 2:
                    raw_style = parts[1]

        if raw_style:
            style_parts = self._split_compound(raw_style)
            if style_parts:
                raw_style = style_parts[0]

        mapped_genre = self.normalize_value(raw_genre, "genre") if raw_genre else None
        mapped_style = self.normalize_value(raw_style, "style") if raw_style else None
        mapped_genre = mapped_genre or None
        mapped_style = mapped_style or None

        style_parent = self._parent_for_style(mapped_style)
        if mapped_genre and not self._is_canonical_genre(mapped_genre):
            genre_as_style = self.normalize_value(mapped_genre, "style")
            parent = self._parent_for_style(genre_as_style)
            if parent:
                mapped_genre = parent
                mapped_style = mapped_style or genre_as_style
            else:
                mapped_genre = self.fallback_genre or None
                mapped_style = None

        if not mapped_genre and style_parent:
            mapped_genre = style_parent
        elif style_parent and mapped_genre:
            if self._lookup_key(mapped_genre) == self._lookup_key(self.fallback_genre):
                mapped_genre = style_parent
            elif self._lookup_key(mapped_genre) in {"house", "techno", "trance", "electronica", "dance / pop"}:
                mapped_genre = style_parent

        if mapped_genre and not self._is_canonical_genre(mapped_genre):
            mapped_genre = self.fallback_genre or None
            mapped_style = None

        if mapped_style and mapped_genre and self._lookup_key(mapped_style) == self._lookup_key(mapped_genre):
            mapped_style = None

        return mapped_genre, mapped_style

    @classmethod
    def _is_protected(cls, value: str) -> bool:
        if not value:
            return False
        normalized = cls._normalize_spacing(value).lower()
        return normalized in cls.PROTECTED_COMPOUND

    @staticmethod
    def _split_compound(value: str) -> List[str]:
        # Split a compound genre/style string on separators, but ignore
        # separators inside parentheses.
        if not value:
            return []
        if GenreNormalizer._is_protected(value):
            return [GenreNormalizer._normalize_spacing(value)]
        parts: List[str] = []
        char_buffer: List[str] = []
        depth = 0
        char_index = 0
        while char_index < len(value):
            ch = value[char_index]
            if ch == "(":
                depth += 1
            elif ch == ")" and depth > 0:
                depth -= 1

            if depth == 0:
                if value[char_index: char_index + 3] == " / ":
                    part = "".join(char_buffer).strip()
                    if part:
                        parts.append(part)
                    char_buffer = []
                    char_index += 3
                    continue
                if ch in [",", ";", "|", "/"]:
                    part = "".join(char_buffer).strip()
                    if part:
                        parts.append(part)
                    char_buffer = []
                    char_index += 1
                    while char_index < len(value) and value[char_index] == " ":
                        char_index += 1
                    continue

            char_buffer.append(ch)
            char_index += 1

        if char_buffer:
            part = "".join(char_buffer).strip()
            if part:
                parts.append(part)
        return parts

    @staticmethod
    def _split_parenthetical(value: str) -> Tuple[Optional[str], Optional[str]]:
        # If value looks like 'Genre (Style)', split into (genre, style).
        if not value:
            return None, None
        value = GenreNormalizer._normalize_spacing(value)
        match = re.match(r"^(.+?)\s*\((.+)\)\s*$", value)
        if not match:
            return value, None
        return match.group(1).strip(), match.group(2).strip()

    def choose_normalized(
        self, tags: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str], List[str]]:
        """
        Select and normalize genre/style from tags with priority cascade.

        Returns:
            (normalized_genre, normalized_style, dropped_tag_keys)

        Where:
        - normalized_genre: Best-match genre after normalization
        - normalized_style: Best-match style after normalization
        - dropped_tag_keys: Tags that were present but not used
        """
        # Collect candidates from each key in priority order
        genre_candidates = []
        for key in self.GENRE_TAG_KEYS:
            vals = self.get_tag(tags, key)
            if vals:
                genre_candidates.extend(vals)

        style_candidates = []
        for key in self.STYLE_TAG_KEYS:
            vals = self.get_tag(tags, key)
            if vals:
                style_candidates.extend(vals)

        # Track which tags are actually present (for dropped reporting)
        present_tags = set()
        all_relevant_keys = self.GENRE_TAG_KEYS + self.STYLE_TAG_KEYS
        for key in all_relevant_keys:
            if self.get_tag(tags, key):
                present_tags.add(key)

        # Select best candidate and normalize
        genre = genre_candidates[0] if genre_candidates else None
        style = style_candidates[0] if style_candidates else None

        # If no explicit style, split parenthetical from genre
        if genre and not style:
            genre, style = self._split_parenthetical(genre)

        # If still no style, split compound genre
        if genre:
            parts = self._split_compound(genre)
            if parts:
                genre = parts[0]
                if not style and len(parts) >= 2:
                    style = parts[1]

        # If style contains compounds, take first part
        if style:
            style_parts = self._split_compound(style)
            if style_parts:
                style = style_parts[0]

        # Normalize values via rules (if present)
        if genre:
            genre = self.normalize_value(genre, "genre")
        if style:
            style = self.normalize_value(style, "style")

        genre, style = self.normalize_pair(genre, style)

        # Any present tag that didn't participate is "dropped"
        used_tags = set()
        if genre_candidates:
            # Genre came from one of GENRE_TAG_KEYS
            for key in self.GENRE_TAG_KEYS:
                if self.get_tag(tags, key):
                    used_tags.add(key)
                    break  # Only first one is used
        if style_candidates:
            for key in self.STYLE_TAG_KEYS:
                if self.get_tag(tags, key):
                    used_tags.add(key)
                    break

        dropped = sorted(present_tags - used_tags)

        return genre, style, dropped

    def apply_tags_to_file(
        self,
        audio: Any,
        genre: Optional[str],
        style: Optional[str],
    ) -> None:
        """
        Apply normalized genre/style directly to audio tags (mutagen object).

        Beatport-compatible format:
        - GENRE: primary genre
        - SUBGENRE: style/sub-genre
        - GENRE_PREFERRED: style or genre (preference signal)
        - GENRE_FULL: hierarchical "genre | style"

        Args:
            audio: Mutagen audio object with tags
            genre: Normalized genre
            style: Normalized style
        """
        if not audio or not audio.tags:
            return

        tags = audio.tags

        # Set Beatport-compatible fields
        if genre:
            tags["GENRE"] = genre
        if style:
            tags["SUBGENRE"] = style
        else:
            if "SUBGENRE" in tags:
                del tags["SUBGENRE"]

        # GENRE_PREFERRED + GENRE_FULL for cascading
        preferred = style or genre
        if preferred:
            tags["GENRE_PREFERRED"] = preferred

        full = f"{genre} | {style}" if style else genre
        if full:
            tags["GENRE_FULL"] = full

        audio.save()
