#!/usr/bin/env python3
"""Root wrapper: forward to canonical script in scripts/verify_post_move.py"""
import os
import sys

_ROOT = os.path.dirname(__file__)
SCRIPT = os.path.join(_ROOT, 'scripts', 'verify_post_move.py')

os.execv(sys.executable, [sys.executable, SCRIPT] + sys.argv[1:])