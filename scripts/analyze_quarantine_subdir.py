"""Legacy entry point delegating to :mod:`dedupe.legacy_cli`."""

from __future__ import annotations

from dedupe.legacy_cli import analyse_quarantine_subdir_main


def main(argv: list[str] | None = None) -> int:
    """Invoke :func:`dedupe.legacy_cli.analyse_quarantine_subdir_main`."""

    return analyse_quarantine_subdir_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
