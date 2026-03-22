#!/usr/bin/env python3
# Prompt for Codex (as a comment at the top of your Python file)
# Context and goal
# We previously classified tracks from a CSV into three categories-"club" (high-energy dancefloor tracks), "bar"
# (mid-energy/chill tracks suitable for lounge or warm-up sets), and "remove" (non-dance tracks). Now we have a
# SQLite database with all tracks and want to continue the same process programmatically. We also want to prepare
# additional energy-level playlists (chill, mid-tempo, high-energy, banger) based on industry guidance.
# Technical requirements
# 1. Connect to the SQLite database. Use Python's built-in sqlite3 module to create a connection and cursor. The docs
#    show that you open a database with sqlite3.connect("tutorial.db") and then create a cursor with con.cursor().
#    Replace "tutorial.db" with the real path to our database (e.g. tracks.db).
# 2. Inspect the schema. Query sqlite_master to find the table names (SELECT name FROM sqlite_master WHERE type='table').
#    Assume the main table contains columns such as title, artist, bpm, energy, genre, comment, duration, label,
#    and file_path. If necessary, adjust the column names based on the actual schema.
# 3. Load data into pandas. Use pandas.read_sql_query() to read the relevant table into a DataFrame. Keep only the
#    columns needed for classification: title, artist, bpm, energy, genre, duration, and file_path.
# 4. Define classification heuristics. Create a function classify_track(row) that returns "club", "bar" or "remove"
#    based on the following logic:
#    * Tempo (BPM): Dance genres like house/techno/trance generally fall between ~115-130 BPM. If bpm is within 115-130
#      and energy is high, treat it as a strong club candidate. Lower BPMs (80-115) are more suitable for bar or chill
#      sets; very slow (<80) should lean toward remove.
#    * Energy rating: Mixed-In-Key's system notes that energy levels 1-4 are chillout/non-club, level 5 is where
#      dancing begins, levels 6-7 are easily danceable and peak-time. Use energy >=5 as a baseline for club; energy 3-4
#      for bar; energy <3 for remove.
#    * Genre: If the genre string contains keywords like house, techno, disco, dance, club, or electro, boost the score
#      for club. If it contains funk, soul, downtempo, chill, world, ambient, or similar, lean toward bar or remove.
#    * Track titles/albums: If the title or comment fields include DJ-friendly cues such as "Remix", "Mix", "Edit",
#      "Dub", "Extended", "Club", "VIP", or "Original Mix", treat them as intended for DJ sets. Conversely, tracks marked
#      "Live", "Acoustic", "Demo" or featuring extremely long ambient intros may be non-dance.
#    * Combine these cues into a scoring system. For example:
#      * Start with a base score of 0.
#      * Add +2 if BPM is between 115-130; +1 if between 100-115; -1 if below 100 or above 140.
#      * Add +2 if energy >=6; +1 if energy is 5; -1 if energy <3.
#      * Add +2 if genre contains a club keyword; +1 if genre contains a bar keyword; -2 otherwise.
#      * Add +1 if title/comment contains DJ-friendly keywords; -1 if it contains non-club keywords.
#      * Assign the category: score >=4 -> "club", score 1-3 -> "bar", score <=0 -> "remove".
# 5. Document the rationale: ZipDJ recommends using mood/energy-based playlists such as Chill (low energy) for warm-up
#    sets and bars, Mid-Tempo (medium energy) for early evening/lively bars, High Energy for dancing, and Absolute
#    Banger for peak sets. DJ TechTools adds categories like Sunrise, Kickin It, Warm-Up, Primetime, Bangin, Trippin
#    and Late Night. Use these as optional labels when creating additional playlists beyond the basic "club/bar/remove."
# 6. Apply classification. Use df.apply(classify_track, axis=1) to compute a new classification column. Count the number
#    of tracks in each category and print the totals to verify the distribution.
# 7. Update the SQLite database. If desired, alter the table to add a classification column
#    (ALTER TABLE tracks ADD COLUMN classification TEXT). Then iterate over the DataFrame and update each row using
#    parameterized SQL (UPDATE tracks SET classification=? WHERE id=?). Remember to commit the transaction (con.commit()).
# 8. Export a CSV summary. Use df.to_csv("unnamed_playlist_classification_with_bar.csv", index=False) so the user can
#    review the results. Include columns artist, title, bpm, energy, genre, classification, and file_path.
# 9. Generate M3U8 playlists. For each category (club, bar, remove) and for each additional energy playlist if desired
#    (e.g. chill, midtempo, highenergy, banger), do the following:
#    * Create a file with the .m3u8 extension (e.g. club_playlist.m3u8).
#    * Write #EXTM3U on the first line (M3U is a plain text format containing one entry per line).
#    * For each track in that category, write an #EXTINF line containing the duration in seconds and the display name
#      (artist - title), then write the absolute file path on the next line. Example:
#      #EXTINF:208,Argonaut & Wasp - Crystal Stills
#      /Volumes/MUSIC/LIBRARY/Argonaut & Wasp/(2018) Future Protocol/Argonaut & Wasp - (2018) Future Protocol - 01 Crystal Stills.flac
#    * Use newline separation between entries.
# 10. Create additional energy-level playlists. Based on the ZipDJ guidance and DJ TechTools categories, define
#     energy-specific playlists:
#     * Chill/Sunrise: BPM <100 or energy <3; genres like chill house, downtempo and ambient.
#     * Mid-Tempo/Warm-Up/Kickin It: BPM 100-115 and energy 3-4; genres like deep house, soul, funk and disco.
#     * High Energy/Primetime: BPM 115-130 and energy 5-6; genres like house, electro and slower-tempo techno.
#     * Absolute Banger/Bangin: BPM >130 or energy >=7; genres like drum & bass, hardcore and hard techno.
# 11. Use similar scoring logic to assign each track to one of these categories and export corresponding M3U8 files
#     (e.g. energy_chill.m3u8, energy_midtempo.m3u8, etc.).
# 12. Test and iterate. After generating the playlists and CSV, print sample rows from each category to confirm that the
#     classification matches your intuition. Adjust thresholds or keywords if necessary. DJ TechTools stresses that
#     energy categories are subjective and you should listen to each song "as if you were a person on the dancefloor",
#     so feel free to refine the scoring to better reflect your library and DJ style.
# Deliverables
# * The updated SQLite database with a new classification column.
# * unnamed_playlist_classification_with_bar.csv summarizing the classification.
# * club_playlist.m3u8, bar_playlist.m3u8, remove_playlist.m3u8.
# * Additional energy-based M3U8 playlists (energy_chill.m3u8, energy_midtempo.m3u8, energy_highenergy.m3u8,
#   energy_banger.m3u8), if requested.
# Reminder: Use parameterized SQL queries to prevent SQL injection, commit after inserts/updates, and close the
# connection when done. Document your assumptions and the reasoning behind your scoring so the user can tweak the
# heuristics later.

