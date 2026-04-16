from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Optional

# Signature: progress_cb(label: str, index: int, total: int) -> None
ProgressCallback = Callable[[str, int, int], None]

if TYPE_CHECKING:
    from tagslut.utils.console_ui import ConsoleUI


def make_progress_cb(verbose: bool, *, ui: "ConsoleUI | None" = None) -> Optional[ProgressCallback]:
    """Return a progress callback if verbose, else None."""
    if not verbose:
        return None

    def _cb(label: str, index: int, total: int) -> None:
        if ui is not None:
            ui.stage(f"{label}", "running", detail=f"{index}/{total}")
            return
        import sys

        print(f"[{index}/{total}] {label}", file=sys.stderr, flush=True)

    return _cb
