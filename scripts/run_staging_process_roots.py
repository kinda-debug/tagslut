#!/opt/homebrew/bin/python3
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Queue:
    root: str
    slug: str
    source: str


QUEUES: list[Queue] = [
    Queue("/Volumes/MUSIC/staging/bpdl", "bpdl", "bpdl"),
    Queue("/Volumes/MUSIC/staging/tidal", "tidal", "tidal"),
    Queue("/Volumes/MUSIC/staging/StreamripDownloads", "streamripdownloads", "streamrip"),
    Queue("/Volumes/MUSIC/staging/SpotiFLACnext", "spotiflacnext", "spotiflacnext"),
    Queue("/Volumes/MUSIC/staging/Apple/Apple", "apple_apple", "apple"),
    Queue("/Volumes/MUSIC/staging/Apple/Apple Music", "apple_apple_music", "apple"),
    Queue("/Volumes/MUSIC/staging/Deep & Minimal", "deep_minimal", "manual"),
    Queue("/Volumes/MUSIC/staging/Groove It Out EP", "groove_it_out_ep", "manual"),
    Queue(
        "/Volumes/MUSIC/staging/Pareidolia (feat. Amanda Zamolo) [Frazer Ray Remix]",
        "pareidolia_feat_amanda_zamolo_frazer_ray_remix",
        "manual",
    ),
    Queue(
        "/Volumes/MUSIC/staging/Sounds Of Blue (Gui Boratto Remix)",
        "sounds_of_blue_gui_boratto_remix",
        "manual",
    ),
    Queue("/Volumes/MUSIC/staging/This Is bbno$", "this_is_bbno", "manual"),
    Queue("/Volumes/MUSIC/staging/mp3_to_sort_intake", "mp3_to_sort_intake", "mp3"),
]

PHASES = "identify,enrich,art,promote"


def run_logged(*, repo_root: Path, logs_dir: Path, queue: Queue) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"intake_{queue.slug}_{timestamp}.log"

    env = os.environ.copy()
    env["PATH"] = f"{Path.home()}/.local/bin:{env.get('PATH','')}"
    env["PYTHONUNBUFFERED"] = "1"

    tagslut_cli = repo_root / "scripts" / "tagslut_cli.py"
    register_cmd = [
        sys.executable,
        str(tagslut_cli),
        "admin",
        "index",
        "register",
        queue.root,
        "--source",
        queue.source,
        "--check-duration",
        "--execute",
    ]
    duration_cmd = [
        sys.executable,
        str(tagslut_cli),
        "admin",
        "index",
        "duration-check",
        queue.root,
        "--source",
        queue.source,
        "--execute",
    ]
    process_root_cmd = [
        sys.executable,
        str(tagslut_cli),
        "admin",
        "intake",
        "process-root",
        "--phases",
        PHASES,
        "--root",
        queue.root,
    ]

    print(f"root: {queue.root}")
    print(f"log: {log_path}")
    with log_path.open("wb") as log_file:
        for cmd in (register_cmd, duration_cmd, process_root_cmd):
            log_file.write(("$ " + " ".join(cmd) + "\n").encode("utf-8"))
            process = subprocess.Popen(
                cmd,
                cwd=str(repo_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            assert process.stdout is not None
            for chunk in iter(lambda: process.stdout.read(8192), b""):
                log_file.write(chunk)
            returncode = process.wait()
            if returncode != 0:
                raise SystemExit(f"FAILED ({returncode}): {queue.root}")
    print(f"ok: {queue.root}")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    logs_dir = Path("/Volumes/MUSIC/staging/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    for queue in QUEUES:
        run_logged(repo_root=repo_root, logs_dir=logs_dir, queue=queue)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
