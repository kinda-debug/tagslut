#!/usr/bin/env python3
"""
Rebuild one playlist from Apple export files plus local MP3/FLAC inventory.

What it does:
  1. Reads one Apple playlist from:
       - an Apple Music playlist text export (.txt, tab-separated)
       - the paired Apple Music playlist CSV export (.csv, with ISRC values)
  2. Tries to resolve MP3s in order using:
       - embedded ISRC tags in a candidate M3U/M3U8 playlist such as keeps.m3u8
       - exact / normalized label matching against that playlist
       - fuzzy fallback against an MP3 library root
       - optional manual overrides from a TSV file
  3. Writes:
       - "<name> (MP3).m3u8"
       - "<name> (MP3 unresolved).tsv"
  4. Calls scripts/match_history_m3u_to_master_flac.py to derive:
       - "<name> (FLAC).m3u8"
       - "<name> (FLAC unresolved).tsv"

This script is read-only with respect to the tagslut DB. It does not insert or
update any DB links.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterator, Optional

from mutagen import File


_EXTINF_RE = re.compile(r"^#EXTINF:(?P<dur>-?\d+)\s*,\s*(?P<label>.*)\s*$")
_SPLIT_RE = re.compile(r"\s+[–-]\s+")
_TRACKNUM_SEG_RE = re.compile(r"^\d+[A-Za-z.\-]*$")
_BRACKET_RE = re.compile(r"(\[[^\]]*\]|\([^)]*\))")
_FEAT_RE = re.compile(r"\b(feat|featuring|with|ft)\b.*$", re.I)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_SPACE_RE = re.compile(r"\s+")
_MIX_RE = re.compile(
    r"\b("
    r"original mix|extended mix|extended|radio edit|edit|mixed|mix|remix|dub|"
    r"version|vocal|instrumental|remastered|reversion|club|miks|diskomiks"
    r")\b",
    re.I,
)
_ISRC_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{3}\d{7}\b", re.I)


@dataclass(frozen=True)
class PlaylistRow:
    artist: str
    title: str
    album: str
    duration_s: int
    isrc: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.artist, self.title)

    @property
    def label(self) -> str:
        return f"{self.artist} - {self.title}"


@dataclass(frozen=True)
class CandidateEntry:
    path: str
    artist: str
    title: str
    album: str
    duration_s: Optional[int]
    isrc: str
    source: str

    @property
    def label(self) -> str:
        return f"{self.artist} - {self.title}".strip(" -")

    @property
    def artist_norm(self) -> str:
        return _norm_artist(self.artist)

    @property
    def title_full(self) -> str:
        return _title_full(self.title)

    @property
    def title_core(self) -> str:
        return _title_core(self.title)


def _fold(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(ch))


def _norm(text: str) -> str:
    text = _fold(text).lower().replace("&", " and ")
    text = _NON_ALNUM_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _norm_artist(text: str) -> str:
    return _norm(_FEAT_RE.sub("", _fold(text)))


def _title_full(text: str) -> str:
    return _norm(text)


def _title_core(text: str) -> str:
    text = _fold(text)
    text = _BRACKET_RE.sub(" ", text)
    text = _FEAT_RE.sub("", text)
    text = _MIX_RE.sub(" ", text)
    return _norm(text)


def _core_tokens(text: str) -> set[str]:
    return {token for token in _title_core(text).split() if len(token) >= 4}


def _artist_score(want: str, have: str) -> float:
    a = _norm_artist(want)
    b = _norm_artist(have)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    toks_a = set(a.split())
    toks_b = set(b.split())
    overlap = len(toks_a & toks_b) / float(max(1, min(len(toks_a), len(toks_b)))) if toks_a and toks_b else 0.0
    return max(overlap, SequenceMatcher(a=a, b=b).ratio())


def _title_scores(want: str, have: str) -> tuple[float, float]:
    want_full = _title_full(want)
    have_full = _title_full(have)
    want_core = _title_core(want)
    have_core = _title_core(have)

    full_ratio = SequenceMatcher(a=want_full, b=have_full).ratio() if want_full and have_full else 0.0
    core_ratio = SequenceMatcher(a=want_core, b=have_core).ratio() if want_core and have_core else 0.0
    if want_core and have_core and (want_core.startswith(have_core) or have_core.startswith(want_core)):
        core_ratio = max(core_ratio, 0.98)

    want_tokens = set(want_core.split())
    have_tokens = set(have_core.split())
    coverage = len(want_tokens & have_tokens) / float(len(want_tokens)) if want_tokens else 1.0
    return max(full_ratio, core_ratio), coverage


def _duration_score(want: int, have: Optional[int]) -> float:
    if not want or not have:
        return 0.0
    diff = abs(want - have)
    if diff <= 2:
        return 1.0
    if diff <= 5:
        return 0.8
    if diff <= 10:
        return 0.6
    if diff <= 20:
        return 0.35
    if diff <= 40:
        return 0.15
    if diff <= 90:
        return 0.05
    return -0.2


def _read_playlist_rows(apple_txt: Path, apple_csv: Path) -> list[PlaylistRow]:
    with apple_txt.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        txt_rows = list(csv.DictReader(handle, dialect="excel-tab"))
    with apple_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    if len(txt_rows) != len(csv_rows):
        raise SystemExit(f"Row mismatch between {apple_txt} ({len(txt_rows)}) and {apple_csv} ({len(csv_rows)})")

    rows: list[PlaylistRow] = []
    for txt_row, csv_row in zip(txt_rows, csv_rows):
        rows.append(
            PlaylistRow(
                artist=(txt_row.get("Artist") or "").strip(),
                title=(txt_row.get("Name") or "").strip(),
                album=(txt_row.get("Album") or "").strip(),
                duration_s=int(((txt_row.get("Time") or "0").strip() or "0")),
                isrc=(csv_row.get("ISRC") or "").strip().upper(),
            )
        )
    return rows


def _playlist_name(rows: list[PlaylistRow], apple_csv: Path) -> str:
    with apple_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    for row in csv_rows:
        name = (row.get("Playlist name") or "").strip()
        if name:
            return name
    stem = apple_txt_stem = apple_csv.stem
    return apple_txt_stem


def _safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {" ", "-", "_"} else "_" for ch in text).strip() or "playlist"


def _iter_m3u_entries(path: Path) -> Iterator[tuple[Optional[int], str, str]]:
    duration_s: Optional[int] = None
    label = ""
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#EXTM3U"):
            continue
        match = _EXTINF_RE.match(line)
        if match:
            try:
                duration_s = int(match.group("dur"))
            except Exception:
                duration_s = None
            label = (match.group("label") or "").strip()
            continue
        if line.startswith("#"):
            continue
        yield duration_s, label, line
        duration_s = None
        label = ""


def _parse_label(label: str) -> tuple[str, str]:
    parts = _SPLIT_RE.split(label, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", label.strip()


def _extract_isrc_and_duration(path: str, cache: dict[str, tuple[str, Optional[int]]]) -> tuple[str, Optional[int]]:
    cached = cache.get(path)
    if cached is not None:
        return cached

    isrc = ""
    duration_s: Optional[int] = None
    try:
        audio = File(path, easy=False)
    except Exception:
        audio = None

    if audio is not None:
        try:
            if getattr(audio, "info", None) is not None:
                duration_s = int(round(float(audio.info.length)))
        except Exception:
            duration_s = None
        tags = getattr(audio, "tags", None)
        if tags:
            for key, value in tags.items():
                if "isrc" not in str(key).lower() and "tsrc" not in str(key).lower():
                    continue
                values = value if isinstance(value, list) else [value]
                for item in values:
                    payload = getattr(item, "text", item)
                    payloads = payload if isinstance(payload, list) else [payload]
                    for chunk in payloads:
                        match = _ISRC_RE.search(str(chunk))
                        if match:
                            isrc = match.group(0).upper()
                            cache[path] = (isrc, duration_s)
                            return cache[path]

    cache[path] = (isrc, duration_s)
    return cache[path]


def _parse_path(path: str) -> tuple[str, str, str]:
    node = Path(path)
    stem = node.stem
    parts = [part.strip() for part in _SPLIT_RE.split(stem) if part.strip()]
    artist = ""
    title = stem

    if parts:
        if _TRACKNUM_SEG_RE.match(parts[0]) or parts[0].replace(".", "").isdigit():
            if len(parts) >= 3:
                artist = parts[1]
                title = " - ".join(parts[2:])
            elif len(parts) == 2:
                title = parts[1]
        elif len(parts) >= 2:
            artist = parts[0]
            title = " - ".join(parts[1:])

    album = re.sub(r"^\(\d{4}\)\s*", "", node.parent.name).strip()
    if not artist:
        artist = node.parent.parent.name or node.parent.name
    return artist, title, album


def _load_keeps_entries(path: Path, cache: dict[str, tuple[str, Optional[int]]]) -> list[CandidateEntry]:
    entries: list[CandidateEntry] = []
    for extinf_duration, label, entry_path in _iter_m3u_entries(path):
        artist, title = _parse_label(label)
        isrc, tag_duration = _extract_isrc_and_duration(entry_path, cache)
        entries.append(
            CandidateEntry(
                path=entry_path,
                artist=artist,
                title=title,
                album=Path(entry_path).parent.name,
                duration_s=tag_duration if tag_duration is not None else extinf_duration,
                isrc=isrc,
                source="keeps",
            )
        )
    return entries


def _load_library_candidates(root: Path) -> list[CandidateEntry]:
    entries: list[CandidateEntry] = []
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if not filename.lower().endswith(".mp3"):
                continue
            full_path = str(Path(dirpath) / filename)
            artist, title, album = _parse_path(full_path)
            entries.append(
                CandidateEntry(
                    path=full_path,
                    artist=artist,
                    title=title,
                    album=album,
                    duration_s=None,
                    isrc="",
                    source="library",
                )
            )
    return entries


def _load_manual_overrides(path: Optional[Path]) -> dict[tuple[str, str], str]:
    if path is None:
        return {}
    overrides: dict[tuple[str, str], str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"artist", "title", "path"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise SystemExit(f"{path} must be a TSV with columns: artist, title, path")
        for row in reader:
            artist = (row.get("artist") or "").strip()
            title = (row.get("title") or "").strip()
            candidate_path = (row.get("path") or "").strip()
            if artist and title and candidate_path:
                overrides[(artist, title)] = candidate_path
    return overrides


def _build_lookup(entries: list[CandidateEntry]) -> tuple[dict[str, CandidateEntry], dict[tuple[str, str], list[CandidateEntry]]]:
    by_isrc: dict[str, CandidateEntry] = {}
    by_artist_core: dict[tuple[str, str], list[CandidateEntry]] = defaultdict(list)
    for entry in entries:
        if entry.isrc and entry.isrc not in by_isrc:
            by_isrc[entry.isrc] = entry
        by_artist_core[(entry.artist_norm, entry.title_core)].append(entry)
    return by_isrc, by_artist_core


def _match_keep_row(
    row: PlaylistRow,
    keeps_entries: list[CandidateEntry],
    by_keep_isrc: dict[str, CandidateEntry],
    by_keep_artist_core: dict[tuple[str, str], list[CandidateEntry]],
) -> tuple[Optional[CandidateEntry], str]:
    if row.isrc and row.isrc in by_keep_isrc:
        return by_keep_isrc[row.isrc], "keeps_isrc"

    exact = by_keep_artist_core.get((_norm_artist(row.artist), _title_core(row.title)), [])
    if len(exact) == 1:
        return exact[0], "keeps_core"
    if len(exact) > 1:
        ranked = sorted(
            exact,
            key=lambda entry: (
                _duration_score(row.duration_s, entry.duration_s),
                SequenceMatcher(a=_title_full(row.title), b=entry.title_full).ratio(),
            ),
            reverse=True,
        )
        return ranked[0], "keeps_core"

    row_tokens = _core_tokens(row.title)
    ranked: list[tuple[float, CandidateEntry]] = []
    for entry in keeps_entries:
        artist_score = _artist_score(row.artist, entry.artist)
        if artist_score < 0.75:
            continue
        title_score, coverage = _title_scores(row.title, entry.title)
        if coverage < 1.0 or title_score < 0.82:
            continue
        score = artist_score * 0.45 + title_score * 0.35 + coverage * 0.15 + _duration_score(row.duration_s, entry.duration_s) * 0.05
        ranked.append((score, entry))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked:
        best_score, best_entry = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else -1.0
        if best_score >= 0.88 or (best_score >= 0.84 and best_score - second_score >= 0.05):
            return best_entry, "keeps_fuzzy"

    return None, ""


def _match_library_row(
    row: PlaylistRow,
    library_entries: list[CandidateEntry],
    overrides: dict[tuple[str, str], str],
    cache: dict[str, tuple[str, Optional[int]]],
) -> tuple[Optional[CandidateEntry], str]:
    override_path = overrides.get(row.key)
    if override_path:
        override = Path(override_path).expanduser()
        if override.exists():
            isrc, duration_s = _extract_isrc_and_duration(str(override), cache)
            artist, title, album = _parse_path(str(override))
            return (
                CandidateEntry(
                    path=str(override),
                    artist=artist,
                    title=title,
                    album=album,
                    duration_s=duration_s,
                    isrc=isrc,
                    source="manual",
                ),
                "manual_override",
            )

    ranked: list[tuple[float, CandidateEntry]] = []
    for entry in library_entries:
        artist_score = _artist_score(row.artist, entry.artist)
        if artist_score < 0.45:
            continue
        title_score, coverage = _title_scores(row.title, entry.title)
        if coverage < 1.0 or title_score < 0.72:
            continue
        isrc, duration_s = _extract_isrc_and_duration(entry.path, cache)
        adjusted_entry = CandidateEntry(
            path=entry.path,
            artist=entry.artist,
            title=entry.title,
            album=entry.album,
            duration_s=duration_s,
            isrc=isrc,
            source=entry.source,
        )
        exact_isrc = 1.0 if row.isrc and isrc == row.isrc else 0.0
        score = (
            artist_score * 0.35
            + title_score * 0.20
            + coverage * 0.25
            + _duration_score(row.duration_s, duration_s) * 0.05
            + exact_isrc * 0.40
        )
        ranked.append((score, adjusted_entry))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked:
        best_score, best_entry = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else -1.0
        exact_isrc = bool(row.isrc and best_entry.isrc == row.isrc)
        if exact_isrc or best_score >= 0.90 or (best_score >= 0.84 and best_score - second_score >= 0.05):
            return best_entry, "library_fuzzy"

    return None, ""


def _write_mp3_playlist(path: Path, resolved: list[tuple[PlaylistRow, CandidateEntry]]) -> None:
    lines = ["#EXTM3U"]
    for row, entry in resolved:
        lines.append(f"#EXTINF:{row.duration_s},{row.label}")
        lines.append(entry.path)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_unresolved(path: Path, unresolved: list[PlaylistRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["artist", "title", "album", "duration_s", "isrc"])
        for row in unresolved:
            writer.writerow([row.artist, row.title, row.album, row.duration_s, row.isrc])


def _run_flac_matcher(repo_root: Path, db_path: Path, master_root: Path, mp3_m3u: Path, flac_out: Path, flac_unresolved: Path) -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="rebuild_playlist_flac_"))
    try:
        cmd = [
            "python3",
            str(repo_root / "scripts" / "match_history_m3u_to_master_flac.py"),
            "--db",
            str(db_path),
            "--master-root",
            str(master_root),
            "--out-dir",
            str(temp_dir),
            str(mp3_m3u),
        ]
        result = subprocess.run(cmd, cwd=str(repo_root), text=True, capture_output=True)
        if result.returncode != 0:
            raise SystemExit(result.stderr.strip() or result.stdout.strip() or "FLAC matcher failed")

        base = mp3_m3u.stem
        src_flac = temp_dir / f"{base} (Roon).m3u8"
        src_unmatched = temp_dir / f"{base} (Unmatched).tsv"
        if flac_out.exists():
            flac_out.unlink()
        if flac_unresolved.exists():
            flac_unresolved.unlink()
        shutil.move(str(src_flac), str(flac_out))
        shutil.move(str(src_unmatched), str(flac_unresolved))
    finally:
        for extra in temp_dir.glob("*"):
            if extra.is_file():
                extra.unlink()
        temp_dir.rmdir()

    return sum(1 for line in flac_out.read_text(encoding="utf-8", errors="replace").splitlines() if line and not line.startswith("#"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apple-txt", required=True, help="Apple playlist text export (.txt)")
    parser.add_argument("--apple-csv", required=True, help="Apple playlist CSV export (.csv)")
    parser.add_argument("--keeps", required=True, help="Candidate MP3 M3U/M3U8, for example keeps.m3u8")
    parser.add_argument("--mp3-root", required=True, help="MP3 library root used for fuzzy fallback")
    parser.add_argument("--db", default=os.environ.get("TAGSLUT_DB", ""), help="tagslut DB path (read-only use)")
    parser.add_argument("--master-root", default=os.environ.get("MASTER_LIBRARY", ""), help="Master FLAC root")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1], help="Repo root containing scripts/match_history_m3u_to_master_flac.py")
    parser.add_argument("--out-dir", default=".", help="Output directory")
    parser.add_argument("--playlist-name", default="", help="Optional output name override")
    parser.add_argument("--manual-overrides-tsv", default="", help="Optional TSV with columns: artist, title, path")
    args = parser.parse_args()

    apple_txt = Path(args.apple_txt).expanduser().resolve()
    apple_csv = Path(args.apple_csv).expanduser().resolve()
    keeps = Path(args.keeps).expanduser().resolve()
    mp3_root = Path(args.mp3_root).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve() if args.db else None
    master_root = Path(args.master_root).expanduser().resolve() if args.master_root else None
    repo_root = Path(args.repo_root).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    overrides_path = Path(args.manual_overrides_tsv).expanduser().resolve() if args.manual_overrides_tsv else None

    if not apple_txt.exists():
        raise SystemExit(f"Playlist text export not found: {apple_txt}")
    if not apple_csv.exists():
        raise SystemExit(f"Playlist CSV export not found: {apple_csv}")
    if not keeps.exists():
        raise SystemExit(f"Keeps playlist not found: {keeps}")
    if not mp3_root.exists():
        raise SystemExit(f"MP3 root not found: {mp3_root}")
    if db_path is None or not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")
    if master_root is None or not master_root.exists():
        raise SystemExit(f"Master root not found: {master_root}")

    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_playlist_rows(apple_txt, apple_csv)
    playlist_name = args.playlist_name.strip() or _playlist_name(rows, apple_csv)
    safe_name = _safe_name(playlist_name)

    tag_cache: dict[str, tuple[str, Optional[int]]] = {}
    keeps_entries = _load_keeps_entries(keeps, tag_cache)
    by_keep_isrc, by_keep_artist_core = _build_lookup(keeps_entries)
    library_entries = _load_library_candidates(mp3_root)
    overrides = _load_manual_overrides(overrides_path)

    resolved: list[tuple[PlaylistRow, CandidateEntry]] = []
    unresolved: list[PlaylistRow] = []
    method_counts: dict[str, int] = defaultdict(int)

    for row in rows:
        entry, method = _match_keep_row(row, keeps_entries, by_keep_isrc, by_keep_artist_core)
        if entry is None:
            entry, method = _match_library_row(row, library_entries, overrides, tag_cache)
        if entry is None:
            unresolved.append(row)
            continue
        resolved.append((row, entry))
        method_counts[method] += 1

    mp3_out = out_dir / f"{safe_name} (MP3).m3u8"
    mp3_unresolved = out_dir / f"{safe_name} (MP3 unresolved).tsv"
    flac_out = out_dir / f"{safe_name} (FLAC).m3u8"
    flac_unresolved = out_dir / f"{safe_name} (FLAC unresolved).tsv"

    _write_mp3_playlist(mp3_out, resolved)
    _write_unresolved(mp3_unresolved, unresolved)
    flac_count = _run_flac_matcher(repo_root, db_path, master_root, mp3_out, flac_out, flac_unresolved)

    print(f"playlist_name={playlist_name}")
    print(f"rows={len(rows)}")
    print(f"mp3_matched={len(resolved)}")
    print(f"mp3_unresolved={len(unresolved)}")
    print(f"flac_matched={flac_count}")
    print(f"methods={dict(sorted(method_counts.items()))}")
    print(f"mp3_out={mp3_out}")
    print(f"mp3_unresolved_out={mp3_unresolved}")
    print(f"flac_out={flac_out}")
    print(f"flac_unresolved_out={flac_unresolved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
