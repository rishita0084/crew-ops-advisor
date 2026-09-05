-- Normalized operational store. Rebuilt idempotently by scripts/import_data.py.
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS risk_signals;
DROP TABLE IF EXISTS costs;
DROP TABLE IF EXISTS rules;
DROP TABLE IF EXISTS certifications;
DROP TABLE IF EXISTS reserve_dates;
DROP TABLE IF EXISTS reserve_pool;
DROP TABLE IF EXISTS duty_history;
DROP TABLE IF EXISTS duty_clocks;
DROP TABLE IF EXISTS pairing_crew;
DROP TABLE IF EXISTS pairing_day_flights;
DROP TABLE IF EXISTS pairing_days;
DROP TABLE IF EXISTS flagged_exceptions;
DROP TABLE IF EXISTS pairings;
DROP TABLE IF EXISTS flights;
DROP TABLE IF EXISTS crew_ratings;
DROP TABLE IF EXISTS crew;

CREATE TABLE crew (
    crew_id              TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    rank                 TEXT NOT NULL,
    base                 TEXT NOT NULL,
    seniority            INTEGER,
    reachability_minutes INTEGER,
    status               TEXT NOT NULL
);

CREATE TABLE crew_ratings (
    crew_id       TEXT NOT NULL REFERENCES crew(crew_id),
    aircraft_type TEXT NOT NULL,
    PRIMARY KEY (crew_id, aircraft_type)
);

CREATE TABLE flights (
    flight_id     TEXT PRIMARY KEY,
    flight_no     TEXT NOT NULL,
    date          TEXT NOT NULL,
    dep_station   TEXT NOT NULL,
    arr_station   TEXT NOT NULL,
    dep_utc       TEXT NOT NULL,
    arr_utc       TEXT NOT NULL,
    block_hours   REAL NOT NULL,
    aircraft      TEXT NOT NULL,
    aircraft_type TEXT NOT NULL,
    seats         INTEGER NOT NULL
);
CREATE INDEX idx_flights_date ON flights(date);
CREATE INDEX idx_flights_dep ON flights(dep_station, date);
CREATE INDEX idx_flights_no ON flights(flight_no);

CREATE TABLE pairings (
    pairing_id TEXT PRIMARY KEY,
    aircraft   TEXT NOT NULL
);

CREATE TABLE pairing_days (
    pairing_id  TEXT NOT NULL REFERENCES pairings(pairing_id),
    day_index   INTEGER NOT NULL,
    date        TEXT NOT NULL,
    report_utc  TEXT NOT NULL,
    release_utc TEXT NOT NULL,
    PRIMARY KEY (pairing_id, day_index)
);
CREATE INDEX idx_pday_date ON pairing_days(date);

CREATE TABLE pairing_day_flights (
    pairing_id TEXT NOT NULL,
    day_index  INTEGER NOT NULL,
    leg_index  INTEGER NOT NULL,
    flight_id  TEXT NOT NULL REFERENCES flights(flight_id),
    PRIMARY KEY (pairing_id, day_index, leg_index)
);
CREATE INDEX idx_pdf_flight ON pairing_day_flights(flight_id);

CREATE TABLE pairing_crew (
    pairing_id TEXT NOT NULL REFERENCES pairings(pairing_id),
    crew_id    TEXT NOT NULL REFERENCES crew(crew_id),
    role       TEXT NOT NULL,
    PRIMARY KEY (pairing_id, crew_id)
);
CREATE INDEX idx_pcrew_crew ON pairing_crew(crew_id);

CREATE TABLE flagged_exceptions (
    crew_id TEXT NOT NULL,
    date    TEXT NOT NULL,
    rule    TEXT NOT NULL,
    note    TEXT
);

CREATE TABLE duty_clocks (
    crew_id          TEXT PRIMARY KEY REFERENCES crew(crew_id),
    as_of_utc        TEXT NOT NULL,
    duty_hours_7d    REAL NOT NULL,
    flight_hours_28d REAL NOT NULL,
    last_rest_ended  TEXT
);

CREATE TABLE duty_history (
    crew_id      TEXT NOT NULL REFERENCES crew(crew_id),
    date         TEXT NOT NULL,
    duty_hours   REAL NOT NULL,
    flight_hours REAL NOT NULL,
    PRIMARY KEY (crew_id, date)
);

CREATE TABLE reserve_pool (
    crew_id      TEXT PRIMARY KEY REFERENCES crew(crew_id),
    base         TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end   TEXT NOT NULL,
    note         TEXT
);

CREATE TABLE reserve_dates (
    crew_id TEXT NOT NULL REFERENCES reserve_pool(crew_id),
    date    TEXT NOT NULL,
    PRIMARY KEY (crew_id, date)
);

CREATE TABLE certifications (
    crew_id    TEXT NOT NULL REFERENCES crew(crew_id),
    cert_type  TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to   TEXT NOT NULL,
    PRIMARY KEY (crew_id, cert_type)
);
CREATE INDEX idx_cert_to ON certifications(valid_to);

CREATE TABLE rules (
    rule_id TEXT PRIMARY KEY,
    text    TEXT NOT NULL,
    params  TEXT NOT NULL          -- JSON blob; rule modules read limits from here
);

CREATE TABLE costs (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE risk_signals (
    crew_id               TEXT PRIMARY KEY REFERENCES crew(crew_id),
    as_of_utc             TEXT NOT NULL,
    disruption_risk_score REAL NOT NULL,
    drivers               TEXT NOT NULL   -- JSON array
);
