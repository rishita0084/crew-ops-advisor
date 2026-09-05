"""Time arithmetic for the ruleset. Every duty/rest/window calculation routes through here.

Dataset conventions (rules.json):
  - All times UTC.
  - Duty period = report -> release. Report = first dep - 60min; release = last arr + 30min.
  - RULE-DUTY-02 / RULE-FLT-03 windows are CALENDAR-DAY windows (UTC dates), inclusive
    of the duty date -- not rolling 168/672 hour windows.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

ISO_FMT = "%Y-%m-%dT%H:%M:%SZ"


def parse_utc(value: str) -> datetime:
    """Parse the dataset's Zulu timestamp format into a naive-UTC datetime."""
    return datetime.strptime(value, ISO_FMT)


def fmt_utc(value: datetime) -> str:
    return value.strftime(ISO_FMT)


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def hours_between(start: datetime, end: datetime) -> float:
    return round((end - start).total_seconds() / 3600.0, 2)


def calendar_window(end: date, days: int) -> tuple[date, date]:
    """Inclusive calendar-day window of `days` dates ending on `end`."""
    return end - timedelta(days=days - 1), end


def in_window(day: date, window: tuple[date, date]) -> bool:
    return window[0] <= day <= window[1]


def time_on_date(day: date, hhmm: str) -> datetime:
    """Combine a UTC date with an 'HH:MM' clock time (reserve on-call windows)."""
    hour, minute = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute)


def fmt_hours_minutes(value: float) -> str:
    """0.83 -> '0h50m'. Used verbatim in rule detail strings shown to controllers."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    whole = int(value)
    minutes = int(round((value - whole) * 60))
    if minutes == 60:
        whole, minutes = whole + 1, 0
    return f"{sign}{whole}h{minutes:02d}m"
