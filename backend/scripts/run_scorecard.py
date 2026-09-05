"""Run the dataset's own questions and scenarios through the live engine.

    python scripts/run_scorecard.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.repository import get_repository  # noqa: E402
from app.services.scorecard import run_scorecard  # noqa: E402


def main() -> int:
    card = run_scorecard(get_repository())
    print("=" * 78)
    print("CREW OPS ADVISOR - SCORECARD (computed live, never hardcoded)")
    print("=" * 78)
    for tier in card["tiers"]:
        print(f"  Tier {tier['tier']}    {tier['passed']:>2}/{tier['total']:<2}")
    print(f"  Scenarios {card['scenarios']['passed']:>2}/{card['scenarios']['total']:<2}")
    print(f"  Runtime   {card['total_ms']} ms")
    failures = [c for c in card["cases"] if not c["passed"]]
    if failures:
        print(f"\n{len(failures)} FAILING:")
        for c in failures:
            print(f"  {c['id']} T{c['tier']}: {c['detail'][:150]}")
    else:
        print("\nAll cases pass.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
