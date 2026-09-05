"""Strict audit of every question in questions.json against the live engine.

    python scripts/audit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.repository import get_repository  # noqa: E402
from app.services.audit import audit  # noqa: E402


def main() -> int:
    rows = audit(get_repository())
    width = 78
    print("=" * width)
    print("STRICT AUDIT vs questions.json (field-by-field, no fuzzy matching)")
    print("=" * width)
    for row in rows:
        mark = "PASS" if row["passed"] else "FAIL"
        print(f"{mark}  {row['id']} T{row['tier']}  {row['detail'][:100]}")
    failed = [r for r in rows if not r["passed"]]
    print("-" * width)
    print(f"{len(rows) - len(failed)}/{len(rows)} pass")
    if failed:
        print(f"\n{len(failed)} FAILING:")
        for row in failed:
            print(f"\n  {row['id']}: {row['question'][:96]}")
            print(f"     -> {row['detail'][:400]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
