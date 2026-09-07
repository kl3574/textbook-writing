#!/usr/bin/env python3
"""Compatibility CLI; publication must use verify_release.py and its common manifest."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import legacy_browser

if __name__=='__main__':
    print('WARNING: legacy browser receipt is not release approval; use verify_release.py',file=sys.stderr)
    raise SystemExit(legacy_browser.main())
