"""Pytest bootstrap: ensure the backend package root is importable."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("GROQ_API_KEY", "test-key")