from __future__ import annotations

import argparse
import math
import sqlite3
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


CLUB_KEYWORDS = [
    "house",
    "techno",
    "trance",
    "disco",
    "dance",
    "club",
    "electro",
    "edm",
]

BAR_KEYWORDS = [
    "funk",
    "soul",
    "downtempo",
    "chill",
    "ambient",
    "world",
    "lounge",
    "deep house",
    "nu disco",
]

DJ_FRIENDLY_KEYWORDS = [
    "remix",
    "mix",
    "edit",
    "dub",
    "extended",
    "club",
    "vip",
    "original mix",
]

NON_CLUB_KEYWORDS = [
    "live",
    "acoustic",
    "demo",
]

ANTI_DJ_KEYWORDS = [
    "ambient",
    "classical",
    "soundtrack",
    "spoken word",
    "audiobook",
    "meditation",
    "nature sounds",
]

ENERGY_KEYWORDS = {
    "chill": ["chill", "chillout", "downtempo", "ambient", "lofi", "lo-fi"],
    "midtempo": ["deep house", "soul", "funk", "disco"],
    "highenergy": ["house", "electro", "techno"],
    "banger": ["drum & bass", "dnb", "hardcore", "hard techno"],
}

DURATION_MS_COLUMNS = {"duration_ms", "duration_ref_ms", "duration_measured_ms"}

