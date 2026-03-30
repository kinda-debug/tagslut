from __future__ import annotations
from typing import Callable, Optional

# Signature: progress_cb(label: str, index: int, total: int) -> None
ProgressCallback = Callable[[str, int, int], None]

def make_progress_cb(verbose: bool) -> Optional[ProgressCallback]:
    """Return a progress callback if verbose, else None."""
    if not verbose:
        return None
    import sys

    def _cb(label: str, index: int, total: int) -> None:
        print(f"[{index}/{total}] {label}", file=sys.stderr, flush=True)

    return _cb
