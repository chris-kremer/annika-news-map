#!/usr/bin/env python3

from __future__ import annotations

import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))
runpy.run_path(str(SCRIPTS / "serve_app.py"), run_name="__main__")
