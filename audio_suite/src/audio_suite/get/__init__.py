"""Streaming provider API integration for Audio Suite.

The :mod:`audio_suite.get` package contains modules that interface with
external music services.  Each provider lives in its own subpackage under
``providers`` and exposes a ``download_track`` function.
"""

__all__ = ["providers"]