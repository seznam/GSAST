"""
Test configuration for gsast-core tests.

This file ensures that gsast_core can be imported when running tests.
"""

import sys
import os
from pathlib import Path

# Add the gsast-core directory to Python path so gsast_core package can be imported
gsast_core_dir = Path(__file__).parent.parent
sys.path.insert(0, str(gsast_core_dir))
