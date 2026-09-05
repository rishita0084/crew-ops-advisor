"""Load the dCortex JSON dataset into SQLite. Idempotent: rebuilds from scratch each run.

    python scripts/import_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR, DB_PATH  # noqa: E402
from app.db.connection import connect  # noqa: E402


def _load(name: str):
    with open(DATA_DIR / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    schema = (Path(__file__).resolve().parents[1] / "app" / "db" / "schema.sql").read_text(encoding="utf-8")
    conn = connect()
    conn.executescript(schema)

    crew = _load("crew")
    conn.executemany(
        "INSERT INTO crew VALUES (?,?,?,?,?,?,?)",
        [
            (c["crew_id"], c["name"], c["rank"], c["base"], c.get("seniority"),
             c.get("reachability_minutes"), c.get("status", "active"))
            for c in crew
        ],
    )
    conn.executemany(
        "INSERT INTO crew_ratings VALUES (?,?)",
        [(c["crew_id"], r) for c in crew for r in c.get("ratings", [])],
    )

    flights = _load("flights")
    conn.executemany(
        "INSERT INTO flights VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            (f["flight_id"], f["flight_no"], f["date"], f["dep_station"], f["arr_station"],
             f["dep_utc"], f["arr_utc"], f["block_hours"], f["aircraft"], f["aircraft_type"], f["seats"])
            for f in flights
        ],
    )

    rosters = _load("rosters")
    for p in rosters["pairings"]:
        conn.execute("INSERT INTO pairings VALUES (?,?)", (p["pairing_id"], p["aircraft"]))
        for di, day in enumerate(p["days"]):
            conn.execute(
                "INSERT INTO pairing_days VALUES (?,?,?,?,?)",
                (p["pairing_id"], di, day["date"], day["report_utc"], day["release_utc"]),
            )
            for li, fid in enumerate(day["flights"]):
                conn.execute(
                    "INSERT INTO pairing_day_flights VALUES (?,?,?,?)",
                    (p["pairing_id"], di, li, fid),
                )
        for m in p["crew"]:
            conn.execute(
                "INSERT INTO pairing_crew VALUES (?,?,?)",
                (p["pairing_id"], m["crew_id"], m["role"]),
            )
    conn.executemany(
        "INSERT INTO flagged_exceptions VALUES (?,?,?,?)",
        [(x["crew_id"], x["date"], x["rule"], x.get("note")) for x in rosters.get("flagged_exceptions", [])],
    )

    clocks = _load("duty_clocks")
    conn.executemany(
        "INSERT INTO duty_clocks VALUES (?,?,?,?,?)",
        [
            (c["crew_id"], c["as_of_utc"], c["duty_hours_7d"], c["flight_hours_28d"], c.get("last_rest_ended"))
            for c in clocks
        ],
    )
    conn.executemany(
        "INSERT INTO duty_history VALUES (?,?,?,?)",
        [
            (c["crew_id"], h["date"], h["duty_hours"], h["flight_hours"])
            for c in clocks for h in c.get("daily_history", [])
        ],
    )

    reserves = _load("reserve_pool")
    conn.executemany(
        "INSERT INTO reserve_pool VALUES (?,?,?,?,?)",
        [
            (r["crew_id"], r["base"], r["oncall_window_utc"]["start"], r["oncall_window_utc"]["end"], r.get("note"))
            for r in reserves
        ],
    )
    conn.executemany(
        "INSERT INTO reserve_dates VALUES (?,?)",
        [(r["crew_id"], d) for r in reserves for d in r.get("dates", [])],
    )

    conn.executemany(
        "INSERT INTO certifications VALUES (?,?,?,?)",
        [(c["crew_id"], c["cert_type"], c["valid_from"], c["valid_to"]) for c in _load("certifications")],
    )

    rules = _load("rules")
    conn.executemany(
        "INSERT INTO rules VALUES (?,?,?)",
        [(r["rule_id"], r["text"], json.dumps(r.get("params", {}))) for r in rules["rules"]],
    )

    costs = _load("costs")
    conn.executemany(
        "INSERT INTO costs VALUES (?,?)",
        [(k, json.dumps(v)) for k, v in costs.items()],
    )

    conn.executemany(
        "INSERT INTO risk_signals VALUES (?,?,?,?)",
        [
            (r["crew_id"], r["as_of_utc"], r["disruption_risk_score"], json.dumps(r.get("drivers", [])))
            for r in _load("risk_signals")
        ],
    )

    conn.commit()
    counts = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("crew", "flights", "pairings", "pairing_days", "pairing_crew",
                  "duty_history", "reserve_pool", "certifications", "rules", "risk_signals")
    }
    conn.close()
    print(f"Imported into {DB_PATH}")
    for k, v in counts.items():
        print(f"  {k:<20} {v}")


if __name__ == "__main__":
    main()
