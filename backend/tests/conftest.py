"""Shared pytest setup for the backend test suite.

The app resolves paths at import time. Point GENAI_DATA_DIR at a throwaway
directory before any `app.*` import so tests never touch the developer's real
settings/jobs/library.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

_TEST_DATA = Path(tempfile.mkdtemp(prefix="genai-gui-tests-"))
os.environ["GENAI_DATA_DIR"] = str(_TEST_DATA)

atexit.register(lambda: shutil.rmtree(_TEST_DATA, ignore_errors=True))
