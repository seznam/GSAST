"""
Test configuration for GSAST tests.

This file ensures that the gsast package can be imported when running tests.
"""

import sys
import os
from pathlib import Path

# Add the gsast directory to Python path so gsast package can be imported
gsast_dir = Path(__file__).parent.parent
sys.path.insert(0, str(gsast_dir.parent)) 