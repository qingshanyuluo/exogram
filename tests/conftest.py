"""Pytest configuration and fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src directory to Python path for tests
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Check Python version - project requires 3.11+
if sys.version_info < (3, 11):
    pytest.skip(
        "This project requires Python 3.11+",
        allow_module_level=True,
    )
