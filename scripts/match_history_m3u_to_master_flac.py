#!/usr/bin/env python3
"""
Match EXTINF "Artist - Title" entries from an M3U/M3U8 playlist against the
master library FLAC inventory in the tagslut v3 SQLite DB, then emit:
  - Roon-importable .m3u8 playlists pointing at matched .flac paths
  - TuneMyMusic/SongShift-friendly plain-text playlists ("Artist - Title" per line)

This script avoids filesystem scanning of the master volume by using the DB.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence


_EXTINF_RE = re.compile(r"^#EXTINF:(?P<dur>-?\d+)\s*,\s*(?P<label>.*)\s*$")
_SPLIT_RE = re.compile(r"\s+-\s+")
_BRACKET_RE = re.compile(r"(\[[^\]]*\]|\([^)]*\))")
_ARTIST_SEP_RE = re.compile(r"\s*(?:,|;|&|\band\b|/|\+|\bx\b|\bvs\.?\b|\bwith\b|\bfeat\.?\b|\bft\.?\b|\bfeaturing\b)\s*", re.I)
_TITLE_NOISE_TAIL_RE = re.compile(
    r"\b(?:feat\.?|ft\.?|featuring|remaster(?:ed)?|radio\s+edit|original\s+mix|extended\s+mix)\b.*$",
    re.I,
)


def _norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("&", " and ")
    s = s.casefold()
    # Keep alnum/spaces; drop punctuation for robust matching.
    out = []
    for ch in s:
        if ch.isalnum() or ch.isspace():
            out.append(ch)
        else:
            out.append(" ")
    s = "".join(out)
    s = " ".join(s.split())
    return s


def _strip_brackets(s: str) -> str:
    # Remove bracketed qualifiers: (Radio Edit), (Original Mix), [Remastered], etc.
    return _BRACKET_RE.sub(" ", s)


def _title_key_full(s: str) -> str:
    return _norm_text(s)


def _title_key_core(s: str) -> str:
    # A more permissive title key to match across mix/remaster/feat suffixes.
    s = _strip_brackets(s)
    s = _TITLE_NOISE_TAIL_RE.sub("", s)
    return _norm_text(s)


def _artist_key(s: str) -> str:
    # Order-insensitive artist matching: normalize, split on common separators,
    # drop empties, then sort.
    raw = unicodedata.normalize("NFKD", s)
    raw = raw.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    raw = raw.replace("&", " and ")
    raw = raw.casefold()

    # Split before punctuation-stripping so commas/semicolons/etc aren't lost.
    parts_raw = [p.strip() for p in _ARTIST_SEP_RE.split(raw) if p and p.strip()]
    parts = [_norm_text(p) for p in parts_raw]
    parts = [p for p in parts if p and p not in {"various artists"}]
    parts = sorted(set(parts))
    return " | ".join(parts)


def _artist_tokens(s: str) -> set[str]:
    k = _artist_key(s)
    if not k:
        return set()
    return {p.strip() for p in k.split("|") if p.strip()}


def _artist_sim(a: str, b: str) -> float:
    # Combine string similarity with token-overlap containment.
    # This handles cases like:
    #   want: "Kalabrese, Palinstar"  vs row: "Kalabrese"
    ka = _artist_key(a)
    kb = _artist_key(b)
    r = _ratio(ka, kb)
    ta = _artist_tokens(a)
    tb = _artist_tokens(b)
    if ta and tb:
        inter = len(ta.intersection(tb))
        contain = inter / float(min(len(ta), len(tb)))
        r = max(r, contain)
    return r


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(a=a, b=b).ratio()


def _maybe_float(x: object) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


@dataclass(frozen=True)
class FlacRow:
    path: str
    artist: str
    title: str
    album: str
    duration_s: Optional[float]
    quality_rank: Optional[int]

    @property
    def ext(self) -> str:
        return Path(self.path).suffix.casefold()


def _iter_playlist_entries(m3u_path: Path) -> Iterator[tuple[int | None, str, str]]:
    """
    Yield (duration_s, label, source_path) tuples.
    For standard playlists, this comes in EXTINF + following path line pairs.
    """
    dur: int | None = None
    label: str = ""
    for raw in m3u_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTM3U"):
            continue
        m = _EXTINF_RE.match(line)
        if m:
            try:
                dur = int(m.group("dur"))
            except Exception:
                dur = None
            label = (m.group("label") or "").strip()
            continue
        if line.startswith("#"):
            continue
        yield (dur, label, line)
        dur = None
        label = ""


def _parse_artist_title(label: str) -> tuple[str, str]:
    """
    Best-effort split of "Artist - Title".
    Falls back to ("", label) if it doesn't look split-able.
    """
    parts = _SPLIT_RE.split(label, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", label.strip()


def _load_flac_inventory(conn: sqlite3.Connection, master_root: Path | None) -> list[FlacRow]:
    # The `files` table is the canonical v3 inventory (one row per path).
    # Prefer measured duration if present, else canonical duration, else raw duration.
    # Filter to FLAC and (optionally) to the master volume path prefix.
    where = "LOWER(path) LIKE '%.flac'"
    params: list[object] = []
    if master_root is not None:
        where += " AND path LIKE ?"
        params.append(str(master_root) + "%")

    q = f"""
        SELECT
          path,
          COALESCE(canonical_artist, '') AS canonical_artist,
          COALESCE(canonical_title, '')  AS canonical_title,
          COALESCE(canonical_album, '')  AS canonical_album,
          metadata_json,
          duration_measured_ms,
          canonical_duration,
          duration,
          quality_rank
        FROM files
        WHERE {where}
    """
    rows: list[FlacRow] = []
    for r in conn.execute(q, params):
        # Prefer canonical_* if present, else fall back to raw tag fields in metadata_json.
        artist = str(r[1] or "").strip()
        title = str(r[2] or "").strip()
        album = str(r[3] or "").strip()
        meta_raw = r[4]
        if meta_raw and (not artist or not title):
            try:
                meta = json.loads(meta_raw)
            except Exception:
                meta = {}
            if not artist:
                a = meta.get("artist") or meta.get("albumartist") or ""
                if isinstance(a, list):
                    a = ", ".join(str(x) for x in a if x)
                artist = str(a or "").strip()
            if not title:
                t = meta.get("title") or ""
                if isinstance(t, list):
                    t = " / ".join(str(x) for x in t if x)
                title = str(t or "").strip()
            if not album:
                al = meta.get("album") or ""
                if isinstance(al, list):
                    al = " / ".join(str(x) for x in al if x)
                album = str(al or "").strip()

        duration_s: Optional[float] = None
        measured_ms = r[5]
        if measured_ms is not None:
            try:
                duration_s = float(measured_ms) / 1000.0
            except Exception:
                duration_s = None
        if duration_s is None:
            duration_s = _maybe_float(r[6])
        if duration_s is None:
            duration_s = _maybe_float(r[7])
        rows.append(
            FlacRow(
                path=str(r[0]),
                artist=artist,
                title=title,
                album=album,
                duration_s=duration_s,
                quality_rank=(int(r[8]) if r[8] is not None else None),
            )
        )
    return rows


def _choose_best(
    candidates: Sequence[FlacRow],
    want_artist: str,
    want_title: str,
    want_duration_s: int | None,
) -> FlacRow | None:
    if not candidates:
        return None

    na = want_artist
    nt_full = _title_key_full(want_title)
    nt_core = _title_key_core(want_title)

    def _duration_delta(row: FlacRow) -> float:
        if want_duration_s is None or row.duration_s is None:
            return 999999.0
        return abs(float(want_duration_s) - float(row.duration_s))

    def _score(row: FlacRow) -> tuple[float, float, int, str]:
        # Lower is better.
        # Primary: title similarity (full/core), then artist similarity (order-insensitive),
        # then duration, then quality rank.
        ra = _artist_sim(na, row.artist)
        rt_full = _ratio(nt_full, _title_key_full(row.title))
        rt_core = _ratio(nt_core, _title_key_core(row.title))
        rt = max(rt_full, rt_core)
        sim = (0.75 * rt) + (0.25 * ra)
        dur = _duration_delta(row)
        q = row.quality_rank if row.quality_rank is not None else 999
        # Convert similarity to "distance"
        return (1.0 - sim, dur, q, row.path.casefold())

    best = min(candidates, key=_score)

    # Reject if it's clearly the wrong track (avoid accidental cross-links).
    ba = _artist_sim(na, best.artist)
    bt_full = _ratio(nt_full, _title_key_full(best.title))
    bt_core = _ratio(nt_core, _title_key_core(best.title))
    bt = max(bt_full, bt_core)
    if bt < 0.66:
        return None
    if na and ba < 0.50:
        return None
    if want_duration_s is not None and best.duration_s is not None:
        # If artist+title are near-exact, accept even when the edit/version differs.
        if bt >= 0.92 and ba >= 0.85:
            return best
        if abs(float(want_duration_s) - float(best.duration_s)) > 20.0:
            # Duration mismatch large enough to be suspicious.
            return None
    return best


def _build_indexes(
    rows: Iterable[FlacRow],
) -> tuple[
    dict[tuple[str, str], list[FlacRow]],
    dict[tuple[str, str], list[FlacRow]],
    dict[str, list[FlacRow]],
    dict[str, list[FlacRow]],
]:
    by_artist_title: dict[tuple[str, str], list[FlacRow]] = {}
    by_artist_title_core: dict[tuple[str, str], list[FlacRow]] = {}
    by_title: dict[str, list[FlacRow]] = {}
    by_title_core: dict[str, list[FlacRow]] = {}
    for r in rows:
        ka = _norm_text(r.artist)
        kt = _title_key_full(r.title)
        ktc = _title_key_core(r.title)
        by_artist_title.setdefault((ka, kt), []).append(r)
        by_artist_title_core.setdefault((ka, ktc), []).append(r)
        by_title.setdefault(kt, []).append(r)
        by_title_core.setdefault(ktc, []).append(r)
    return by_artist_title, by_artist_title_core, by_title, by_title_core


def _resolve_track(
    by_artist_title: dict[tuple[str, str], list[FlacRow]],
    by_artist_title_core: dict[tuple[str, str], list[FlacRow]],
    by_title: dict[str, list[FlacRow]],
    by_title_core: dict[str, list[FlacRow]],
    artist: str,
    title: str,
    duration_s: int | None,
) -> FlacRow | None:
    ka = _norm_text(artist)
    kt = _title_key_full(title)
    ktc = _title_key_core(title)

    # 1) Exact artist+title match (normalized)
    direct = by_artist_title.get((ka, kt), [])
    best = _choose_best(direct, artist, title, duration_s)
    if best is not None:
        return best

    # 1b) Exact artist+core-title match
    direct_core = by_artist_title_core.get((ka, ktc), [])
    best = _choose_best(direct_core, artist, title, duration_s)
    if best is not None:
        return best

    # 2) Title-only exact match; choose by artist similarity + duration + quality
    title_only = by_title.get(kt, [])
    best = _choose_best(title_only, artist, title, duration_s)
    if best is not None:
        return best

    # 2b) Title-only exact core-title match
    title_only_core = by_title_core.get(ktc, [])
    best = _choose_best(title_only_core, artist, title, duration_s)
    if best is not None:
        return best

    # 3) Fuzzy within a constrained candidate set (titles that share a few tokens).
    want_tokens = set(ktc.split()) or set(kt.split())
    if not want_tokens:
        return None
    pool: list[FlacRow] = []
    for tkey, rows in by_title.items():
        # Compare against core title tokens for better recall.
        t_tokens = set(_title_key_core(tkey).split()) or set(tkey.split())
        if not t_tokens:
            continue
        # Require some overlap to avoid O(N) fuzz over the whole library.
        if len(want_tokens.intersection(t_tokens)) >= max(2, min(4, len(want_tokens) // 2)):
            pool.extend(rows)
    return _choose_best(pool, artist, title, duration_s)


def _write_roon_m3u8(out_path: Path, items: Sequence[tuple[int | None, str, FlacRow]]) -> None:
    lines: list[str] = ["#EXTM3U"]
    for dur_s, label, row in items:
        dur = int(dur_s) if dur_s is not None else -1
        lines.append(f"#EXTINF:{dur},{label}")
        lines.append(row.path)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_text_playlist(out_path: Path, labels: Sequence[str]) -> None:
    # Plain "Artist - Title" lines; suitable for text-import matchers.
    out_path.write_text("\n".join(labels) + "\n", encoding="utf-8")


def _write_unmatched(out_path: Path, items: Sequence[tuple[int | None, str, str]]) -> None:
    lines: list[str] = []
    for dur_s, label, src in items:
        dur = str(int(dur_s)) if dur_s is not None else ""
        lines.append(f"{label}\t{dur}\t{src}")
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("TAGSLUT_DB", ""), help="tagslut v3 sqlite db path (default: $TAGSLUT_DB)")
    ap.add_argument(
        "--master-root",
        default=os.environ.get("MASTER_LIBRARY", ""),
        help="Master library root path prefix to restrict matches (default: $MASTER_LIBRARY)",
    )
    ap.add_argument("--out-dir", default="output", help="Output directory (default: output/ in repo)")
    ap.add_argument("playlists", nargs="+", help="Input .m3u/.m3u8 paths")
    args = ap.parse_args(list(argv) if argv is not None else None)

    db_path = Path(args.db).expanduser() if args.db else None
    if not db_path or not db_path.exists():
        raise SystemExit(f"DB not found (set --db or TAGSLUT_DB): {db_path}")

    master_root = Path(args.master_root).expanduser().resolve() if args.master_root else None
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        flacs = _load_flac_inventory(conn, master_root)
    finally:
        conn.close()

    by_artist_title, by_artist_title_core, by_title, by_title_core = _build_indexes(flacs)

    total = 0
    matched = 0
    for pl in args.playlists:
        in_path = Path(pl).expanduser().resolve()
        if not in_path.exists():
            raise SystemExit(f"Playlist not found: {in_path}")

        roon_items: list[tuple[int | None, str, FlacRow]] = []
        text_lines: list[str] = []
        unmatched: list[tuple[int | None, str, str]] = []
        for dur_s, label, src in _iter_playlist_entries(in_path):
            artist, title = _parse_artist_title(label)
            clean_label = f"{artist} - {title}".strip(" -")
            text_lines.append(clean_label)
            total += 1
            row = _resolve_track(by_artist_title, by_artist_title_core, by_title, by_title_core, artist, title, dur_s)
            if row is None:
                unmatched.append((dur_s, clean_label, src))
                continue
            matched += 1
            roon_items.append((dur_s, clean_label, row))

        base = in_path.stem
        _write_roon_m3u8(out_dir / f"{base} (Roon).m3u8", roon_items)
        _write_text_playlist(out_dir / f"{base} (TuneMyMusic).txt", text_lines)
        _write_unmatched(out_dir / f"{base} (Unmatched).tsv", unmatched)

    print(f"Tracks: {matched}/{total} matched to master FLACs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
