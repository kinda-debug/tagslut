from __future__ import annotations

from pathlib import Path

from dedupe import rstudio_parser


def test_parse_export_reads_rows(tmp_path: Path) -> None:
    export = tmp_path / "recognized.csv"
    export.write_text("Source Name,New File Name,Size\n/foo/bar.flac,bar.flac,123\n")
    rows = list(rstudio_parser.parse_export(export))
    assert len(rows) == 1
    row = rows[0]
    assert row.source_path.endswith("/foo/bar.flac")
    assert row.suggested_name == "bar.flac"
    assert row.size_bytes == 123
