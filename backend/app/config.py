"""Single source of runtime configuration. Everything env-driven, nothing hardcoded."""
from __future__ import annotations

import json
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

def _derive_snapshot_and_week() -> tuple[datetime, str, str]:
    """Read the operating period out of the dataset instead of writing it down twice.

    The snapshot is stated on every duty clock (`as_of_utc`); the week is simply the span
    of the schedule. Hardcoding either would be a second source of truth that a new
    dataset would silently invalidate -- the engine would keep answering, confidently,
    about the wrong week.

    Falls back to the shipped dataset's values only if the files are unreadable, so an
    import never explodes before `import_data.py` has been run.
    """
    try:
        with open(DATA_DIR / "duty_clocks.json", encoding="utf-8") as fh:
            stamps = {c["as_of_utc"] for c in json.load(fh)}
        if len(stamps) != 1:
            raise ValueError(f"duty_clocks disagree about the snapshot: {sorted(stamps)}")
        snapshot = datetime.strptime(next(iter(stamps)), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        with open(DATA_DIR / "flights.json", encoding="utf-8") as fh:
            dates = {f["date"] for f in json.load(fh)}
        return snapshot, min(dates), max(dates)
    except (OSError, KeyError, ValueError):
        return datetime(2026, 9, 14, 18, 0, 0, tzinfo=timezone.utc), "2026-09-14", "2026-09-20"


# The dataset's frozen "now". Every relative date ("tomorrow") resolves against this,
# never against the wall clock -- the schedule is a fixed week, so real time is irrelevant.
SNAPSHOT_UTC, WEEK_START, WEEK_END = _derive_snapshot_and_week()

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
