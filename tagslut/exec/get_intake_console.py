from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from tagslut.utils.env_paths import get_artifacts_dir


StageStatus = Literal["pending", "running", "ok", "skipped", "failed"]
TrackOutcome = Literal["downloaded", "present", "skipped", "failed", "unknown"]


_STEP_RE = re.compile(r"^\[(\d+)/(\d+)\]\s+(.*)$")
_CONFIG_KV_RE = re.compile(r"^\s{2}([A-Za-z][A-Za-z0-9 /_-]*?)\s{2,}(.+?)\s*$")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_TIDAL_TRACK_ID_RE = re.compile(r"/(?:browse/)?track/(\d+)", re.IGNORECASE)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _norm_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _abbrev_path(path: str, *, roots: dict[str, str]) -> str:
    value = (path or "").strip()
    if not value:
        return ""
    for label, root in roots.items():
        if root and value.startswith(root.rstrip("/") + "/"):
            return f"{label}:{value[len(root.rstrip('/'))+1:]}"
        if root and value == root.rstrip("/"):
            return f"{label}:/"
    if len(value) <= 72:
        return value
    head = value[:34]
    tail = value[-34:]
    return f"{head}…{tail}"


@dataclass
class Stage:
    idx: int
    total: int
    name: str
    status: StageStatus = "pending"
    details: list[str] = field(default_factory=list)


@dataclass
class TrackRow:
    domain: str
    track_id: str
    index: int | None
    title: str
    artist: str
    precheck_decision: str
    precheck_reason: str
    outcome: TrackOutcome = "unknown"
    outcome_reason: str = ""
    dest: str = ""
    quality: str = ""
    inferred_from_log: bool = False


@dataclass
class RunArtifacts:
    raw_log: Path
    compare_dir: Path
    precheck_decisions_csv: Path | None = None
    precheck_tracks_csv: Path | None = None
    keep_urls_txt: Path | None = None
    outcomes_csv: Path | None = None


@dataclass
class RunReport:
    source: str = ""
    url: str = ""
    batch_root: str = ""
    db_path: str = ""
    library_root: str = ""
    toggles: dict[str, str] = field(default_factory=dict)
    stages: list[Stage] = field(default_factory=list)

    requested_total: int | None = None
    precheck_total: int | None = None
    precheck_keep: int | None = None
    precheck_skip: int | None = None
    selected_for_download: int | None = None

    download_downloaded: int = 0
    download_present: int = 0
    download_failed: int = 0

    tagged_count: int | None = None
    dj_identity_resolved: int | None = None

    tracks: dict[tuple[str, str], TrackRow] = field(default_factory=dict)
    track_order: list[tuple[str, str]] = field(default_factory=list)
    pending_download_by_key: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    pending_download_by_title: list[dict[str, str]] = field(default_factory=list)


