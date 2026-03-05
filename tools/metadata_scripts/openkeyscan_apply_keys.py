#!/usr/bin/env python3
"""
Apply OpenKeyScan key detection to local audio files and write ID3 key tags.

This script talks to the OpenKeyScan analyzer server via stdin/stdout NDJSON.
See https://github.com/rekordcloud/openkeyscan-analyzer (INTERFACING.md) for protocol.

Inputs:
  - M3U/M3U8 playlist of file paths, OR
  - CSV with a 'path' column

Outputs:
  - CSV report with key results and errors

Default is dry-run; use --execute to write tags.
Writes:
  - TKEY = Camelot notation (e.g., "8A")
  - TXXX:INITIALKEY = Camelot notation (for legacy key readers)
  - TXXX:OPENKEY = Open Key notation (e.g., "2m")
  - TXXX:KEY = Human-readable key (e.g., "E minor")
"""
from __future__ import annotations

import argparse
import csv
import json
import queue
import shlex
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Iterable, Optional

from mutagen.id3 import ID3, ID3NoHeaderError, TKEY, TXXX


def _read_paths_from_playlist(path: Path) -> list[Path]:
    paths: list[Path] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        paths.append(Path(line))
    return paths


def _read_paths_from_csv(path: Path) -> list[Path]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "path" not in reader.fieldnames:
            raise SystemExit("CSV must contain a 'path' column.")
        return [Path(row["path"]) for row in reader if row.get("path")]


def _get_id3(path: Path) -> Optional[ID3]:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()
    except Exception:
        return None


class OpenKeyScanClient:
    def __init__(self, cmd: list[str], ready_timeout_s: float = 30.0):
        self._cmd = cmd
        self._proc: subprocess.Popen[str] | None = None
        self._ready_timeout_s = ready_timeout_s
        self._pending: dict[str, queue.Queue[dict]] = {}
        self._lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None
        self._ready = threading.Event()

    def start(self) -> None:
        self._proc = subprocess.Popen(
            self._cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert self._proc.stdout is not None
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()

        # Wait for ready signal
        if not self._ready.wait(self._ready_timeout_s):
            raise RuntimeError("OpenKeyScan server did not become ready in time.")

    def _read_stdout(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            # System messages
            if payload.get("type") == "ready":
                self._ready.set()
                continue
            if payload.get("type") == "heartbeat":
                continue

            req_id = payload.get("id")
            if not req_id:
                continue
            with self._lock:
                q = self._pending.get(req_id)
            if q is not None:
                q.put(payload)

    def analyze(self, path: Path, timeout_s: float = 60.0) -> dict:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("OpenKeyScan server is not running.")
        req_id = str(uuid.uuid4())
        q: queue.Queue[dict] = queue.Queue(maxsize=1)
        with self._lock:
            self._pending[req_id] = q
        request = {"id": req_id, "path": str(path.resolve())}
        self._proc.stdin.write(json.dumps(request) + "\n")
        self._proc.stdin.flush()
        try:
            response = q.get(timeout=timeout_s)
        except queue.Empty:
            raise TimeoutError(f"Timed out waiting for response: {path}")
        finally:
            with self._lock:
                self._pending.pop(req_id, None)
        return response

    def stop(self) -> None:
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()


def _write_key_tags(tags: ID3, camelot: str, openkey: str, key_name: str) -> None:
    if camelot:
        tags["TKEY"] = TKEY(encoding=3, text=camelot)
        tags["TXXX:INITIALKEY"] = TXXX(encoding=3, desc="INITIALKEY", text=camelot)
    if openkey:
        tags["TXXX:OPENKEY"] = TXXX(encoding=3, desc="OPENKEY", text=openkey)
    if key_name:
        tags["TXXX:KEY"] = TXXX(encoding=3, desc="KEY", text=key_name)


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply OpenKeyScan keys to audio files.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--playlist", type=Path, help="M3U/M3U8 file with absolute paths")
    src.add_argument("--csv", type=Path, help="CSV with a 'path' column")
    ap.add_argument(
        "--server-cmd",
        required=True,
        help="Command to launch OpenKeyScan server (quoted string).",
    )
    ap.add_argument("--out", type=Path, default=Path("artifacts/openkeyscan_report.csv"))
    ap.add_argument("--limit", type=int, help="Limit number of files")
    ap.add_argument("--timeout-s", type=float, default=120.0, help="Per-file timeout")
    ap.add_argument("--execute", action="store_true", help="Write tags to files")
    args = ap.parse_args()

    if args.playlist:
        paths = _read_paths_from_playlist(args.playlist)
    else:
        paths = _read_paths_from_csv(args.csv)

    if args.limit:
        paths = paths[: args.limit]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    cmd = shlex.split(args.server_cmd)
    client = OpenKeyScanClient(cmd)
    client.start()

    try:
        with args.out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "path",
                    "status",
                    "camelot",
                    "openkey",
                    "key_name",
                    "error",
                ],
            )
            writer.writeheader()

            for path in paths:
                if not path.exists():
                    writer.writerow({"path": str(path), "status": "missing"})
                    continue

                try:
                    response = client.analyze(path, timeout_s=args.timeout_s)
                except Exception as exc:
                    writer.writerow(
                        {
                            "path": str(path),
                            "status": "error",
                            "error": str(exc),
                        }
                    )
                    continue

                if response.get("status") != "success":
                    writer.writerow(
                        {
                            "path": str(path),
                            "status": "error",
                            "error": response.get("error", "unknown"),
                        }
                    )
                    continue

                camelot = response.get("camelot", "")
                openkey = response.get("openkey", "")
                key_name = response.get("key", "")

                if args.execute:
                    tags = _get_id3(path)
                    if tags is None:
                        writer.writerow(
                            {
                                "path": str(path),
                                "status": "tag_read_error",
                                "camelot": camelot,
                                "openkey": openkey,
                                "key_name": key_name,
                            }
                        )
                        continue
                    _write_key_tags(tags, camelot, openkey, key_name)
                    tags.save(path, v2_version=3)

                writer.writerow(
                    {
                        "path": str(path),
                        "status": "ok",
                        "camelot": camelot,
                        "openkey": openkey,
                        "key_name": key_name,
                    }
                )
    finally:
        client.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
