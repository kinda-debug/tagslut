#!/usr/bin/env python3
"""Backward-compatible launcher shim for the DJ review web app."""

from __future__ import annotations

from tagslut._web.review_app import main


if __name__ == "__main__":
    main()
