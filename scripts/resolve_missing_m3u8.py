#!/usr/bin/env python3
"""
Given:
  - all.m3u8: a large playlist representing what's already present/known
  - missing.m3u8: a playlist of items that appear to be missing

This script:
  1) Detects which "missing" entries are duplicates (already in all, or duplicated within missing).
     Writes an M3U8 + TSV you can use to archive/handle those duplicate entries.
  2) For the remaining unique "missing" entries, resolves them to master-library FLACs using the
     tagslut v3 SQLite inventory DB (no filesystem scanning), and writes an M3U8.

Outputs (default: output/):
  - <missing-stem> (Duplicates).m3u8
  - <missing-stem> (Duplicates).tsv
  - <missing-stem> (Unique Located).m3u8
  - <missing-stem> (Unique Located).tsv
  - <missing-stem> (Unique Unresolved).tsv
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


_EXTINF_RE = re.compile(r"^#EXTINF:(?P<dur>[^,]*?)\s*,\s*(?P<label>.*)\s*$")
_SPLIT_RE = re.compile(r"\s+-\s+")
_BRACKET_RE = re.compile(r"(\[[^\]]*\]|\([^)]*\))")
_TITLE_NOISE_TAIL_RE = re.compile(
    r"\b(?:feat\.?|ft\.?|featuring|remaster(?:ed)?|radio\s+edit|original\s+mix|extended\s+mix)\b.*$",
    re.I,
)
_ARTIST_SEP_RE = re.compile(
    r"\s*(?:,|;|&|\band\b|/|\+|\bx\b|\bvs\.?\b|\bwith\b|\bfeat\.?\b|\bft\.?\b|\bfeaturing\b)\s*",
    re.I,
)

_AUDIO_EXTS = (".flac", ".mp3", ".m4a", ".aac", ".wav", ".aiff", ".aif", ".alac", ".ogg", ".opus")


def _norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = s.replace("&", " and ")
    s = s.casefold()
    out = []
    for ch in s:
        if ch.isalnum() or ch.isspace():
            out.append(ch)
        else:
            out.append(" ")
    s = "".join(out)
    return " ".join(s.split())


def _strip_brackets(s: str) -> str:
    return _BRACKET_RE.sub(" ", s)


def _title_key_full(s: str) -> str:
    return _norm_text(s)


def _title_key_core(s: str) -> str:
    s = _strip_brackets(s)
    s = _TITLE_NOISE_TAIL_RE.sub("", s)
    return _norm_text(s)


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(a=a, b=b).ratio()


def _artist_key(s: str) -> str:
    raw = unicodedata.normalize("NFKD", s)
    raw = raw.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    raw = raw.replace("&", " and ")
    raw = raw.casefold()

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


def _maybe_float(x: object) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except Exception:
        return None


def _parse_extinf_duration(raw: str) -> int | None:
    s = (raw or "").strip()
    if not s:
        return None
    if s.casefold() == "nan":
        return None
    try:
        return int(float(s))
    except Exception:
        return None


@dataclass(frozen=True)
class PlaylistEntry:
    dur_s: int | None
    label: str
    src_path: str
    artist: str
    title: str

    @property
    def key(self) -> tuple[str, str]:
        return (_artist_key(self.artist), _title_key_core(self.title))


def _parse_artist_title(label: str) -> tuple[str, str]:
    parts = _SPLIT_RE.split(label, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", label.strip()


def _read_m3u_entries(path: Path) -> list[PlaylistEntry]:
    dur: int | None = None
    label: str = ""
    out: list[PlaylistEntry] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTM3U"):
            continue
        m = _EXTINF_RE.match(line)
        if m:
            dur = _parse_extinf_duration(m.group("dur") or "")
            label = (m.group("label") or "").strip()
            continue
        if line.startswith("#"):
            continue
        artist, title = _parse_artist_title(label)
        clean_label = f"{artist} - {title}".strip(" -")
        out.append(
            PlaylistEntry(
                dur_s=dur,
                label=clean_label,
                src_path=line,
                artist=artist,
                title=title,
            )
        )
        dur = None
        label = ""
    return out


@dataclass(frozen=True)
class AssetRow:
    path: str
    artist: str
    title: str
    duration_s: Optional[float]
    quality_rank: Optional[int]


def _load_inventory(
    conn: sqlite3.Connection,
    master_root: Path | None,
    exts: Sequence[str],
) -> list[AssetRow]:
    ext_where = " OR ".join(["LOWER(path) LIKE ?"] * len(exts))
    where = f"({ext_where})"
    params: list[object] = []
    for ext in exts:
        params.append("%" + ext.casefold())
    if master_root is not None:
        where += " AND path LIKE ?"
        params.append(str(master_root) + "%")

    q = f"""
        SELECT
          path,
          COALESCE(canonical_artist, '') AS canonical_artist,
          COALESCE(canonical_title, '')  AS canonical_title,
          metadata_json,
          duration_measured_ms,
          canonical_duration,
          duration,
          quality_rank
        FROM files
        WHERE {where}
    """
    rows: list[AssetRow] = []
    for r in conn.execute(q, params):
        artist = str(r[1] or "").strip()
        title = str(r[2] or "").strip()
        meta_raw = r[3]
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

        duration_s: Optional[float] = None
        measured_ms = r[4]
        if measured_ms is not None:
            try:
                duration_s = float(measured_ms) / 1000.0
            except Exception:
                duration_s = None
        if duration_s is None:
            duration_s = _maybe_float(r[5])
        if duration_s is None:
            duration_s = _maybe_float(r[6])

        rows.append(
            AssetRow(
                path=str(r[0]),
                artist=artist,
                title=title,
                duration_s=duration_s,
                quality_rank=(int(r[7]) if r[7] is not None else None),
            )
        )
    return rows


def _build_flac_indexes(
    rows: Iterable[AssetRow],
) -> tuple[
    dict[tuple[str, str], list[AssetRow]],
    dict[tuple[str, str], list[AssetRow]],
    dict[str, list[AssetRow]],
    dict[str, list[AssetRow]],
]:
    by_artist_title: dict[tuple[str, str], list[AssetRow]] = {}
    by_artist_title_core: dict[tuple[str, str], list[AssetRow]] = {}
    by_title: dict[str, list[AssetRow]] = {}
    by_title_core: dict[str, list[AssetRow]] = {}

    for r in rows:
        ka = _norm_text(r.artist)
        kt = _title_key_full(r.title)
        ktc = _title_key_core(r.title)
        by_artist_title.setdefault((ka, kt), []).append(r)
        by_artist_title_core.setdefault((ka, ktc), []).append(r)
        by_title.setdefault(kt, []).append(r)
        by_title_core.setdefault(ktc, []).append(r)
    return by_artist_title, by_artist_title_core, by_title, by_title_core


def _choose_best_flac(
    candidates: Sequence[AssetRow],
    want_artist: str,
    want_title: str,
    want_duration_s: int | None,
) -> AssetRow | None:
    if not candidates:
        return None

    nt_full = _title_key_full(want_title)
    nt_core = _title_key_core(want_title)

    def _duration_delta(row: AssetRow) -> float:
        if want_duration_s is None or row.duration_s is None:
            return 999999.0
        return abs(float(want_duration_s) - float(row.duration_s))

    def _score(row: AssetRow) -> tuple[float, float, int, str]:
        ra = _artist_sim(want_artist, row.artist)
        rt_full = _ratio(nt_full, _title_key_full(row.title))
        rt_core = _ratio(nt_core, _title_key_core(row.title))
        rt = max(rt_full, rt_core)
        sim = (0.75 * rt) + (0.25 * ra)
        dur = _duration_delta(row)
        q = row.quality_rank if row.quality_rank is not None else 999
        return (1.0 - sim, dur, q, row.path.casefold())

    best = min(candidates, key=_score)

    ba = _artist_sim(want_artist, best.artist)
    bt_full = _ratio(nt_full, _title_key_full(best.title))
    bt_core = _ratio(nt_core, _title_key_core(best.title))
    bt = max(bt_full, bt_core)
    if bt < 0.66:
        return None
    if want_artist and ba < 0.50:
        return None
    if want_duration_s is not None and best.duration_s is not None:
        if bt >= 0.92 and ba >= 0.85:
            return best
        if abs(float(want_duration_s) - float(best.duration_s)) > 20.0:
            return None
    return best


def _resolve_to_flac(
    by_artist_title: dict[tuple[str, str], list[AssetRow]],
    by_artist_title_core: dict[tuple[str, str], list[AssetRow]],
    by_title: dict[str, list[AssetRow]],
    by_title_core: dict[str, list[AssetRow]],
    entry: PlaylistEntry,
) -> AssetRow | None:
    ka = _norm_text(entry.artist)
    kt = _title_key_full(entry.title)
    ktc = _title_key_core(entry.title)

    c = by_artist_title.get((ka, kt), [])
    best = _choose_best_flac(c, entry.artist, entry.title, entry.dur_s)
    if best is not None:
        return best

    c = by_artist_title_core.get((ka, ktc), [])
    best = _choose_best_flac(c, entry.artist, entry.title, entry.dur_s)
    if best is not None:
        return best

    c = by_title.get(kt, [])
    best = _choose_best_flac(c, entry.artist, entry.title, entry.dur_s)
    if best is not None:
        return best

    c = by_title_core.get(ktc, [])
    best = _choose_best_flac(c, entry.artist, entry.title, entry.dur_s)
    if best is not None:
        return best

    want_tokens = set(ktc.split()) or set(kt.split())
    if not want_tokens:
        return None
    pool: list[AssetRow] = []
    for tkey, rows in by_title.items():
        t_tokens = set(_title_key_core(tkey).split()) or set(tkey.split())
        if not t_tokens:
            continue
        if len(want_tokens.intersection(t_tokens)) >= max(2, min(4, len(want_tokens) // 2)):
            pool.extend(rows)
    return _choose_best_flac(pool, entry.artist, entry.title, entry.dur_s)


def _write_m3u8(out_path: Path, items: Sequence[tuple[int | None, str, str]]) -> None:
    lines: list[str] = ["#EXTM3U"]
    for dur_s, label, path in items:
        dur = int(dur_s) if dur_s is not None else -1
        lines.append(f"#EXTINF:{dur},{label}")
        lines.append(path)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_tsv(out_path: Path, rows: Sequence[Sequence[str]]) -> None:
    lines = ["\t".join(r) for r in rows]
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
    ap.add_argument("--all", required=True, help="all.m3u8 path")
    ap.add_argument("--missing", required=True, help="missing.m3u8 path")
    args = ap.parse_args(list(argv) if argv is not None else None)

    db_path = Path(args.db).expanduser() if args.db else None
    if not db_path or not db_path.exists():
        raise SystemExit(f"DB not found (set --db or TAGSLUT_DB): {db_path}")

    master_root = Path(args.master_root).expanduser().resolve() if args.master_root else None
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    all_path = Path(args.all).expanduser().resolve()
    missing_path = Path(args.missing).expanduser().resolve()
    if not all_path.exists():
        raise SystemExit(f"--all not found: {all_path}")
    if not missing_path.exists():
        raise SystemExit(f"--missing not found: {missing_path}")

    all_entries = _read_m3u_entries(all_path)
    missing_entries = _read_m3u_entries(missing_path)

    all_src = {e.src_path.casefold() for e in all_entries}
    all_keys = {e.key for e in all_entries}
    # For "locate via all.m3u8" fallback when missing src_path is stale.
    all_by_key: dict[tuple[str, str], str] = {}
    for e in all_entries:
        all_by_key.setdefault(e.key, e.src_path)

    seen_missing_src: set[str] = set()
    seen_missing_key: set[tuple[str, str]] = set()

    duplicates: list[tuple[int | None, str, str]] = []
    dup_rows: list[list[str]] = []
    unique: list[PlaylistEntry] = []

    for e in missing_entries:
        src_k = e.src_path.casefold()
        is_dup = False
        reasons: list[str] = []
        if src_k in all_src:
            is_dup = True
            reasons.append("in_all:path")
        if e.key in all_keys:
            is_dup = True
            reasons.append("in_all:artist+title")
        if src_k in seen_missing_src:
            is_dup = True
            reasons.append("in_missing:path")
        if e.key in seen_missing_key:
            is_dup = True
            reasons.append("in_missing:artist+title")

        seen_missing_src.add(src_k)
        seen_missing_key.add(e.key)

        if is_dup:
            duplicates.append((e.dur_s, e.label, e.src_path))
            dup_rows.append([e.label, str(e.dur_s or ""), e.src_path, ",".join(reasons)])
        else:
            unique.append(e)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        flac_assets = _load_inventory(conn, master_root, exts=(".flac",))
        any_assets = _load_inventory(conn, master_root, exts=_AUDIO_EXTS)
    finally:
        conn.close()

    fl_by_artist_title, fl_by_artist_title_core, fl_by_title, fl_by_title_core = _build_flac_indexes(flac_assets)
    any_by_artist_title, any_by_artist_title_core, any_by_title, any_by_title_core = _build_flac_indexes(any_assets)

    resolved_items: list[tuple[int | None, str, str]] = []
    located_rows: list[list[str]] = []
    unresolved_rows: list[list[str]] = []

    for e in unique:
        # Prefer FLAC in master, but fall back to any audio file in master.
        r = _resolve_to_flac(fl_by_artist_title, fl_by_artist_title_core, fl_by_title, fl_by_title_core, e)
        if r is None:
            r = _resolve_to_flac(
                any_by_artist_title, any_by_artist_title_core, any_by_title, any_by_title_core, e
            )
        if r is not None:
            resolved_items.append((e.dur_s, e.label, r.path))
            located_rows.append([e.label, str(e.dur_s or ""), e.src_path, r.path, "db"])
            continue

        # DB didn't have it. If the referenced path exists, it's already "located".
        src_p = Path(e.src_path)
        try:
            src_exists = src_p.exists()
        except Exception:
            src_exists = False
        if src_exists:
            resolved_items.append((e.dur_s, e.label, e.src_path))
            located_rows.append([e.label, str(e.dur_s or ""), e.src_path, e.src_path, "src_exists"])
            continue

        # Last resort: if it's in all.m3u8 by normalized artist+title, use that path.
        alt = all_by_key.get(e.key)
        if alt:
            resolved_items.append((e.dur_s, e.label, alt))
            located_rows.append([e.label, str(e.dur_s or ""), e.src_path, alt, "all_by_key"])
            continue

        unresolved_rows.append([e.label, str(e.dur_s or ""), e.src_path])

    stem = missing_path.stem
    _write_m3u8(out_dir / f"{stem} (Duplicates).m3u8", duplicates)
    _write_tsv(out_dir / f"{stem} (Duplicates).tsv", dup_rows)
    _write_m3u8(out_dir / f"{stem} (Unique Located).m3u8", resolved_items)
    _write_tsv(out_dir / f"{stem} (Unique Located).tsv", located_rows)
    _write_tsv(out_dir / f"{stem} (Unique Unresolved).tsv", unresolved_rows)

    print(
        "missing:",
        len(missing_entries),
        "duplicates:",
        len(duplicates),
        "unique:",
        len(unique),
        "unique_resolved:",
        len(resolved_items),
        "unique_unresolved:",
        len(unresolved_rows),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
