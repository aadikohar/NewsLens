import sys
import os
from pathlib import Path

# Add root directory to sys.path for local module resolution
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from database import ensure_initialized
ensure_initialized()

from app import app

