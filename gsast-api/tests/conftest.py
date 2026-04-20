"""
Test configuration for gsast-api tests.

This file ensures that gsast_api and gsast_core can be imported when running tests.
"""

import sys
from pathlib import Path

# Resolve the monorepo root (GSAST/) from this file's location: gsast-api/tests/conftest.py
monorepo_root = Path(__file__).parent.parent.parent

sys.path.insert(0, str(monorepo_root / "gsast-core"))
sys.path.insert(0, str(monorepo_root / "gsast-worker"))
sys.path.insert(0, str(monorepo_root / "gsast-api"))
