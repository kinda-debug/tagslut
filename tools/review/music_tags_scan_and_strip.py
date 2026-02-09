#!/usr/bin/env python3
"""
music_tags_scan_and_strip.py

Standalone (no DB) scanner for a local music folder and an optional tag-stripping pass.

Primary use case: scan /Users/georgeskhawam/Music/Music, generate an XLSX inventory of:
  - all tag frames encountered across files (with counts + examples)
  - per-file canonical fields (Title, Artist, Album, etc.)

Then (optionally) rewrite tags, keeping only a user-provided allowlist of fields + artwork.

Safety:
  - Default mode is scan only.
  - Tag stripping is opt-in via --strip --execute.
  - Writes a JSONL backup log of "before" state per file.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Font

from mutagen.id3 import (
    APIC,
    COMM,
    ID3,
    POPM,
    TBPM,
    TCON,
    TDRC,
    TKEY,
    TALB,
    TIT2,
    TPE1,
    TPE2,
    TPE4,
    TPUB,
    TRCK,
    TSRC,
    TYER,
    TXXX,
)


KEEP_FIELDS = [
    "Title",
    "Artist",
    "Album",
    "Album Artist",
    "Track Number",
    "Year",
    "Genre",
    "Mix / Version (in Title)",
    "Remixer",
    "BPM",
    "Initial Key",
    "Label",
    "Catalog Number",
    "ISRC",
    "Comment",
    "Rating",
    "Artwork",
]


def _now_local_stamp() -> str:
    # Local time makes it easier to correlate with a human session.
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "; ".join(_safe_str(x) for x in v if x is not None)
    return str(v)


def _first_text(frame: Any) -> str:
    if frame is None:
        return ""
    text = getattr(frame, "text", None)
    return _safe_str(text)


def _get_txxx(id3: ID3, desc: str) -> List[TXXX]:
    out: List[TXXX] = []
    want = desc.strip().casefold()
    for fr in id3.getall("TXXX"):
        if (fr.desc or "").strip().casefold() == want:
            out.append(fr)
    return out


def _extract_comment(id3: ID3) -> str:
    comms = id3.getall("COMM")
    if not comms:
        return ""
    # Prefer eng, otherwise first.
    for fr in comms:
        if getattr(fr, "lang", None) == "eng":
            return _safe_str(getattr(fr, "text", ""))
    return _safe_str(getattr(comms[0], "text", ""))


def _extract_year(id3: ID3) -> str:
    if id3.get("TDRC"):
        return _safe_str(getattr(id3.get("TDRC"), "text", ""))
    if id3.get("TYER"):
        return _safe_str(getattr(id3.get("TYER"), "text", ""))
    return ""


def _extract_rating(id3: ID3) -> str:
    popms = id3.getall("POPM")
    if not popms:
        return ""
    # Prefer iTunes-like email if present, else first.
    for fr in popms:
        if (fr.email or "").lower().endswith("itunes.com"):
            return str(fr.rating)
    return str(popms[0].rating)


def _parse_mix_version_from_title(title: str) -> str:
    # Heuristic: capture trailing "(...)" or "[...]" that looks like mix/version.
    # We only report this; we do not mutate title.
    t = title.strip()
    m = re.search(r"(\(([^)]{1,80})\)|\[([^\]]{1,80})\])\s*$", t)
    if not m:
        return ""
    inner = m.group(2) or m.group(3) or ""
    inner_cf = inner.casefold()
    keywords = [
        "mix",
        "remix",
        "version",
        "edit",
        "dub",
        "instrumental",
        "extended",
        "radio",
        "club",
        "vip",
        "rework",
        "bootleg",
        "live",
    ]
    if any(k in inner_cf for k in keywords):
        return inner
    return ""


@dataclass
class CanonicalRow:
    path: str
    title: str = ""
    artist: str = ""
    album: str = ""
    album_artist: str = ""
    track_number: str = ""
    year: str = ""
    genre: str = ""
    mix_version_in_title: str = ""
    remixer: str = ""
    bpm: str = ""
    initial_key: str = ""
    label: str = ""
    catalog_number: str = ""
    isrc: str = ""
    comment: str = ""
    rating: str = ""
    artwork: str = ""  # yes/no
    tag_keys: str = ""  # all frames present
    extra_tag_keys: str = ""  # frames not in keep allowlist


def _mp3_files(root: Path) -> Iterable[Path]:
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.startswith("._"):
                continue
            if fn.lower().endswith(".mp3"):
                yield Path(dirpath) / fn


def _load_id3(path: Path) -> Optional[ID3]:
    try:
        return ID3(str(path))
    except Exception:
        return None


def _canonical_from_id3(path: Path, id3: ID3) -> CanonicalRow:
    title = _first_text(id3.get("TIT2"))
    remixer = ""
    if id3.get("TPE4"):
        remixer = _first_text(id3.get("TPE4"))
    elif _get_txxx(id3, "REMIXER"):
        remixer = _safe_str(_get_txxx(id3, "REMIXER")[0].text)

    label = ""
    if id3.get("TPUB"):
        label = _first_text(id3.get("TPUB"))
    elif _get_txxx(id3, "LABEL"):
        label = _safe_str(_get_txxx(id3, "LABEL")[0].text)

    catalog = ""
    for d in ["CATALOGNUMBER", "CATALOG NUMBER", "CATALOG"]:
        xs = _get_txxx(id3, d)
        if xs:
            catalog = _safe_str(xs[0].text)
            break

    has_artwork = "yes" if id3.getall("APIC") else "no"
    keys = sorted({fr.FrameID for fr in id3.values()})
    keep_ids = {
        "TIT2",
        "TPE1",
        "TALB",
        "TPE2",
        "TRCK",
        "TDRC",
        "TYER",
        "TCON",
        "TPE4",
        "TBPM",
        "TKEY",
        "TPUB",
        "TSRC",
        "COMM",
        "POPM",
        "APIC",
        "TXXX",
    }
    # For extra keys we treat TXXX as "kept only if desc is allowed".
    extra = []
    for k in keys:
        if k not in keep_ids:
            extra.append(k)
    # Additionally, list any TXXX descs we will drop.
    dropped_txxx = []
    allowed_desc = {"REMIXER", "LABEL", "CATALOGNUMBER", "CATALOG NUMBER", "CATALOG"}
    for fr in id3.getall("TXXX"):
        if (fr.desc or "").strip() not in allowed_desc:
            dropped_txxx.append(f"TXXX:{fr.desc}")
    extra.extend(dropped_txxx)
    extra_sorted = sorted(extra)

    return CanonicalRow(
        path=str(path),
        title=title,
        artist=_first_text(id3.get("TPE1")),
        album=_first_text(id3.get("TALB")),
        album_artist=_first_text(id3.get("TPE2")),
        track_number=_first_text(id3.get("TRCK")),
        year=_extract_year(id3),
        genre=_first_text(id3.get("TCON")),
        mix_version_in_title=_parse_mix_version_from_title(title),
        remixer=remixer,
        bpm=_first_text(id3.get("TBPM")),
        initial_key=_first_text(id3.get("TKEY")),
        label=label,
        catalog_number=catalog,
        isrc=_first_text(id3.get("TSRC")),
        comment=_extract_comment(id3),
        rating=_extract_rating(id3),
        artwork=has_artwork,
        tag_keys=";".join(keys),
        extra_tag_keys=";".join(extra_sorted),
    )


def _frame_description(frame_id: str) -> str:
    # Mutagen keeps descriptions on frame classes, but we keep it lightweight here.
    # If we can't resolve it, return empty.
    try:
        cls = ID3()._frames.get(frame_id)  # type: ignore[attr-defined]
        return getattr(cls, "__doc__", "") or ""
    except Exception:
        return ""


def _write_xlsx(
    out_path: Path,
    *,
    tag_counts: Dict[str, int],
    tag_examples: Dict[str, str],
    files: List[CanonicalRow],
) -> None:
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "TagInventory"

    ws1.append(["tag_id", "count_files", "example_value", "description"])
    ws1["A1"].font = ws1["B1"].font = ws1["C1"].font = ws1["D1"].font = Font(bold=True)
    for tag_id, cnt in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        ws1.append([tag_id, cnt, tag_examples.get(tag_id, ""), _frame_description(tag_id)])

    ws2 = wb.create_sheet("Files")
    ws2.append(
        [
            "path",
            "Title",
            "Artist",
            "Album",
            "Album Artist",
            "Track Number",
            "Year",
            "Genre",
            "Mix/Version (parsed from Title)",
            "Remixer",
            "BPM",
            "Initial Key",
            "Label",
            "Catalog Number",
            "ISRC",
            "Comment",
            "Rating",
            "Artwork",
            "tag_keys",
            "extra_tag_keys",
        ]
    )
    for cell in ws2[1]:
        cell.font = Font(bold=True)
    for r in files:
        ws2.append(
            [
                r.path,
                r.title,
                r.artist,
                r.album,
                r.album_artist,
                r.track_number,
                r.year,
                r.genre,
                r.mix_version_in_title,
                r.remixer,
                r.bpm,
                r.initial_key,
                r.label,
                r.catalog_number,
                r.isrc,
                r.comment,
                r.rating,
                r.artwork,
                r.tag_keys,
                r.extra_tag_keys,
            ]
        )

    for ws in (ws1, ws2):
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)


def _backup_event(path: Path, id3: ID3, *, note: str) -> Dict[str, Any]:
    keys = sorted({fr.FrameID for fr in id3.values()})
    txxx_descs = sorted({(fr.desc or "") for fr in id3.getall("TXXX")})
    return {
        "event": "id3_backup",
        "timestamp": _now_utc_iso(),
        "path": str(path),
        "note": note,
        "frame_ids": keys,
        "txxx_descs": txxx_descs,
        "title": _first_text(id3.get("TIT2")),
        "artist": _first_text(id3.get("TPE1")),
        "album": _first_text(id3.get("TALB")),
        "album_artist": _first_text(id3.get("TPE2")),
        "track_number": _first_text(id3.get("TRCK")),
        "year": _extract_year(id3),
        "genre": _first_text(id3.get("TCON")),
        "remixer_tpe4": _first_text(id3.get("TPE4")),
        "remixer_txxx": _safe_str(_get_txxx(id3, "REMIXER")[0].text) if _get_txxx(id3, "REMIXER") else "",
        "bpm": _first_text(id3.get("TBPM")),
        "initial_key": _first_text(id3.get("TKEY")),
        "label_tpub": _first_text(id3.get("TPUB")),
        "label_txxx": _safe_str(_get_txxx(id3, "LABEL")[0].text) if _get_txxx(id3, "LABEL") else "",
        "catalog_txxx": "",
        "isrc": _first_text(id3.get("TSRC")),
        "comment": _extract_comment(id3),
        "rating": _extract_rating(id3),
        "apic_count": len(id3.getall("APIC")),
    }


def _build_stripped_id3(id3: ID3) -> ID3:
    keep: ID3 = ID3()

    # Simple text frames
    for frame_cls, fid in [
        (TIT2, "TIT2"),
        (TPE1, "TPE1"),
        (TALB, "TALB"),
        (TPE2, "TPE2"),
        (TRCK, "TRCK"),
        (TCON, "TCON"),
        (TBPM, "TBPM"),
        (TKEY, "TKEY"),
        (TPUB, "TPUB"),
        (TSRC, "TSRC"),
        (TPE4, "TPE4"),
    ]:
        for fr in id3.getall(fid):
            keep.add(frame_cls(encoding=fr.encoding, text=list(getattr(fr, "text", []))))

    # Year: prefer TDRC but keep TYER if that was the only one
    if id3.getall("TDRC"):
        for fr in id3.getall("TDRC"):
            keep.add(TDRC(encoding=fr.encoding, text=list(getattr(fr, "text", []))))
    elif id3.getall("TYER"):
        for fr in id3.getall("TYER"):
            keep.add(TYER(encoding=fr.encoding, text=list(getattr(fr, "text", []))))

    # Comments: keep all
    for fr in id3.getall("COMM"):
        keep.add(COMM(encoding=fr.encoding, lang=fr.lang, desc=fr.desc, text=list(getattr(fr, "text", []))))

    # Rating: keep all POPM
    for fr in id3.getall("POPM"):
        keep.add(POPM(email=fr.email, rating=fr.rating, count=fr.count))

    # Artwork: keep all APIC
    for fr in id3.getall("APIC"):
        keep.add(
            APIC(
                encoding=fr.encoding,
                mime=fr.mime,
                type=fr.type,
                desc=fr.desc,
                data=fr.data,
            )
        )

    # TXXX: keep only a small allowlist by description.
    allowed_desc = {"REMIXER", "LABEL", "CATALOGNUMBER", "CATALOG NUMBER", "CATALOG"}
    for fr in id3.getall("TXXX"):
        if (fr.desc or "").strip() in allowed_desc:
            keep.add(TXXX(encoding=fr.encoding, desc=fr.desc, text=list(getattr(fr, "text", []))))

    return keep


def _strip_tags_mp3(
    path: Path,
    *,
    backup_log,
    execute: bool,
) -> Tuple[bool, str]:
    id3 = _load_id3(path)
    if id3 is None:
        return False, "unreadable_id3"

    backup_log.write(json.dumps(_backup_event(path, id3, note="pre_strip"), ensure_ascii=False) + "\n")

    new_id3 = _build_stripped_id3(id3)
    if not execute:
        return True, "dry_run"

    try:
        new_id3.save(str(path), v2_version=4)
        return True, "stripped"
    except Exception as e:
        return False, f"save_failed:{type(e).__name__}:{e}"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Scan tags and optionally strip everything except a small allowlist.")
    ap.add_argument("root", type=Path, help="Root folder to scan (e.g., /Users/georgeskhawam/Music/Music)")
    ap.add_argument(
        "--xlsx",
        type=Path,
        default=None,
        help="Output XLSX path (default: artifacts/music_tags_<ts>.xlsx)",
    )
    ap.add_argument(
        "--backup-jsonl",
        type=Path,
        default=None,
        help="Backup JSONL path for tag stripping (default: artifacts/music_tags_backup_<ts>.jsonl)",
    )
    ap.add_argument("--strip", action="store_true", help="Enable strip pass (requires --execute to write)")
    ap.add_argument("--execute", action="store_true", help="Actually write changes (default: dry-run)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    if not root.exists():
        print(f"ERROR: root does not exist: {root}")
        return 2

    ts = _now_local_stamp()
    xlsx_path = (args.xlsx or Path("artifacts") / f"music_tags_{ts}.xlsx").expanduser().resolve()
    backup_path = (args.backup_jsonl or Path("artifacts") / f"music_tags_backup_{ts}.jsonl").expanduser().resolve()

    tag_counts: Counter[str] = Counter()
    tag_examples: Dict[str, str] = {}
    file_rows: List[CanonicalRow] = []

    unreadable = 0
    total = 0
    for p in _mp3_files(root):
        total += 1
        id3 = _load_id3(p)
        if id3 is None:
            unreadable += 1
            continue
        keys = {fr.FrameID for fr in id3.values()}
        for k in keys:
            tag_counts[k] += 1
            if k not in tag_examples:
                try:
                    # Best-effort example
                    fr = id3.getall(k)[0]
                    tag_examples[k] = _safe_str(getattr(fr, "text", ""))[:200]
                except Exception:
                    tag_examples[k] = ""
        file_rows.append(_canonical_from_id3(p, id3))

    _write_xlsx(xlsx_path, tag_counts=dict(tag_counts), tag_examples=tag_examples, files=file_rows)
    print(f"Scanned root: {root}")
    print(f"Files (mp3): {total}")
    print(f"Unreadable ID3: {unreadable}")
    print(f"Unique tag frame IDs: {len(tag_counts)}")
    print(f"XLSX: {xlsx_path}")
    print("Keep allowlist:")
    for f in KEEP_FIELDS:
        print(f"  - {f}")

    if args.strip:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        ok = 0
        fail = 0
        with backup_path.open("w", encoding="utf-8") as backup_log:
            for i, row in enumerate(file_rows, start=1):
                p = Path(row.path)
                success, status = _strip_tags_mp3(p, backup_log=backup_log, execute=bool(args.execute))
                if success:
                    ok += 1
                else:
                    fail += 1
                if i % 100 == 0:
                    print(f"strip progress: {i}/{len(file_rows)} ok={ok} fail={fail}")

        mode = "EXECUTE" if args.execute else "DRY-RUN"
        print(f"{mode} strip done: ok={ok} fail={fail}")
        print(f"Backup JSONL: {backup_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

