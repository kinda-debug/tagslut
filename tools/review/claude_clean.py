#!/usr/bin/env python3
"""Clean Claude export Markdown files into readable transcripts."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

TIMESTAMP_RE = re.compile(r"\b\d{1,2}:\d{2}\s*[AP]M\b")

SKIP_EXACT = {
    "New chat",
    "Search",
    "Chats",
    "Projects",
    "Artifacts",
    "All chats",
    "Show more",
    "Done",
    "Buy more",
    "### Starred",
    "### RecentsHide",
    "Claude is AI and can make mistakes. Please double-check responses.",
}

SKIP_PREFIXES = (
    "![",
    "You've hit your extra usage spending limit",
)


@dataclass(frozen=True)
class Message:
    timestamp: str
    user_lines: List[str]
    assistant_lines: List[str]


def _insert_timestamp_separators(text: str) -> str:
    return TIMESTAMP_RE.sub(lambda m: f"\n{m.group(0)}\n", text)


def _should_skip(line: str) -> bool:
    stripped = line.strip()
    if stripped in SKIP_EXACT:
        return True
    lstripped = line.lstrip()
    return any(lstripped.startswith(prefix) for prefix in SKIP_PREFIXES)


def _collapse_duplicate_lines(lines: Iterable[str]) -> List[str]:
    out: List[str] = []
    prev = None
    for line in lines:
        if prev is not None and line == prev and line != "":
            continue
        out.append(line)
        prev = line
    return out


def _collapse_blank_lines(lines: Iterable[str]) -> List[str]:
    out: List[str] = []
    prev_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        out.append("" if is_blank else line)
        prev_blank = is_blank
    return out


def clean_lines(text: str) -> List[str]:
    text = _insert_timestamp_separators(text)
    cleaned: List[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if _should_skip(line):
            continue
        cleaned.append(line)
    cleaned = _collapse_duplicate_lines(cleaned)
    cleaned = _collapse_blank_lines(cleaned)
    return cleaned


def _strip_blank_edges(lines: Sequence[str]) -> List[str]:
    start = 0
    end = len(lines)
    while start < end and lines[start].strip() == "":
        start += 1
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    return list(lines[start:end])


def extract_messages(lines: Sequence[str]) -> tuple[List[str], List[Message]]:
    timestamp_indices = [i for i, line in enumerate(lines) if TIMESTAMP_RE.fullmatch(line.strip() or "")]
    if not timestamp_indices:
        return list(lines), []

    user_starts: List[int] = []
    for idx in timestamp_indices:
        cursor = idx - 1
        while cursor >= 0:
            if lines[cursor].strip() == "":
                break
            if TIMESTAMP_RE.fullmatch(lines[cursor].strip() or ""):
                break
            cursor -= 1
        user_starts.append(cursor + 1)

    preamble = list(lines[: user_starts[0]])
    messages: List[Message] = []
    for i, ts_index in enumerate(timestamp_indices):
        user_lines = _strip_blank_edges(lines[user_starts[i] : ts_index])
        assistant_start = ts_index + 1
        assistant_end = user_starts[i + 1] if i + 1 < len(user_starts) else len(lines)
        assistant_lines = _strip_blank_edges(lines[assistant_start:assistant_end])
        messages.append(
            Message(
                timestamp=lines[ts_index].strip(),
                user_lines=user_lines,
                assistant_lines=assistant_lines,
            )
        )

    return preamble, messages


def render_markdown(filename: str, preamble: Sequence[str], messages: Sequence[Message]) -> str:
    output: List[str] = [f"# {filename} (cleaned)", ""]

    if any(line.strip() for line in preamble):
        output.append("## Preamble")
        output.extend(preamble)
        output.append("")

    for message in messages:
        output.append(f"### User — {message.timestamp}")
        output.extend(message.user_lines)
        output.append("")
        output.append("### Assistant")
        output.extend(message.assistant_lines)
        output.append("")

    return "\n".join(output).rstrip() + "\n"


def parse_text(text: str, filename: str) -> str:
    lines = clean_lines(text)
    preamble, messages = extract_messages(lines)
    return render_markdown(filename, preamble, messages)


def _write_output(out_path: Path, content: str, overwrite: bool) -> None:
    if out_path.exists() and not overwrite:
        raise SystemExit(f"Refusing to overwrite existing file: {out_path}")
    out_path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean Claude export Markdown files.")
    parser.add_argument("inputs", nargs="+", help="Input Markdown file(s)")
    parser.add_argument("--out-dir", default="output/claude_clean", help="Output directory")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing output files")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for input_path in args.inputs:
        in_path = Path(input_path)
        if not in_path.exists():
            raise SystemExit(f"Input not found: {in_path}")
        content = in_path.read_text(encoding="utf-8", errors="replace")
        rendered = parse_text(content, in_path.name)
        out_path = out_dir / f"{in_path.stem}.clean.md"
        _write_output(out_path, rendered, args.overwrite)
        print(f"Wrote {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
