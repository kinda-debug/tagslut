#!/usr/bin/env python3
import runpy
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "metadata_scripts" / "metadata_audit.py"
runpy.run_path(str(TARGET), run_name="__main__")
