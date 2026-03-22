from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from textwrap import dedent

from tagslut.adapters.rekordbox.overlay import apply_rekordbox_overlay


def _write_overlay_config(path: Path) -> None:
    path.write_text(
        dedent(
            """
            colour_palette:
              none: null
              blue: 0x0000FF
              green: 0x00FF00
              yellow: 0xFFFF00
              pink: 0xFF66CC
              orange: 0xFF8000
              red: 0xFF0000

            state_defaults:
              arriving:
                rating: 1
                colour: blue
                priority: 10
              warming_up:
                rating: 2
                colour: green
                priority: 20
              transition:
                rating: 2
                colour: green
                priority: 30
              safety_net:
                rating: 3
                colour: yellow
                priority: 45
              wants_recognition:
                rating: 3
                colour: pink
                priority: 50
              locked_in:
                rating: 4
                colour: orange
                priority: 70
              late_night_open:
                rating: 5
                colour: red
                priority: 90
              utility:
                rating: 2
                colour: none
                priority: 15

            playlist_state_hints:
              01_WARMUP_GROOVE: arriving
              02_BUILDERS: warming_up
              04_PEAK_FLOOR: locked_in
              05_SINGALONG_CROWD: wants_recognition
              08_LAST_HOUR_DESTROYERS: late_night_open

            heuristics:
              preserve_existing_overlay: true
              duration_min_seconds: 90
              duration_max_seconds: 720

            manual_overrides:
              - match:
                  track_id: "2"
                force_rating: 2
                force_colour: green
                notes: keep this as a bridge

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
              <COLLECTION Entries="6">
                <TRACK TrackID="1" Name="Warm Track" Artist="Alpha Artist" Genre="House" AverageBpm="110" Comments="04 Energy, 05 Dance" Location="file://localhost/Users/test/Music/Warm%20Track.mp3" />
                <TRACK TrackID="2" Name="Peak Track" Artist="Bravo Artist" Genre="Techno" AverageBpm="128" Comments="10 Energy, 09 Dance" Location="file://localhost/Users/test/Music/Peak%20Track.mp3" />
                <TRACK TrackID="3" Name="Clash Track" Artist="Charlie Artist" Genre="Techno" AverageBpm="127" Comments="08 Energy, 08 Dance" Location="file://localhost/Users/test/Music/Clash%20Track.mp3" />
                <TRACK TrackID="4" Name="Crowd Track" Artist="Delta Artist" Genre="Pop" AverageBpm="oops" Location="file://localhost/Users/test/Music/Crowd%20Track.mp3" />
                <TRACK TrackID="5" Name="Loose Track" Artist="Echo Artist" Genre="Ambient" Location="file://localhost/Users/test/Music/Loose%20Track.mp3" />
                <TRACK TrackID="6" Name="Existing Track" Artist="Foxtrot Artist" Genre="Disco" Rating="3" Colour="0xFFFF00" Comments="06 Energy, 06 Dance" Location="file://localhost/Users/test/Music/Existing%20Track.mp3" />
              </COLLECTION>
              <PLAYLISTS>
                <NODE Type="0" Name="ROOT" Count="4">
                  <NODE Type="1" Name="01_WARMUP_GROOVE" Entries="1">
                    <TRACK Key="1" />
                  </NODE>
                  <NODE Type="1" Name="04_PEAK_FLOOR" Entries="1">
                    <TRACK Key="2" />
                  </NODE>
                  <NODE Type="0" Name="Set Folder" Count="2">
                    <NODE Type="1" Name="02_BUILDERS" Entries="1">
                      <TRACK Key="3" />
                    </NODE>
                    <NODE Type="1" Name="08_LAST_HOUR_DESTROYERS" Entries="1">
                      <TRACK Key="3" />
                    </NODE>
                  </NODE>
                  <NODE Type="1" Name="05_SINGALONG_CROWD" Entries="1">
                    <TRACK Key="4" />
                  </NODE>
                </NODE>
              </PLAYLISTS>
            </DJ_PLAYLISTS>
            """
        ),
        encoding="utf-8",
    )


def _track_map(xml_path: Path) -> dict[str, ET.Element]:
    tree = ET.parse(xml_path)
    collection = tree.getroot().find("COLLECTION")
    assert collection is not None
    return {track.attrib["TrackID"]: track for track in collection.findall("TRACK")}


