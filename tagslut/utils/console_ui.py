from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from typing import Iterable, Sequence

from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.text import Text


_STATUS_STYLE = {
    "running": "bold cyan",
    "ok": "bold green",
    "success": "bold green",
    "skipped": "bold yellow",
    "warn": "bold yellow",
    "warning": "bold yellow",
    "failed": "bold red",
    "error": "bold red",
}


class ConsoleUI:
    """
    Shared terminal renderer for human-facing file-processing commands.

    Rich is used only on a TTY with color enabled. Plain text is emitted
    otherwise so logs and pipes stay stable and ANSI-free.
    """

    def __init__(
        self,
        quiet: bool = False,
        *,
        verbose: bool = False,
        stream: io.TextIOBase | None = None,
        err_stream: io.TextIOBase | None = None,
        force_tty: bool | None = None,
    ):
        self.quiet = quiet
        self.verbose = verbose
        self.stream = stream or sys.stdout
        self.err_stream = err_stream or sys.stderr
        self.rich_enabled = self._should_use_rich(force_tty=force_tty, stream=self.stream)
        self.console = Console(
            file=self.stream,
            force_terminal=self.rich_enabled,
            no_color=not self.rich_enabled,
            color_system="standard" if self.rich_enabled else None,
            soft_wrap=True,
            highlight=False,
        )
        self.err_console = Console(
            file=self.err_stream,
            force_terminal=self.rich_enabled,
            no_color=not self.rich_enabled,
            color_system="standard" if self.rich_enabled else None,
            soft_wrap=True,
            highlight=False,
        )

    @staticmethod
    def _should_use_rich(*, force_tty: bool | None, stream: io.TextIOBase) -> bool:
        if force_tty is not None:
            return bool(force_tty)
        if os.getenv("NO_COLOR"):
            return False
        try:
            return bool(stream.isatty())
        except Exception:
            return False

    def display_path(self, value: str | Path | None) -> str:
        if value is None:
            return ""
        path = str(value)
        if self.verbose or len(path) <= 72:
            return path
        resolved = Path(path)
        name = resolved.name or path
        parent = str(resolved.parent)
        if parent in {"", "."}:
            return path
        if len(name) >= 28:
            return name
        head = parent[:20]
        tail = parent[-20:] if len(parent) > 20 else parent
        return f"{head}…{tail}/{name}"

    def _emit_plain(self, message: str, *, err: bool = False) -> None:
        if self.quiet:
            return
        print(message, file=self.err_stream if err else self.stream)

    def _emit_rich(self, renderable: object, *, err: bool = False) -> None:
        if self.quiet:
            return
        target = self.err_console if err else self.console
        target.print(renderable)

    def begin_command(self, name: str, target: str | None = None, mode: str | None = None) -> None:
        if self.quiet:
            return
        title = f"{name}"
        if self.rich_enabled:
            self._emit_rich(Rule(Text(title, style="bold")))
        else:
            self._emit_plain(f"== {title} ==")
        context: list[str] = []
        if target:
            context.append(f"target={self.display_path(target)}")
        if mode:
            context.append(f"mode={mode}")
        if context:
            if self.rich_enabled:
                self._emit_rich(Text(" | ".join(context), style="dim"))
            else:
                self._emit_plain(" | ".join(context))

    def section(self, title: str, subtitle: str | None = None) -> None:
        if self.rich_enabled:
            self._emit_rich(Rule(Text(title, style="bold")))
            if subtitle:
                self._emit_rich(Text(subtitle, style="dim"))
        else:
            self._emit_plain(f"-- {title} --")
            if subtitle:
                self._emit_plain(subtitle)

    def stage(
        self,
        label: str,
        status: str,
        detail: str | None = None,
        counts: dict[str, object] | Sequence[tuple[str, object]] | None = None,
    ) -> None:
        status_norm = status.strip().lower()
        badge = status_norm.upper()
        count_text = ""
        if counts:
            if isinstance(counts, dict):
                count_items = counts.items()
            else:
                count_items = counts
            count_text = " | " + ", ".join(f"{key}={value}" for key, value in count_items)
        line = f"[{badge}] {label}"
        if detail:
            line += f" — {detail}"
        line += count_text
        if self.rich_enabled:
            text = Text()
            text.append(f"[{badge}] ", style=_STATUS_STYLE.get(status_norm, "bold"))
            text.append(label, style="bold")
            if detail:
                text.append(f" — {detail}", style="dim")
            if count_text:
                text.append(count_text, style="dim")
            self._emit_rich(text)
        else:
            self._emit_plain(line)

    def file_event(
        self,
        action: str,
        path: str | Path | None = None,
        title: str | None = None,
        artist: str | None = None,
        reason: str | None = None,
        extra: str | None = None,
    ) -> None:
        lead = action.upper()
        subject_parts = [part for part in (artist, title) if part]
        subject = " — ".join(subject_parts)
        fragments = [f"[{lead}]"]
        if subject:
            fragments.append(subject)
        if path:
            fragments.append(self.display_path(path))
        if reason:
            fragments.append(f"reason={reason}")
        if extra:
            fragments.append(extra)
        line = " ".join(fragments)
        if self.rich_enabled:
            text = Text()
            text.append(f"[{lead}] ", style="bold cyan")
            if subject:
                text.append(subject, style="bold")
                if path or reason or extra:
                    text.append(" ")
            if path:
                text.append(self.display_path(path), style="dim")
            if reason:
                text.append(f" reason={reason}", style="dim")
            if extra:
                text.append(f" {extra}", style="dim")
            self._emit_rich(text)
        else:
            self._emit_plain(line)

    def note(self, message: str) -> None:
        if self.rich_enabled:
            self._emit_rich(Text(message, style="dim"))
        else:
            self._emit_plain(message)

    def warn(self, message: str) -> None:
        if self.rich_enabled:
            self._emit_rich(Text(f"WARNING: {message}", style="bold yellow"), err=True)
        else:
            self._emit_plain(f"WARNING: {message}", err=True)

    def error(self, message: str, exit_code: int | None = None) -> None:
        if self.rich_enabled:
            self._emit_rich(Text(f"ERROR: {message}", style="bold red"), err=True)
        else:
            self._emit_plain(f"ERROR: {message}", err=True)
        if exit_code is not None:
            sys.exit(exit_code)

    def summary(self, title: str, rows: Iterable[tuple[str, object]]) -> None:
        items = [(str(label), value) for label, value in rows]
        if self.rich_enabled:
            table = Table(show_header=False, box=None, padding=(0, 1))
            table.add_column("label", style="dim")
            table.add_column("value", style="bold")
            for label, value in items:
                table.add_row(label, str(value))
            self._emit_rich(Rule(Text(title, style="bold")))
            self._emit_rich(table)
        else:
            self._emit_plain(title)
            for label, value in items:
                self._emit_plain(f"{label}: {value}")

    def finish(self, status: str, rows: Iterable[tuple[str, object]] | None = None) -> None:
        if rows:
            self.summary("Summary", rows)
        self.stage("Finished", status)

    def print(self, message: str):  # type: ignore[override]
        self.note(message)

    def warning(self, message: str):  # type: ignore[override]
        self.warn(message)

    def success(self, message: str):  # type: ignore[override]
        self.stage(message, "success")

    def confirm(self, prompt: str, required_phrase: str) -> bool:
        self.warn(prompt)
        self.note(f"To confirm, type exactly: '{required_phrase}'")
        response = input("> ").strip()
        return response == required_phrase
