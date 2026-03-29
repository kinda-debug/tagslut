from __future__ import annotations

import subprocess


def test_plain_intake_empty_promoted_flacs_is_fatal() -> None:
    snippet = r"""
#!/usr/bin/env bash
set -euo pipefail

err() {
  echo "Error: $*" >&2
  exit 1
}

EXECUTE=1
DJ_MODE=0
M3U_MODE=0
PROMOTED_AUDIO_COUNT=0
PROMOTED_FLACS_COUNT=0

if [[ "$EXECUTE" -eq 1 && "$DJ_MODE" -eq 0 && "$M3U_MODE" -eq 0 && "$PROMOTED_FLACS_COUNT" -eq 0 ]]; then
  if [[ "$PROMOTED_AUDIO_COUNT" -gt 0 ]]; then
    err "Promotion produced $PROMOTED_AUDIO_COUNT audio file(s) but zero FLAC masters. Aborting canonical intake."
  fi
  err "No FLAC files were promoted in this run. Aborting canonical intake."
fi
"""
    result = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True)
    assert result.returncode == 1
    assert "No FLAC files were promoted in this run" in result.stderr
