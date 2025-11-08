"""Legacy entry point delegating to :mod:`dedupe.legacy_cli`."""

from __future__ import annotations

from dedupe.legacy_cli import detect_playback_length_issues_main


def main(argv: list[str] | None = None) -> int:
    """Invoke :func:`dedupe.legacy_cli.detect_playback_length_issues_main`."""

    return detect_playback_length_issues_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
