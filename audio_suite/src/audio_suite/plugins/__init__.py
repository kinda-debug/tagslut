"""Extension points for Audio Suite.

Plugins allow core functionality to be extended without modifying the
core application.  Built‑in plugins live under :mod:`audio_suite.plugins.match`
and :mod:`audio_suite.plugins.export`.  External plugins can be installed
via entry points in the future.
"""

__all__ = ["match", "export"]