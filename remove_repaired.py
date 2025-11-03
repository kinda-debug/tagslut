#!/usr/bin/env python3
"""Root wrapper: forward to canonical script in scripts/remove_repaired.py"""
import os
import sys

_ROOT = os.path.dirname(__file__)
SCRIPT = os.path.join(_ROOT, 'scripts', 'remove_repaired.py')

os.execv(sys.executable, [sys.executable, SCRIPT] + sys.argv[1:])
