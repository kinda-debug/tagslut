"""Module description placeholder."""

from __future__ import annotations

import csv
from pathlib import Path

from dedupe import manifest, utils


def test_rows_from_matches_normalises_paths(tmp_path: Path) -> None:
    matches_csv = tmp_path / "matches.csv"
    library_path = str(tmp_path / "Cafe\u0301" / "song.flac")
    recovery_path = str(tmp_path / "Cafe\u0301" / "song.flac")
    with matches_csv.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "library_path",
                "recovery_path",
                "recovery_name",
                "score",
                "classification",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "library_path": library_path,
                "recovery_path": recovery_path,
                "recovery_name": "song.flac",
                "score": "1.0",
                "classification": "exact",
            }
        )

    rows = list(manifest._rows_from_matches(matches_csv))
    assert rows[0].library_path == utils.normalise_path(library_path)
    assert rows[0].recovery_path == utils.normalise_path(recovery_path)
