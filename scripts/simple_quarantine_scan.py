"""Legacy entry point delegating to :mod:`dedupe.legacy_cli`."""

from __future__ import annotations

from dedupe.legacy_cli import simple_quarantine_scan_main


def main(argv: list[str] | None = None) -> int:
    """Invoke :func:`dedupe.legacy_cli.simple_quarantine_scan_main`."""

    return simple_quarantine_scan_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
