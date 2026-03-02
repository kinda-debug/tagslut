from __future__ import annotations

import csv
from pathlib import Path

from tagslut.dj.rekordbox_prep import parse_rekordbox_report_summary


def test_parse_rekordbox_report_summary_counts(tmp_path: Path) -> None:
    report_path = tmp_path / "rekordbox_prep_report.csv"
    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["status", "note"])
        writer.writeheader()
        writer.writerow({"status": "OK", "note": ""})
        writer.writerow({"status": "SUSPECT_UPSCALE", "note": "HF warning | quarantined=2"})
        writer.writerow({"status": "OK", "note": "quarantined=1"})

    summary = parse_rekordbox_report_summary(report_path)

    assert summary.tracks_processed == 3
    assert summary.suspect_upscale_count == 1
    assert summary.files_quarantined == 3
    assert summary.report_path == report_path
