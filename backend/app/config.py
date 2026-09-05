"""Single source of runtime configuration. Everything env-driven, nothing hardcoded."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:  # dotenv is convenience only
    pass

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT_DIR / "data"))
DB_PATH = Path(os.getenv("DB_PATH", BACKEND_DIR / "db" / "crew_ops.db"))

# The dataset's frozen "now". Every relative date ("tomorrow") resolves against this.
SNAPSHOT_UTC = datetime(2026, 9, 14, 18, 0, 0, tzinfo=timezone.utc)
WEEK_START = "2026-09-14"
WEEK_END = "2026-09-20"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").strip().lower()
LLM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile").strip()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip()
LLM_ENABLED = os.getenv("LLM_ENABLED", "true").strip().lower() == "true" and bool(LLM_API_KEY)

CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

# Recovery search
BEAM_WIDTH = int(os.getenv("BEAM_WIDTH", "8"))
MAX_CHAIN_DEPTH = int(os.getenv("MAX_CHAIN_DEPTH", "3"))
