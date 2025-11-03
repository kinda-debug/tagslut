#!/usr/bin/env python3
"""Root wrapper: forward to canonical script in scripts/apply_dedupe_plan.py"""
import os
import sys

_ROOT = os.path.dirname(__file__)
SCRIPT = os.path.join(_ROOT, 'scripts', 'apply_dedupe_plan.py')

os.execv(sys.executable, [sys.executable, SCRIPT] + sys.argv[1:])