def test_apply_rekordbox_overlay_preserves_comments_and_only_changes_intended_tracks(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    input_xml = tmp_path / "input.xml"
    output_xml = tmp_path / "output.xml"
    audit_csv = tmp_path / "audit.csv"
    audit_json = tmp_path / "audit.json"

    _write_overlay_config(config_path)
    _write_input_xml(input_xml)

    result = apply_rekordbox_overlay(
        input_xml=input_xml,
        output_xml=output_xml,
        config_path=config_path,
        audit_csv_path=audit_csv,
        audit_json_path=audit_json,
        backup_existing=False,
    )

    assert result.tracks_scanned == 6
    assert result.tracks_changed == 4
    assert result.rating_changed == 4
    assert result.colour_changed == 4
    assert result.manual_overrides_applied == 1
    assert result.preserved_existing == 1

    tracks = _track_map(output_xml)

    assert tracks["1"].attrib["Comments"] == "04 Energy, 05 Dance"
    assert tracks["1"].attrib["Rating"] == "1"
    assert tracks["1"].attrib["Colour"] == "0x0000FF"

    assert tracks["2"].attrib["Rating"] == "2"
    assert tracks["2"].attrib["Colour"] == "0x00FF00"

    assert tracks["3"].attrib["Rating"] == "5"
    assert tracks["3"].attrib["Colour"] == "0xFF0000"

    assert tracks["4"].attrib["Rating"] == "3"
    assert tracks["4"].attrib["Colour"] == "0xFF66CC"

    assert "Rating" not in tracks["5"].attrib
    assert "Colour" not in tracks["5"].attrib

    assert tracks["6"].attrib["Rating"] == "3"
    assert tracks["6"].attrib["Colour"] == "0xFFFF00"

    ET.parse(output_xml)
    audit_rows = list(csv.DictReader(audit_csv.open("r", encoding="utf-8", newline="")))
    assert [row["TrackID"] for row in audit_rows] == ["1", "2", "3", "4"]

    audit_payload = json.loads(audit_json.read_text(encoding="utf-8"))
    assert audit_payload["tracks_changed"] == 4
    assert len(audit_payload["changed_tracks"]) == 4


def test_apply_rekordbox_overlay_audit_explains_manual_override_and_playlist_conflict(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "overlay.yaml"
    input_xml = tmp_path / "input.xml"
    output_xml = tmp_path / "output.xml"
    audit_csv = tmp_path / "audit.csv"

    _write_overlay_config(config_path)
    _write_input_xml(input_xml)

    apply_rekordbox_overlay(
        input_xml=input_xml,
        output_xml=output_xml,
        config_path=config_path,
        audit_csv_path=audit_csv,
        backup_existing=False,
    )

    audit_rows = {row["TrackID"]: row for row in csv.DictReader(audit_csv.open("r", encoding="utf-8", newline=""))}

    assert audit_rows["2"]["override_source"] == "manual_overrides[0]"
    assert "playlist hint: 04_PEAK_FLOOR -> locked_in" in audit_rows["2"]["decision_reason"]
    assert "force_rating=2" in audit_rows["2"]["decision_reason"]
    assert "keep this as a bridge" in audit_rows["2"]["decision_reason"]

    assert audit_rows["3"]["override_source"] == "playlist_state_hints"
    assert "02_BUILDERS->warming_up" in audit_rows["3"]["decision_reason"]
    assert "08_LAST_HOUR_DESTROYERS->late_night_open" in audit_rows["3"]["decision_reason"]
    assert audit_rows["3"]["chosen_state"] == "late_night_open"


def test_apply_rekordbox_overlay_handles_missing_comments_and_malformed_bpm(tmp_path: Path) -> None:
    config_path = tmp_path / "overlay.yaml"
    input_xml = tmp_path / "input.xml"
    output_xml = tmp_path / "output.xml"

    _write_overlay_config(config_path)
    _write_input_xml(input_xml)

    apply_rekordbox_overlay(
        input_xml=input_xml,
        output_xml=output_xml,
        config_path=config_path,
        backup_existing=False,
    )

    tracks = _track_map(output_xml)
    assert tracks["4"].attrib["Rating"] == "3"
    assert tracks["4"].attrib["Colour"] == "0xFF66CC"
    assert "Comments" not in tracks["4"].attrib
    assert tracks["5"].attrib.get("AverageBpm") is None
