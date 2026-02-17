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
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional


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

    def __init__(self, rules_path: Optional[Path] = None):
        """
        Initialize normalizer with optional rules file.

        Args:
            rules_path: Path to genre normalization rules JSON.
                       If None, no normalization is applied (pass-through).
        """
        self.rules = self._load_rules(rules_path) if rules_path else {}

    @staticmethod
    def _load_rules(path: Path) -> Dict[str, Dict[str, str]]:
        """Load genre/style mapping rules from JSON."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "genre_map": data.get("genre_map", {}),
                "style_map": data.get("style_map", {}),
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
        return mapping.get(value, value)

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
        genre = None
        if genre_candidates:
            genre = self.normalize_value(genre_candidates[0], "genre")

        style = None
        if style_candidates:
            style = self.normalize_value(style_candidates[0], "style")

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
