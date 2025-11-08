from __future__ import annotations

import zipfile
from pathlib import Path

from dedupe import health
from dedupe.health import HealthChecker, HealthStatus


class StubChecker(HealthChecker):
    def __init__(self, mapping: dict[Path, HealthStatus]):
        self._mapping = mapping

    def check(self, path: Path) -> HealthStatus:  # type: ignore[override]
        return self._mapping.get(path, (True, "stub"))


def test_scan_directory_counts(tmp_path: Path) -> None:
    root = tmp_path / "library"
    root.mkdir()
    good = root / "good.flac"
    bad = root / "bad.wav"
    ignored = root / "note.txt"
    good.write_bytes(b"good")
    bad.write_bytes(b"bad")
    ignored.write_text("skip me", encoding="utf-8")

    checker = StubChecker({good: (True, "ok"), bad: (False, "decode error")})
    log_path = tmp_path / "scan.log"

    summary = health.scan_directory(
        root,
        log_path=log_path,
        workers=1,
        checker=checker,
    )

    assert summary.total == 2
    assert summary.healthy == 1
    assert summary.unhealthy == 1
    assert summary.missing == 0
    assert summary.unknown == 0
    assert "Files discovered: 2" in log_path.read_text(encoding="utf-8")


def test_check_spreadsheet_handles_missing_and_unknown(tmp_path: Path) -> None:
    spreadsheet = tmp_path / "paths.xlsx"
    existing = tmp_path / "existing.flac"
    existing.write_bytes(b"data")
    missing = tmp_path / "missing.flac"
    unknown = tmp_path / "unknown.wav"
    unknown.write_bytes(b"data")

    _write_simple_xlsx(
        spreadsheet,
        [str(existing), str(missing), str(unknown)],
    )

    checker = StubChecker(
        {
            existing: (True, "ok"),
            unknown: (None, "ffmpeg unavailable"),
        }
    )
    log_path = tmp_path / "sheet.log"

    summary = health.check_spreadsheet(
        spreadsheet,
        log_path=log_path,
        workers=1,
        checker=checker,
    )

    assert summary.total == 3
    assert summary.healthy == 1
    assert summary.unhealthy == 0
    assert summary.missing == 1
    assert summary.unknown == 1
    contents = log_path.read_text(encoding="utf-8")
    assert "Spreadsheet:" in contents
    assert "[MISSING]" in contents
    assert "[UNKNOWN]" in contents


def _write_simple_xlsx(path: Path, rows: list[str]) -> None:
    shared_strings = """<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{count}" uniqueCount="{count}">
{entries}
</sst>
""".format(
        count=len(rows),
        entries="".join(
            f"  <si><t>{value}</t></si>\n" for value in rows
        ),
    )
    sheet_rows = []
    for index, _ in enumerate(rows):
        sheet_rows.append(
            "  <row r=\"{row}\"><c r=\"A{row}\" t=\"s\"><v>{value}</v></c></row>\n".format(
                row=index + 1,
                value=index,
            )
        )
    sheet = """<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
{rows}  </sheetData>
</worksheet>
""".format(rows="".join(sheet_rows))

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", """<?xml version='1.0' encoding='UTF-8'?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>
""")
        archive.writestr("xl/sharedStrings.xml", shared_strings)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