COLUMN_ALIASES = {
    "id": ["id", "track_id"],
    "title": ["title", "track_title", "name", "song", "track", "canonical_title"],
    "artist": ["artist", "artist_name", "performer", "canonical_artist"],
    "bpm": ["bpm", "tempo", "canonical_bpm"],
    "energy": ["energy", "energy_level", "energy_rating", "canonical_energy"],
    "genre": ["genre", "style", "tags", "canonical_sub_genre"],
    "genre_fallback": ["canonical_genre"],
    "comment": [
        "comment",
        "comments",
        "note",
        "notes",
        "album",
        "album_comment",
        "mix",
        "version",
        "canonical_mix_name",
        "canonical_album",
    ],
    "duration": [
        "duration",
        "length",
        "seconds",
        "duration_seconds",
        "duration_ms",
        "duration_ref_ms",
        "duration_measured_ms",
    ],
    "file_path": ["file_path", "path", "filepath", "file", "location", "original_path"],
}


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    return " ".join(text.split())


def _has_any(text: str, keywords: Iterable[str]) -> bool:
    if not text:
        return False
    return any(keyword in text for keyword in keywords)


def _to_number(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def classify_track(row: pd.Series) -> str:
    score = 0

    bpm = _to_number(row.get("bpm"))
    energy = _to_number(row.get("energy"))

    # HYBRID GENRE FALLBACK: use sub_genre if present, else main_genre
    sub_genre = _normalize_text(row.get("genre"))  # canonical_sub_genre
    main_genre = _normalize_text(row.get("genre_fallback"))  # canonical_genre
    genre_text = sub_genre if sub_genre else main_genre

    title_text = _normalize_text(row.get("title"))
    comment_text = _normalize_text(row.get("comment"))
    dj_text = " ".join([title_text, comment_text]).strip()

    if bpm is not None:
        if 115 <= bpm <= 130:
            score += 2
        elif 100 <= bpm < 115:
            score += 1
        elif bpm < 100 or bpm > 140:
            score -= 1

    if energy is not None:
        if energy >= 6:
            score += 2
        elif energy >= 5:
            score += 1
        elif energy < 3:
            score -= 1

    # SOFTER GENRE SCORING
    if genre_text:
        if _has_any(genre_text, CLUB_KEYWORDS):
            score += 2
        elif _has_any(genre_text, BAR_KEYWORDS):
            score += 1
        elif _has_any(genre_text, ANTI_DJ_KEYWORDS):
            score -= 2  # Explicit anti-DJ genres penalized
        # else: unknown genre = 0 (no penalty)
    # else: missing genre = 0 (no penalty, data quality issue not musical)

    if _has_any(dj_text, DJ_FRIENDLY_KEYWORDS):
        score += 1
    if _has_any(dj_text, NON_CLUB_KEYWORDS):
        score -= 1

    if score >= 4:
        return "club"
    if score >= 1:
        return "bar"
    return "remove"


def classify_energy_bucket(row: pd.Series) -> str:
    scores = {"chill": 0, "midtempo": 0, "highenergy": 0, "banger": 0}

    bpm = _to_number(row.get("bpm"))
    energy = _to_number(row.get("energy"))
    genre_text = _normalize_text(row.get("genre"))

    if bpm is not None:
        if bpm < 100:
            scores["chill"] += 2
        elif 100 <= bpm < 115:
            scores["midtempo"] += 2
        elif 115 <= bpm <= 130:
            scores["highenergy"] += 2
        elif bpm > 130:
            scores["banger"] += 2

    if energy is not None:
        if energy < 3:
            scores["chill"] += 2
        elif 3 <= energy <= 4:
            scores["midtempo"] += 2
        elif 5 <= energy <= 6:
            scores["highenergy"] += 2
        elif energy >= 7:
            scores["banger"] += 2

    if genre_text:
        for bucket, keywords in ENERGY_KEYWORDS.items():
            if _has_any(genre_text, keywords):
                scores[bucket] += 1

    order = ["banger", "highenergy", "midtempo", "chill"]
    best_score = max(scores.values())
    for bucket in order:
        if scores[bucket] == best_score:
            return bucket
    return "midtempo"


def _robust_norm(series: pd.Series) -> pd.Series:
    """Library-relative normalization using IQR (z-score style, clipped to [-2, 2])."""
    s = series.astype(float)
    med = s.median(skipna=True)
    q25 = s.quantile(0.25, interpolation="linear")
    q75 = s.quantile(0.75, interpolation="linear")
    iqr = (q75 - q25) if (q75 is not None and q25 is not None and pd.notna(q75) and pd.notna(q25)) else 0.0
    if not np.isfinite(iqr) or iqr == 0:
        return pd.Series(np.zeros(len(s)), index=s.index)
    z = (s - med) / iqr
    return z.clip(-2, 2).fillna(0.0)


def _query_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [row[0] for row in rows if row[0] != "sqlite_sequence"]


def _resolve_table(conn: sqlite3.Connection, table_arg: str | None) -> str:
    tables = _query_tables(conn)
    if not tables:
        raise SystemExit("No tables found in the SQLite database.")
    if table_arg:
        if table_arg not in tables:
            raise SystemExit(f"Table '{table_arg}' not found. Available tables: {', '.join(tables)}")
        return table_arg
    if len(tables) == 1:
        return tables[0]
    raise SystemExit("Multiple tables found. Provide --table. Available tables: " + ", ".join(tables))


def _get_table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [row[1] for row in rows]


def _resolve_column(columns: list[str], canonical: str) -> str | None:
    for candidate in COLUMN_ALIASES[canonical]:
        if candidate in columns:
            return candidate
    return None


def _build_select(table: str, columns: list[str], include_comment: bool) -> tuple[str, dict[str, str]]:
    resolved: dict[str, str] = {}
    required = ["title", "artist", "bpm", "energy", "genre", "duration", "file_path"]
    optional = ["comment"] if include_comment else []

    for key in required + optional + ["id"]:
        col = _resolve_column(columns, key)
        if col:
            resolved[key] = col

    # HYBRID GENRE: also try to resolve genre_fallback (canonical_genre)
    if "genre_fallback" in COLUMN_ALIASES:
        fallback_col = _resolve_column(columns, "genre_fallback")
        if fallback_col:
            resolved["genre_fallback"] = fallback_col

    missing_required = [key for key in required if key not in resolved]
    if missing_required:
        raise SystemExit(
            "Missing required columns: "
            + ", ".join(missing_required)
            + "\nAvailable columns: "
            + ", ".join(columns)
        )

    select_cols = [resolved[key] for key in resolved]
    select_sql = f"SELECT {', '.join(select_cols)} FROM {table}"
    return select_sql, resolved


def _normalize_paths(value: object, base_root: Path | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    if not path.is_absolute() and base_root is not None:
        path = base_root / path
    elif not path.is_absolute():
        path = path.resolve()
    return str(path)


def _write_m3u8(path: Path, rows: pd.DataFrame) -> None:
    lines = ["#EXTM3U"]
    for _, row in rows.iterrows():
        duration = _to_number(row.get("duration"))
        duration_int = int(duration) if duration is not None else -1
        artist = str(row.get("artist") or "Unknown").strip()
        title = str(row.get("title") or "Unknown").strip()
        display = f"{artist} - {title}".strip()
        file_path = str(row.get("file_path") or "").strip()
        if not file_path:
            continue
        lines.append(f"#EXTINF:{duration_int},{display}")
        lines.append(file_path)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_samples(df: pd.DataFrame, label_col: str, label: str, sample_size: int) -> None:
    subset = df[df[label_col] == label]
    if subset.empty:
        print(f"Sample {label_col}={label}: 0 rows")
        return
    print(f"Sample {label_col}={label} (showing up to {sample_size} rows):")
    cols = ["artist", "title", "bpm", "energy", "genre", label_col]
    print(subset[cols].head(sample_size).to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify tracks from a SQLite database and generate playlists.")
    parser.add_argument("--db", required=True, help="Path to the SQLite database (e.g. tracks.db).")
    parser.add_argument("--table", help="Table name containing track data.")
    parser.add_argument(
        "--csv-out",
        default="unnamed_playlist_classification_with_bar.csv",
        help="CSV output path.",
    )
    parser.add_argument(
        "--playlist-dir",
        default=".",
        help="Output directory for M3U8 playlists.",
    )
    parser.add_argument(
        "--path-root",
        default=None,
        help="Optional base path to prepend to relative file_path values.",
    )
    parser.add_argument(
        "--no-db-update",
        action="store_true",
        help="Skip adding/updating the classification columns in the database.",
    )
    parser.add_argument(
        "--no-energy-playlists",
        action="store_true",
        help="Skip generating energy-level playlists.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="Number of sample rows to print for each category.",
    )

    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    base_root = Path(args.path_root).expanduser() if args.path_root else None

    con = sqlite3.connect(str(db_path))
    try:
        cursor = con.cursor()
        tables = _query_tables(con)
        print(f"Tables found: {', '.join(tables)}")

        table = _resolve_table(con, args.table)
        columns = _get_table_columns(con, table)
        print(f"Using table: {table}")
        print(f"Columns: {', '.join(columns)}")

        select_sql, resolved = _build_select(table, columns, include_comment=True)
        df = pd.read_sql_query(select_sql, con)

        df = df.rename(columns={v: k for k, v in resolved.items()})

        for col in ("bpm", "energy", "duration"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "comment" not in df.columns:
            df["comment"] = ""

        duration_source = resolved.get("duration")
        if duration_source in DURATION_MS_COLUMNS and "duration" in df.columns:
            df["duration"] = df["duration"] / 1000.0

        if "file_path" in df.columns:
            df["_file_path_key"] = df["file_path"]
            df["file_path"] = df["file_path"].apply(lambda value: _normalize_paths(value, base_root))

        df["classification"] = df.apply(classify_track, axis=1)
        df["energy_bucket"] = df.apply(classify_energy_bucket, axis=1)

        # ENRICH genre column with fallback for CSV export (sparse → hybrid)
        # Fallback logic: use sub_genre if present and non-blank, else use main_genre
        # For display, preserve original casing; normalization only applies to scoring
        if "genre_fallback" in df.columns:
            df["genre"] = df.apply(
                lambda row: (
                    (str(row.get("genre")).strip() if row.get("genre") else "")
                    or (str(row.get("genre_fallback")).strip() if row.get("genre_fallback") else "")
                ),
                axis=1
            )

        print("\nClassification counts:")
        classification_counts = df["classification"].value_counts(dropna=False)
        print(classification_counts.to_string())

        print("\nEnergy bucket counts:")
        print(df["energy_bucket"].value_counts(dropna=False).to_string())

        # REGRESSION TRIPWIRES (v2 invariants)
        # These checks fail loudly if the patch broke expected behavior
        total_rows = len(df)
        remove_pct = (classification_counts.get("remove", 0) / total_rows * 100) if total_rows else 0
        genre_blank_count = df["genre"].isna().sum() + (df["genre"] == "").sum()
        genre_blank_pct = (genre_blank_count / total_rows * 100) if total_rows else 0

        if remove_pct > 80:
            print(f"\n⚠️  WARNING: remove category is {remove_pct:.1f}% (expected ~26% for v2)")
            print("    This suggests genre_fallback resolution may have failed or scoring regressed.")
        if genre_blank_pct > 20:
            print(f"\n⚠️  WARNING: genre blank rate is {genre_blank_pct:.1f}% (expected <10% for v2)")
            print("    Fallback enrichment may not be working; check canonical_genre column.")

        print(f"\nRegression check summary (v2 invariants):")
        print(f"  remove% = {remove_pct:.1f}% (should be ~26%)")
        print(f"  genre_blank% = {genre_blank_pct:.1f}% (should be <10%)")
        print(f"  csv_rows = {total_rows}")
        if remove_pct <= 80 and genre_blank_pct <= 20:
            print("  ✅ All invariants OK")

        # ============================================================================
        # PHASE_V3: SET ARC CLASSIFICATION (warmup, lift, peak, closing, archive)
        # ============================================================================

        # Gate archive early (remove classification → archive phase)
        is_club = df["classification"].astype(str).str.lower().eq("club")
        is_bar = df["classification"].astype(str).str.lower().eq("bar")
        is_archive = df["classification"].astype(str).str.lower().eq("remove")

        # Compute intensity score: 65% energy + 35% BPM (library-relative)
        bpm_norm = _robust_norm(df["bpm"])
        energy_norm = _robust_norm(df["energy"])
        df["_intensity_v3"] = 0.65 * energy_norm + 0.35 * bpm_norm

        # Quantile thresholds computed over club tracks only (domain-aware)
        cal = df.loc[is_club, "_intensity_v3"]
        q25 = float(cal.quantile(0.25))
        q60 = float(cal.quantile(0.60))
        q90 = float(cal.quantile(0.90))

        def _phase_from_intensity(intensity: float) -> str:
            if intensity < q25:
                return "warmup"
            if intensity < q60:
                return "lift"
            if intensity < q90:
                return "peak"
            return "closing"

        # Assign phase: archive for remove, else intensity-based
        df["phase_v3"] = "archive"
        # Club tracks: full arc
        df.loc[is_club, "phase_v3"] = df.loc[is_club, "_intensity_v3"].map(_phase_from_intensity)
        # Bar tracks: cap at lift (never peak/closing)
        bar_phases = df.loc[is_bar, "_intensity_v3"].map(_phase_from_intensity)
        bar_phases = bar_phases.replace({"peak": "lift", "closing": "lift"})
        df.loc[is_bar, "phase_v3"] = bar_phases

        # OPTIONAL: Override peak → closing for emotional closers (high energy, low BPM)
        if is_club.any():
            e = df.loc[is_club, "energy"].astype(float)
            b = df.loc[is_club, "bpm"].astype(float)
            e_q85 = float(e.quantile(0.85))
            b_med = float(b.median())
            override = (
                is_club &
                (df["phase_v3"].eq("peak")) &
                (df["energy"].astype(float) >= e_q85) &
                (df["bpm"].astype(float) <= b_med)
            )
            df.loc[override, "phase_v3"] = "closing"

        print("\nPhase v3 distribution:")
        phase_counts = df["phase_v3"].value_counts(dropna=False)
        print(phase_counts.to_string())
        print("\nPhase v3 by classification:")
        print(df.groupby(["phase_v3", "classification"]).size().unstack(fill_value=0).to_string())

        if not args.no_db_update:
            id_column = resolved.get("id")
            key_column = id_column
            key_value_field = "id"
            if not key_column:
                key_column = resolved.get("file_path")
                key_value_field = "_file_path_key"
            if not key_column:
                raise SystemExit("No id or file_path column found; cannot update database without a key.")

            # Migrate classification_v2 column (non-destructive)
            if "classification_v2" not in columns:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN classification_v2 TEXT")
                con.commit()
                print("Added classification_v2 column to table.")

            update_sql = f"UPDATE {table} SET classification_v2=? WHERE {key_column}=?"
            updates = 0
            skipped = 0
            for _, row in df.iterrows():
                key_value = row.get(key_value_field)
                if key_value in (None, ""):
                    skipped += 1
                    continue
                cursor.execute(update_sql, (row.get("classification"), key_value))
                updates += 1
            con.commit()
            print(f"Updated classification_v2 for {updates} rows.")
            if skipped > 0:
                print(f"⚠️  Skipped {skipped} rows due to missing key (NULL or empty {key_value_field})")

            # TRIPWIRE: Verify no NULLs in classification_v2
            null_count = cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE classification_v2 IS NULL"
            ).fetchone()[0]
            if null_count > 0:
                print(f"\n❌ ERROR: {null_count} rows have NULL classification_v2!")
                print("    This suggests key mismatches or orphaned records.")
                print("    Sample of NULL rows:")
                nulls = cursor.execute(
                    f"SELECT {key_column}, file_path FROM {table} WHERE classification_v2 IS NULL LIMIT 10"
                ).fetchall()
                for row in nulls:
                    print(f"      {row}")
                raise SystemExit("Fix key mismatches and re-run.")

            # Migrate phase_v3 column (non-destructive)
            if "phase_v3" not in columns:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN phase_v3 TEXT")
                con.commit()
                print("Added phase_v3 column to table.")

            # Writeback phase_v3
            update_phase_sql = f"UPDATE {table} SET phase_v3=? WHERE {key_column}=?"
            phase_updates = 0
            for _, row in df.iterrows():
                key_value = row.get(key_value_field)
                if key_value in (None, ""):
                    continue
                cursor.execute(update_phase_sql, (row.get("phase_v3"), key_value))
                phase_updates += 1
            con.commit()
            print(f"Updated phase_v3 for {phase_updates} rows.")

            # TRIPWIRE: Verify no NULLs in phase_v3
            phase_null_count = cursor.execute(
                f"SELECT COUNT(*) FROM {table} WHERE phase_v3 IS NULL"
            ).fetchone()[0]
            if phase_null_count > 0:
                print(f"\n❌ ERROR: {phase_null_count} rows have NULL phase_v3!")
                raise SystemExit("Fix phase_v3 key mismatches and re-run.")

        csv_columns = ["artist", "title", "bpm", "energy", "genre", "classification", "phase_v3", "file_path"]
        df[csv_columns].to_csv(args.csv_out, index=False)
        print(f"\nCSV written: {args.csv_out}")

        playlist_dir = Path(args.playlist_dir).expanduser()
        playlist_dir.mkdir(parents=True, exist_ok=True)

        # v2 classification playlists
        playlist_map = {
            "club": "club_playlist.m3u8",
            "bar": "bar_playlist.m3u8",
            "remove": "remove_playlist.m3u8",
        }
        for label, filename in playlist_map.items():
            out_path = playlist_dir / filename
            _write_m3u8(out_path, df[df["classification"] == label])
            print(f"Playlist written: {out_path}")

        # Phase v3 playlists (set arc)
        phase_map = {
            "warmup": "phase_warmup.m3u8",
            "lift": "phase_lift.m3u8",
            "peak": "phase_peak.m3u8",
            "closing": "phase_closing.m3u8",
            "archive": "phase_archive.m3u8",
        }
        for label, filename in phase_map.items():
            out_path = playlist_dir / filename
            _write_m3u8(out_path, df[df["phase_v3"] == label])
            print(f"Playlist written: {out_path}")

        if not args.no_energy_playlists:
            energy_map = {
                "chill": "energy_chill.m3u8",
                "midtempo": "energy_midtempo.m3u8",
                "highenergy": "energy_highenergy.m3u8",
                "banger": "energy_banger.m3u8",
            }
            for label, filename in energy_map.items():
                out_path = playlist_dir / filename
                _write_m3u8(out_path, df[df["energy_bucket"] == label])
                print(f"Playlist written: {out_path}")

        print("\nSample rows (classification v2):")
        for label in ["club", "bar", "remove"]:
            _print_samples(df, "classification", label, args.sample_size)

        print("\nSample rows (phase v3):")
        for label in ["warmup", "lift", "peak", "closing", "archive"]:
            _print_samples(df, "phase_v3", label, args.sample_size)

        if not args.no_energy_playlists:
            print("\nSample rows (energy bucket):")
            for label in ["chill", "midtempo", "highenergy", "banger"]:
                _print_samples(df, "energy_bucket", label, args.sample_size)
    finally:
        con.close()


if __name__ == "__main__":
    main()
