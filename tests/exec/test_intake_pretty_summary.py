from __future__ import annotations

import json
import sys
from pathlib import Path


def test_main_reads_planned_move_counts(tmp_path: Path, capsys, monkeypatch) -> None:
    from tagslut.exec import intake_pretty_summary as mod

    out_dir = tmp_path / "artifacts" / "compare"
    out_dir.mkdir(parents=True)
    summary = out_dir / "plan_fpcalc_unique_final_summary_20260322_000000.json"
    summary.write_text(
        json.dumps(
            {
                "planned": {
                    "promote_move": 3,
                    "stash_move": 1,
                    "quarantine_move": 2,
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "argv", ["intake_pretty_summary", "--out-dir", str(out_dir)])
    assert mod.main() == 0

    out = capsys.readouterr().out
    assert "Move Plan" in out
    assert "Promote" in out and "3" in out
    assert "Stash" in out and "1" in out
    assert "Quarantine" in out and "2" in out
