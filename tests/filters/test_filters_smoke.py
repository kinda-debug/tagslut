"""Smoke tests for the tagslut.filters submodule."""

import tagslut.filters.gig_filter as gig_filter_mod
import tagslut.filters.identity_resolver as identity_resolver_mod
import tagslut.filters.macos_filters as macos_filters_mod
from tagslut.filters.gig_filter import parse_filter
from tagslut.filters.macos_filters import MacOSFilters


def test_gig_filter_module_importable() -> None:
    assert hasattr(gig_filter_mod, "parse_filter")


def test_identity_resolver_module_importable() -> None:
    assert hasattr(identity_resolver_mod, "IdentityResolver")


def test_macos_filters_module_importable() -> None:
    assert hasattr(macos_filters_mod, "MacOSFilters")


def test_parse_filter_empty_returns_match_all() -> None:
    clause, params = parse_filter("")
    assert clause == "1=1"
    assert params == []


def test_parse_filter_single_token() -> None:
    clause, params = parse_filter("genre:house")
    assert "canonical_genre" in clause
    assert "house" in params


def test_macos_filters_identifies_metadata_files() -> None:
    assert MacOSFilters.is_macos_metadata("/music/._track.flac") is True
    assert MacOSFilters.is_macos_metadata("/music/track.flac") is False
