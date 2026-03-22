from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from click.testing import CliRunner

from tagslut.cli.main import cli


def _write_overlay_config(path: Path) -> None:
    path.write_text(
        dedent(
            """
            colour_palette:
              none: null
              blue: 0x0000FF

            state_defaults:
              arriving:
                rating: 1
                colour: blue
                priority: 10

            playlist_state_hints:
              01_WARMUP_GROOVE: arriving

            heuristics:
              preserve_existing_overlay: true

            manual_overrides: []
            recognition_artists: []
            recognition_titles: []
            never_peak_artists: []
            never_peak_titles: []
            utility_only_titles: []
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _write_input_xml(path: Path) -> None:
    path.write_text(
        dedent(
            """\
            <?xml version="1.0" encoding="UTF-8"?>
            <DJ_PLAYLISTS Version="1.0.0">
              <PRODUCT Name="rekordbox" Version="7.2.11" Company="AlphaTheta" />
              <COLLECTION Entries="1">
                <TRACK TrackID="1" Name="Warm Track" Artist="Alpha Artist" Comments="04 Energy, 05 Dance" Location="file://localhost/Users/test/Music/Warm%20Track.mp3" />
              </COLLECTION>
              <PLAYLISTS>
                <NODE Type="0" Name="ROOT" Count="1">
                  <NODE Type="1" Name="01_WARMUP_GROOVE" Entries="1">
                    <TRACK Key="1" />
                  </NODE>
                </NODE>
              </PLAYLISTS>
            </DJ_PLAYLISTS>
            """
        ),
        encoding="utf-8",
    )


def test_gig_apply_rekordbox_overlay_command_writes_xml_and_default_audit(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    input_xml = tmp_path / "input.xml"
    output_xml = tmp_path / "output.xml"

    _write_overlay_config(config_path)
    _write_input_xml(input_xml)

    result = CliRunner().invoke(
        cli,
        [
            "gig",
            "apply-rekordbox-overlay",
            "--input-xml",
            str(input_xml),
            "--output-xml",
            str(output_xml),
            "--overlay-config",
            str(config_path),
            "--no-backup",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Tracks scanned:            1" in result.output
    assert "Tracks changed:           1" in result.output
    assert f"Output XML:               {output_xml}" in result.output

    audit_csv = output_xml.with_suffix(".overlay_audit.csv")
    assert audit_csv.exists()
    assert output_xml.exists()

    output_text = output_xml.read_text(encoding="utf-8")
    assert 'Comments="04 Energy, 05 Dance"' in output_text
    assert 'Rating="1"' in output_text
    assert 'Colour="0x0000FF"' in output_text
