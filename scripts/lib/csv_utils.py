"""Consistent CSV helpers for the dedupe scripts."""
from __future__ import annotations

import csv
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

CSV_ENCODING = "utf-8"
CSV_QUOTING = csv.QUOTE_ALL
CSV_ESCAPECHAR = "\\"


@contextmanager
def dict_reader(path: Path | str, **kwargs) -> Iterator[csv.DictReader]:
    """Context manager delivering a DictReader for safe CSV parsing."""
    with open(path, newline="", encoding=CSV_ENCODING) as fh:
        reader = csv.DictReader(fh, **kwargs)
        yield reader


@contextmanager
def dict_writer(
    path: Path | str,
    fieldnames: Sequence[str],
    *,
    write_header: bool = True,
    **kwargs,
) -> Iterator[csv.DictWriter]:
    """Context manager that yields a DictWriter configured with safe quoting."""
    with open(path, "w", newline="", encoding=CSV_ENCODING) as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=fieldnames,
            quoting=CSV_QUOTING,
            escapechar=CSV_ESCAPECHAR,
            **kwargs,
        )
        if write_header:
            writer.writeheader()
        yield writer
