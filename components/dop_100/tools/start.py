# SPDX-License-Identifier: Apache-2.0
"""Portable source-archive launcher; Python standard library only."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from universal_diascreen_hmi.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
