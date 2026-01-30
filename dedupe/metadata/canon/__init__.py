"""Canonization utilities for tag normalization."""

from .apply import (
    CanonRules,
    apply_canon,
    canon_diff,
    load_canon_rules,
)

__all__ = ["CanonRules", "apply_canon", "canon_diff", "load_canon_rules"]
