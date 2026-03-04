from __future__ import annotations

import time


def _fmt_hms(seconds: float) -> str:
    sec = max(0, int(seconds))
    hrs, rem = divmod(sec, 3600)
    mins, secs = divmod(rem, 60)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


class ProgressTracker:
    def __init__(self, *, total: int, interval: int = 50, label: str = "Progress") -> None:
        self.total = max(0, int(total))
        self.interval = max(1, int(interval))
        self.label = label
        self.started = time.monotonic()

    def line(self, current: int, *, extra: str = "") -> str:
        elapsed = time.monotonic() - self.started
        rate = current / elapsed if elapsed > 0 else 0.0
        remaining = max(0, self.total - current)
        eta_seconds = (remaining / rate) if rate > 0 else 0.0
        suffix = f" | {extra}" if extra else ""
        return (
            f"{self.label} {current}/{self.total} | remaining={remaining} | "
            f"elapsed={_fmt_hms(elapsed)} | eta={_fmt_hms(eta_seconds)}{suffix}"
        )

    def should_print(self, current: int) -> bool:
        return current % self.interval == 0 or current == self.total
