"""Entity extraction from controller language.

Deliberately deterministic. The LLM is better at this, but the system has to keep
working when the LLM is unavailable, and IDs are exactly the thing we must not let a
model guess at. Relative dates resolve against the dataset's frozen snapshot.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.config import SNAPSHOT_UTC

SNAPSHOT_DATE = SNAPSHOT_UTC.date()

CREW_RE = re.compile(r"\bC-\d{4}\b", re.I)
PAIRING_RE = re.compile(r"\bP-\d{4}\b", re.I)
FLIGHT_NO_RE = re.compile(r"\bDX\d{3}\b", re.I)
FLIGHT_ID_RE = re.compile(r"\bDX\d{3}-\d{4}-\d{2}-\d{2}\b", re.I)
TAIL_RE = re.compile(r"\bVT-[A-Z]{3}\b", re.I)
ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
DAY_MONTH_RE = re.compile(
    r"\b(\d{1,2})\s*(sep|sept|september|oct|october)\b", re.I
)
# Accepts 08:00-14:00Z, 08:00 to 14:00Z, 08:00 until 14:00Z, 0800-1400Z and the
# typographic dashes a pasted brief tends to carry.
TIME_RANGE_RE = re.compile(
    r"\b(\d{1,2}:?\d{2})\s*(?:[-–—−]|to|until|till|through)\s*(\d{1,2}:?\d{2})\s*Z?",
    re.I,
)
TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\s*Z\b", re.I)
MINUTES_RE = re.compile(r"\b(\d{1,3})\s*(?:-|\s)?minutes?\b", re.I)
HOURS_RE = re.compile(r"\b(\d{1,2}(?:\.\d)?)\s*(?:-|\s)?hours?\b", re.I)
DAYS_RE = re.compile(r"\b(\d{1,3})\s*days?\b", re.I)

RANKS = {
    "captain": "Captain",
    "captains": "Captain",
    "first officer": "First Officer",
    "first officers": "First Officer",
    "fo": "First Officer",
    "senior cabin crew": "Senior Cabin Crew",
    "cabin crew": "Cabin Crew",
}

MONTHS = {"sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10}


@dataclass
class Entities:
    crew_ids: list[str] = field(default_factory=list)
    pairing_ids: list[str] = field(default_factory=list)
    flight_nos: list[str] = field(default_factory=list)
    flight_ids: list[str] = field(default_factory=list)
    tails: list[str] = field(default_factory=list)
    stations: list[str] = field(default_factory=list)
    dates: list[date] = field(default_factory=list)
    rank: str | None = None
    time_range: tuple[str, str] | None = None
    minutes: int | None = None
    hours: float | None = None
    days: int | None = None

    @property
    def crew_id(self) -> str | None:
        return self.crew_ids[0] if self.crew_ids else None

    @property
    def pairing_id(self) -> str | None:
        return self.pairing_ids[0] if self.pairing_ids else None

    @property
    def date(self) -> date | None:
        return self.dates[0] if self.dates else None

    @property
    def station(self) -> str | None:
        return self.stations[0] if self.stations else None


def resolve_relative_date(text: str) -> date | None:
    low = text.lower()
    if "day after tomorrow" in low:
        return SNAPSHOT_DATE + timedelta(days=2)
    if "tomorrow" in low:
        return SNAPSHOT_DATE + timedelta(days=1)
    if "today" in low or "tonight" in low:
        return SNAPSHOT_DATE
    if "yesterday" in low:
        return SNAPSHOT_DATE - timedelta(days=1)
    return None


def _hhmm(value: str) -> str:
    """Normalise 0800 / 8:00 to 08:00 so downstream time handling is uniform."""
    if ":" not in value:
        value = value.zfill(4)
        value = f"{value[:2]}:{value[2:]}"
    hour, minute = value.split(":")
    return f"{int(hour):02d}:{minute}"


def extract(text: str, known_stations: set[str] | None = None) -> Entities:
    ent = Entities()
    upper = text.upper()

    ent.crew_ids = sorted({m.upper() for m in CREW_RE.findall(text)})
    ent.pairing_ids = sorted({m.upper() for m in PAIRING_RE.findall(text)})
    ent.flight_ids = sorted({m.upper() for m in FLIGHT_ID_RE.findall(text)})
    ent.tails = sorted({m.upper() for m in TAIL_RE.findall(text)})

    # a bare DX412 is a flight number; strip any that were part of a full flight id
    full = " ".join(ent.flight_ids)
    ent.flight_nos = sorted(
        {m.upper() for m in FLIGHT_NO_RE.findall(text) if m.upper() not in full}
    )

    if known_stations:
        ent.stations = [s for s in sorted(known_stations) if re.search(rf"\b{s}\b", upper)]

    seen: list[date] = []
    for raw in ISO_DATE_RE.findall(text):
        try:
            seen.append(date.fromisoformat(raw))
        except ValueError:
            continue
    for day, month in DAY_MONTH_RE.findall(text):
        seen.append(date(SNAPSHOT_DATE.year, MONTHS[month.lower()], int(day)))
    relative = resolve_relative_date(text)
    if relative:
        seen.append(relative)
    ent.dates = sorted(dict.fromkeys(seen))

    low = text.lower()
    for key in sorted(RANKS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(key)}\b", low):
            ent.rank = RANKS[key]
            break

    tr = TIME_RANGE_RE.search(text)
    if tr:
        ent.time_range = (_hhmm(tr.group(1)), _hhmm(tr.group(2)))

    m = MINUTES_RE.search(text)
    if m:
        ent.minutes = int(m.group(1))
    h = HOURS_RE.search(text)
    if h:
        ent.hours = float(h.group(1))
    d = DAYS_RE.search(text)
    if d:
        ent.days = int(d.group(1))

    return ent