def _latest_after(dir_path: Path, pattern: str, *, started: float) -> Path | None:
    if not dir_path.exists():
        return None
    candidates = sorted(dir_path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in candidates:
        try:
            if p.stat().st_mtime >= started - 1.0:
                return p
        except OSError:
            continue
    return candidates[0] if candidates else None


def _discover_artifacts(*, started: float, raw_log: Path) -> RunArtifacts:
    artifacts_root = get_artifacts_dir().expanduser().resolve()
    compare_dir = artifacts_root / "compare"
    out = RunArtifacts(raw_log=raw_log, compare_dir=compare_dir)
    out.precheck_decisions_csv = _latest_after(compare_dir, "precheck_decisions_*.csv", started=started)
    out.precheck_tracks_csv = _latest_after(compare_dir, "precheck_tracks_extracted_*.csv", started=started)
    out.keep_urls_txt = _latest_after(compare_dir, "precheck_keep_track_urls_*.txt", started=started)
    return out


def _load_precheck_decisions(report: RunReport, path: Path) -> None:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            domain = (row.get("domain") or "").strip()
            track_id = (row.get("track_id") or "").strip()
            if not domain or not track_id:
                continue
            index = None
            try:
                index = int((row.get("track_index") or "").strip() or "0") or None
            except Exception:
                index = None
            tr = TrackRow(
                domain=domain,
                track_id=track_id,
                index=index,
                title=(row.get("title") or "").strip(),
                artist=(row.get("artist") or "").strip(),
                precheck_decision=(row.get("decision") or row.get("action") or "").strip().lower(),
                precheck_reason=(row.get("reason") or "").strip(),
            )
            key = (domain, track_id)
            report.tracks[key] = tr
            report.track_order.append(key)


def _extract_tidal_track_id(url: str) -> str | None:
    m = _TIDAL_TRACK_ID_RE.search(url)
    return m.group(1) if m else None


def _parse_downloaded_line(line: str) -> tuple[str, str, str]:
    stripped = line.strip()
    prefix = stripped.split(" /", 1)[0].strip()
    rest = prefix[len("Downloaded ") :].strip()
    title = rest
    quality = ""
    if "  " in rest:
        title, tail = rest.split("  ", 1)
        title = title.strip()
        quality = tail.strip()
    dest = ""
    if " /" in stripped:
        dest = "/" + stripped.split(" /", 1)[1].strip()
    return title, quality, dest


def reconcile_outcomes(report: RunReport) -> None:
    for key, payload in list(report.pending_download_by_key.items()):
        tr = report.tracks.get(key)
        if not tr:
            continue
        tr.outcome = payload.get("outcome", "unknown")  # type: ignore[assignment]
        tr.outcome_reason = payload.get("reason", "")
        tr.quality = payload.get("quality", "") or tr.quality
        tr.dest = payload.get("dest", "") or tr.dest
        tr.inferred_from_log = True

    if not report.pending_download_by_title:
        return
    by_title: dict[str, list[TrackRow]] = {}
    for key in report.track_order:
        tr = report.tracks.get(key)
        if not tr:
            continue
        by_title.setdefault(_norm_text(tr.title), []).append(tr)
    for ev in report.pending_download_by_title:
        norm = ev.get("title_norm", "")
        candidates = [c for c in (by_title.get(norm) or []) if c.outcome == "unknown"]
        if len(candidates) != 1:
            continue
        tr = candidates[0]
        tr.outcome = ev.get("outcome", "unknown")  # type: ignore[assignment]
        tr.outcome_reason = ev.get("reason", "")
        tr.quality = ev.get("quality", "") or tr.quality
        tr.dest = ev.get("dest", "") or tr.dest
        tr.inferred_from_log = True


def apply_precheck_skips(report: RunReport) -> None:
    for tr in report.tracks.values():
        if tr.outcome != "unknown":
            continue
        if tr.precheck_decision == "skip":
            tr.outcome = "skipped"
            tr.outcome_reason = tr.precheck_reason or "skipped by precheck"
            tr.inferred_from_log = False


def _write_outcomes_csv(*, artifacts: RunArtifacts, report: RunReport) -> Path:
    artifacts_root = get_artifacts_dir().expanduser().resolve()
    out_dir = artifacts_root / "intake" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"outcomes_{_utc_stamp()}.csv"
    fieldnames = ["domain", "track_id", "track_index", "artist", "title", "precheck_decision", "precheck_reason", "outcome", "outcome_reason", "dest", "quality", "inferred_from_log"]
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for key in report.track_order:
            tr = report.tracks.get(key)
            if not tr:
                continue
            w.writerow(
                {
                    "domain": tr.domain,
                    "track_id": tr.track_id,
                    "track_index": tr.index or "",
                    "artist": tr.artist,
                    "title": tr.title,
                    "precheck_decision": tr.precheck_decision,
                    "precheck_reason": tr.precheck_reason,
                    "outcome": tr.outcome,
                    "outcome_reason": tr.outcome_reason,
                    "dest": tr.dest,
                    "quality": tr.quality,
                    "inferred_from_log": "1" if tr.inferred_from_log else "0",
                }
            )
    artifacts.outcomes_csv = out_path
    return out_path


class GetIntakeLogParser:
    def __init__(self) -> None:
        self.report = RunReport()
        self._current_stage: Stage | None = None
        self._in_config = False
        self._current_download_track_key: tuple[str, str] | None = None
        self._download_seen_titles: set[str] = set()

    def feed_line(self, raw: str) -> None:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            return

        m = _STEP_RE.match(stripped)
        if m:
            idx = int(m.group(1))
            total = int(m.group(2))
            label = m.group(3).strip()
            if not _URL_RE.match(label):
                if self._current_stage and self._current_stage.status == "running":
                    self._current_stage.status = "ok"
                st = Stage(idx=idx, total=total, name=label, status="running")
                self.report.stages.append(st)
                self._current_stage = st
                return

        if stripped == "Intake Config":
            self._in_config = True
            return
        if self._in_config:
            kv = _CONFIG_KV_RE.match(line)
            if kv:
                key = kv.group(1).strip().lower()
                value = kv.group(2).strip()
                if key == "source":
                    self.report.source = value
                elif key == "url":
                    self.report.url = value
                elif key == "batch root":
                    self.report.batch_root = value
                elif key == "db":
                    self.report.db_path = value
                elif key == "library root":
                    self.report.library_root = value
                else:
                    self.report.toggles[key] = value
                return
            if stripped.startswith("[") and "]" in stripped:
                self._in_config = False

        if stripped.startswith("Precheck summary:"):
            m2 = re.search(r"keep=(\d+)\s+skip=(\d+)\s+total=(\d+)", stripped)
            if m2:
                self.report.precheck_keep = int(m2.group(1))
                self.report.precheck_skip = int(m2.group(2))
                self.report.precheck_total = int(m2.group(3))
            return
        if self._current_stage and "pre-download" in self._current_stage.name.lower():
            kv = _CONFIG_KV_RE.match(line)
            if kv:
                k = kv.group(1).strip().lower()
                v = kv.group(2).strip()
                if k == "total":
                    self.report.precheck_total = int(v)
                elif k == "keep":
                    self.report.precheck_keep = int(v)
                elif k == "skip":
                    self.report.precheck_skip = int(v)
                return

        if stripped.startswith("Selected for download:"):
            m2 = re.search(r"Selected for download:\s*(\d+)\s+track", stripped)
            if m2:
                self.report.selected_for_download = int(m2.group(1))
            return

        m3 = re.match(r"^\[(\d+)/(\d+)\]\s+(https?://\S+)", stripped)
        if m3:
            url = m3.group(3)
            tid = _extract_tidal_track_id(url)
            if tid:
                self._current_download_track_key = ("tidal", tid)
            return

        if stripped.startswith("Downloaded "):
            title, quality, dest = _parse_downloaded_line(stripped)
            self.report.download_downloaded += 1
            self._buffer_download_outcome(title=title, outcome="downloaded", reason="downloaded (inferred from log)", quality=quality, dest=dest)
            return
        if stripped.startswith("Exists "):
            title = stripped[len("Exists ") :].split(" /", 1)[0].strip()
            self.report.download_present += 1
            self._buffer_download_outcome(title=title, outcome="present", reason="already present (inferred from log)")
            return
        if stripped.startswith("Error:"):
            self.report.download_failed += 1
            self._buffer_download_outcome(title="download error", outcome="failed", reason=stripped[len("Error:") :].strip())
            return

        if stripped.startswith("Tagged:"):
            m2 = re.search(r"Tagged:\s*(\d+)", stripped)
            if m2:
                self.report.tagged_count = int(m2.group(1))
            return
        if stripped.startswith("Resolved ") and " promoted identity ids" in stripped:
            m2 = re.search(r"Resolved\s+(\d+)\s+promoted identity ids", stripped)
            if m2:
                self.report.dj_identity_resolved = int(m2.group(1))
            return

    def finalize(self) -> RunReport:
        if self._current_stage and self._current_stage.status == "running":
            self._current_stage.status = "ok"
        return self.report

    def _buffer_download_outcome(self, *, title: str, outcome: TrackOutcome, reason: str, quality: str = "", dest: str = "") -> None:
        if self._current_download_track_key:
            self.report.pending_download_by_key[self._current_download_track_key] = {"title": title, "outcome": outcome, "reason": reason, "quality": quality, "dest": dest}
            return
        nt = _norm_text(title)
        if not nt or nt in self._download_seen_titles:
            return
        self._download_seen_titles.add(nt)
        self.report.pending_download_by_title.append({"title": title, "title_norm": nt, "outcome": outcome, "reason": reason, "quality": quality, "dest": dest})


def _roots_map(report: RunReport) -> dict[str, str]:
    roots: dict[str, str] = {}
    if report.library_root:
        roots["LIB"] = report.library_root
    if report.batch_root:
        roots["BATCH"] = report.batch_root
    for key, label in [("fix root", "FIX"), ("discard", "DISCARD"), ("quarantine", "QUAR")]:
        if key in report.toggles:
            roots[label] = report.toggles[key]
    return roots


def _render_rich(report: RunReport, artifacts: RunArtifacts, *, verbose: bool, success_limit: int) -> None:
    console = Console()
    roots = _roots_map(report)

    header = Table(show_header=False, box=None, pad_edge=False)
    header.add_column("k", style="dim", no_wrap=True)
    header.add_column("v")
    header.add_row("Source", report.source or "?")
    header.add_row("URL", report.url or "?")
    header.add_row("Batch", _abbrev_path(report.batch_root, roots=roots))
    header.add_row("DB", _abbrev_path(report.db_path, roots=roots))
    header.add_row("Library", _abbrev_path(report.library_root, roots=roots))
    header.add_row("Raw log", str(artifacts.raw_log))
    console.print(Panel(header, title="tools/get Run", border_style="cyan"))

    for st in report.stages:
        style = {"ok": "green", "failed": "red", "skipped": "yellow", "running": "cyan"}.get(st.status, "dim")
        console.print(Panel(f"status: [{style}]{st.status}[/{style}]", title=f"[{st.idx}/{st.total}] {st.name}", border_style=style))

    summary = Table(show_header=False, box=None, pad_edge=False)
    summary.add_column("k", style="dim", no_wrap=True)
    summary.add_column("v")
    if report.precheck_total is not None:
        summary.add_row("Precheck", f"keep={report.precheck_keep} skip={report.precheck_skip} total={report.precheck_total}")
    if report.selected_for_download is not None:
        summary.add_row("Selected", str(report.selected_for_download))
    summary.add_row("Downloaded", str(report.download_downloaded))
    summary.add_row("Present", str(report.download_present))
    summary.add_row("Failed", str(report.download_failed))

    table = Table(title="Per-track outcomes", show_lines=False)
    table.add_column("#", style="dim", width=4, no_wrap=True)
    table.add_column("Artist", overflow="fold")
    table.add_column("Title", overflow="fold")
    table.add_column("Outcome", no_wrap=True)
    table.add_column("Reason", overflow="fold")
    table.add_column("Dest", overflow="fold")
    table.add_column("Quality", no_wrap=True)

    rows = [report.tracks[k] for k in report.track_order if k in report.tracks]
    failures_or_skips = [r for r in rows if r.outcome in {"failed", "skipped"}]
    successes = [r for r in rows if r.outcome in {"downloaded", "present"}]
    unknowns = [r for r in rows if r.outcome == "unknown"]
    render_rows = failures_or_skips + unknowns + successes[:success_limit]
    for r in render_rows:
        outcome_style = {"downloaded": "green", "present": "cyan", "skipped": "yellow", "failed": "red", "unknown": "dim"}[r.outcome]
        reason = r.outcome_reason or r.precheck_reason
        if r.inferred_from_log:
            reason = f"{reason} [inferred-from-log]"
        table.add_row(str(r.index or ""), r.artist, r.title, Text(r.outcome, style=outcome_style), reason, _abbrev_path(r.dest, roots=roots), r.quality)

    footer = ""
    if len(successes) > success_limit:
        footer = f"success rows truncated: showing {success_limit}/{len(successes)}"

    body = Table.grid(padding=(0, 1))
    body.add_row(summary)
    body.add_row(Rule(style="dim"))
    body.add_row(table)
    if footer:
        body.add_row(Text(footer, style="dim"))
    console.print(Panel(body, title="Download Accountability", border_style="cyan"))

    meta = Table(show_header=False, box=None, pad_edge=False)
    meta.add_column("k", style="dim", no_wrap=True)
    meta.add_column("v")
    if report.tagged_count is not None:
        meta.add_row("Tagged", str(report.tagged_count))
    if report.dj_identity_resolved is not None:
        meta.add_row("DJ identities", str(report.dj_identity_resolved))
    console.print(Panel(meta, title="Metadata / DJ", border_style="magenta"))

    arts = Table(show_header=False, box=None, pad_edge=False)
    arts.add_column("k", style="dim", no_wrap=True)
    arts.add_column("v")
    arts.add_row("raw_log", str(artifacts.raw_log))
    if artifacts.precheck_decisions_csv:
        arts.add_row("precheck_decisions", str(artifacts.precheck_decisions_csv))
    if artifacts.precheck_tracks_csv:
        arts.add_row("precheck_tracks", str(artifacts.precheck_tracks_csv))
    if artifacts.keep_urls_txt:
        arts.add_row("keep_urls", str(artifacts.keep_urls_txt))
    if artifacts.outcomes_csv:
        arts.add_row("outcomes", str(artifacts.outcomes_csv))
    console.print(Panel(arts, title="Key Artifacts", border_style="cyan"))


def _render_plain(report: RunReport, artifacts: RunArtifacts, *, out: Any, success_limit: int) -> None:
    w = out.write
    w("tools/get Run\n")
    w(f"  source:  {report.source or '?'}\n")
    w(f"  url:     {report.url or '?'}\n")
    w(f"  batch:   {report.batch_root or '?'}\n")
    w(f"  db:      {report.db_path or '?'}\n")
    w(f"  library: {report.library_root or '?'}\n")
    w(f"  raw_log: {artifacts.raw_log}\n")
    w("\nStages:\n")
    for st in report.stages:
        w(f"  [{st.idx}/{st.total}] {st.name} ({st.status})\n")
    w("\nDownload:\n")
    w(f"  precheck: keep={report.precheck_keep} skip={report.precheck_skip} total={report.precheck_total}\n")
    w(f"  selected: {report.selected_for_download}\n")
    w(f"  outcomes: downloaded={report.download_downloaded} present={report.download_present} failed={report.download_failed}\n")
    rows = [report.tracks[k] for k in report.track_order if k in report.tracks]
    failures_or_skips = [r for r in rows if r.outcome in {"failed", "skipped"}]
    unknowns = [r for r in rows if r.outcome == "unknown"]
    successes = [r for r in rows if r.outcome in {"downloaded", "present"}]
    render_rows = failures_or_skips + unknowns + successes[:success_limit]
    w("  per-track:\n")
    for r in render_rows:
        reason = r.outcome_reason or r.precheck_reason
        if r.inferred_from_log:
            reason = f"{reason} [inferred-from-log]"
        w(f"    - {r.artist} - {r.title} | {r.outcome} | {reason}\n")
    if len(successes) > success_limit:
        w(f"    (success rows truncated: {success_limit}/{len(successes)})\n")
    w("\nKey Artifacts:\n")
    w(f"  raw_log: {artifacts.raw_log}\n")
    if artifacts.precheck_decisions_csv:
        w(f"  precheck_decisions: {artifacts.precheck_decisions_csv}\n")
    if artifacts.outcomes_csv:
        w(f"  outcomes: {artifacts.outcomes_csv}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="tools/get-intake console wrapper (Rich TTY + plain non-TTY).")
    ap.add_argument("--verbose", action="store_true", help="Show more details (still structured).")
    ap.add_argument("--success-limit", type=int, default=40, help="Max success rows to print in default mode.")
    ap.add_argument("--", dest="dashdash", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to run (pass after --).")
    ns = ap.parse_args(argv)

    cmd = ns.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("ERROR: missing backend command (use: ... get_intake_console -- <tools/get-intake ...>)", file=sys.stderr)
        return 2

    started = time.time()
    artifacts_root = get_artifacts_dir().expanduser().resolve()
    raw_log_dir = artifacts_root / "intake" / "logs"
    raw_log_dir.mkdir(parents=True, exist_ok=True)
    raw_log = raw_log_dir / f"get_intake_{_utc_stamp()}.log"

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"

    parser = GetIntakeLogParser()
    with raw_log.open("w", encoding="utf-8") as log_fh:
        proc = subprocess.Popen(
            cmd,
            cwd=str(Path.cwd()),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            log_fh.write(line)
            parser.feed_line(line)
        try:
            proc.stdout.close()
        except Exception:
            pass
        rc = proc.wait()

    report = parser.finalize()
    artifacts = _discover_artifacts(started=started, raw_log=raw_log)
    if artifacts.precheck_decisions_csv and artifacts.precheck_decisions_csv.exists():
        _load_precheck_decisions(report, artifacts.precheck_decisions_csv)
        reconcile_outcomes(report)
        apply_precheck_skips(report)
        report.precheck_total = report.precheck_total or len(report.track_order)
        report.requested_total = report.requested_total or len(report.track_order)

    _write_outcomes_csv(artifacts=artifacts, report=report)

    if _is_tty() and not os.environ.get("NO_COLOR"):
        Console().print(Rule(style="dim"))
        _render_rich(report, artifacts, verbose=bool(ns.verbose), success_limit=int(ns.success_limit))
    else:
        _render_plain(report, artifacts, out=sys.stdout, success_limit=int(ns.success_limit))

    if rc != 0:
        tail = raw_log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        sys.stderr.write(f"\nFAILED: backend rc={rc}\nraw log: {raw_log}\n")
        sys.stderr.write("\n".join(tail) + "\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

