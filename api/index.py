import os
import sys

# Make the project root (where app.py, templates/, static/ live) importable,
# since this file lives one directory deeper under api/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402  (Vercel's Python runtime looks for `app` here)
