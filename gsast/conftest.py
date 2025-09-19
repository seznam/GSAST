"""
Pytest configuration for Global SAST Scanner tests.

This file ensures proper Python path setup for running tests.
"""

import sys
import os
from pathlib import Path

# Add the gsast directory to Python path
gsast_root = Path(__file__).parent
sys.path.insert(0, str(gsast_root))

# Also add the parent directory for any potential cross-package imports
project_root = gsast_root.parent  
sys.path.insert(0, str(project_root))
