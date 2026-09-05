# Architecture — where the LLM stops and the arithmetic starts

The central question in the brief is *"what should the language model do, what should
deterministic code do, and how do you compose them?"* This is our answer.

**The LLM is allowed to reason about what to ask. It is not allowed to invent what is
true.** Everything below follows from that one line.

---

## 1. The boundary

```
                        ┌──────────────────────────────┐
                        │        CREW CONTROLLER        │
                        │   natural language, one box   │
                        └───────────────┬──────────────┘
                                        │
                        ┌───────────────▼──────────────┐
                        │      CONSOLE (React + TS)     │
                        │  answer · impact graph ·      │
                        │  ranked options · evidence    │
                        └───────────────┬──────────────┘
                                        │  one JSON envelope
                        ┌───────────────▼──────────────┐
                        │      FastAPI  /api/*          │
                        └───────────────┬──────────────┘
                                        │
        ╔═══════════════════════════════▼═══════════════════════════════╗
        ║                    LANGUAGE  &  INTENT                        ║
        ║                                                               ║
        ║   LLM orchestrator            ── understands the question     ║
        ║   (Groq / Gemini / OpenAI)    ── picks tools + arguments      ║
        ║                               ── phrases the final answer     ║
        ║                                                               ║
        ║   Deterministic router        ── same job, no model, always   ║
        ║   (regex + entity resolver)      available as the fallback    ║
        ╚═══════════════════════════════╤═══════════════════════════════╝
                                        │  15 typed tools
        ════════════════════════════════╪════════════════════════════════
                     T H E   B O U N D A R Y   —  nothing above
                     computes a fact; nothing below writes prose
        ════════════════════════════════╪════════════════════════════════
        ╔═══════════════════════════════▼═══════════════════════════════╗
        ║                  D E T E R M I N I S T I C   C O R E          ║
        ║                                                               ║
        ║  Rules engine     7 modules, one per rule, each returning     ║
        ║                   {status, actual, limit, signed margin}      ║
        ║  Impact graph     crew → pairing → day → leg → rotation       ║
        ║  Scenario state   copy-on-write; a what-if never mutates      ║
        ║  Candidates       every same-rank crew, fully rule-checked    ║
        ║  Chains           beam search over multi-step swaps           ║
        ║  Splitting        re-crew the illegal tail of a delayed duty  ║
        ║  Closure          delay-to-reopen per leg, FDP-checked        ║
        ║  Joint            simultaneous vacancies, no crew used twice  ║
        ║  Relaxation       invert the margin: what would make it legal ║
        ║  Cost             callout · deadhead · delay · cancellation   ║
        ║  Resilience       what recovery capacity survives the choice  ║
        ║  Ranking          hard-filter illegal, then rank legal        ║
        ╚═══════════════════════════════╤═══════════════════════════════╝
                                        │
                        ┌───────────────▼──────────────┐
                        │   EVIDENCE LEDGER             │
                        │   every fact + its source     │
                        └───────────────┬──────────────┘
                                        │
                        ┌───────────────▼──────────────┐
                        │   GROUNDING VERIFIER          │
                        │   every id, figure and rule   │
                        │   in the prose must appear    │
                        │   in the ledger, or it is     │
                        │   stripped and flagged        │
                        └───────────────┬──────────────┘
                                        │
                        ┌───────────────▼──────────────┐
                        │   SQLite  (16 tables)        │
                        │   loaded once into memory    │
                        └──────────────────────────────┘
```

## 2. What crosses the boundary

| Direction | Carries | Never carries |
|---|---|---|
| LLM → core | tool name + arguments (ids, dates, stations) | duty hours, costs, verdicts |
| core → LLM | a compact digest: summary, top options, rule verdicts | raw tables it might reinterpret |
| core → UI | the full structured payload | anything the model touched |

The model never sees the whole option list, and the UI never receives a number the model
wrote. They are fed from the same engine result by different paths, which is why the
displayed cost and the spoken cost cannot disagree.

## 3. One request, end to end

> *"Captain C-1042 just called in sick for tomorrow. What should I do?"*

```
 1  LLM reads the question, calls recommend_recovery(pairing=P-2291, role=Captain,
                                                     crew_out=C-1042)
 2  Impact graph   C-1042 → P-2291 → 6 legs over 2 days → 486 pax on day 1
 3  Candidates     24 active captains evaluated against all 7 rules
 4  Hard filter    19 rejected, each with a reason:
                     C-2087  RULE-DUTY-02  would exceed 60h/7d by 1h20m (61.33h)
                     C-2091  RULE-QUAL-05  no A320 rating (holds ATR72)
                     C-3305  RULE-BASE-07  on-call 00:00-05:30Z ≠ 06:00Z report
 5  Cost           reserve 18,500 · day-off 24,000 · DEL deadhead 41,200
 6  Resilience     "4 of 5 legal captains remain; 4 upcoming pairings would be
                    left with one or no cover"
 7  Rank           5 legal options + cancellation (1,500,000) as the baseline
 8  Ledger         33 evidence rows recorded
 9  LLM writes     "Assign Captain C-3310 (reserve callout) — INR 18,500 …"
10  Verifier       C-3310 ✓  18,500 ✓  24,000 ✓  all 7 rule ids ✓  → grounded
```

Steps 2–8 are pure Python. Steps 1 and 9 are the only places the model appears.

## 4. Three properties that fall out of the design

**It cannot state an ungrounded fact.** Not "it is prompted not to" — the verifier
extracts every crew id, flight number, pairing, rule id and money figure from the
finished prose and asserts each against the ledger. Unicode dashes are normalised first,
because a model writing `C‑3310` with a non-breaking hyphen would otherwise slip past the
check that exists to catch it.

**It cannot go dark.** The deterministic router answers the same 15 tools with no model
at all. Set `LLM_ENABLED=false` and the console still works — terser, still correct. The
LLM is an interface upgrade, not a dependency.

**A what-if cannot change the roster.** `OperationalState` is frozen; every event returns
a new state. Scenarios branch from the base snapshot and cannot contaminate each other,
which is also why simultaneous disruptions are layered onto one state and solved jointly
rather than one at a time.

## 5. Where it would strain at real scale

Honest limits, since the brief asks:

- **Loading the whole operation into memory** is right for 150 crew and 147 legs and
  wrong for 15,000 crew. The repository is the single seam: it is the only module that
  touches SQL, so Postgres plus per-query loading replaces it without the engine noticing.
- **Candidate enumeration is O(crew × rules)** — 2 ms here, minutes at fleet scale. The
  fix is a precomputed legality matrix (every crew x pairing-day, maintained
  incrementally on roster change). We deliberately did NOT build it: it answers a
  performance problem this dataset does not have, and an unused index is worse than
  none. It is the first thing we would add at real scale.
- **Beam search over swap chains** is bounded by width and depth, not by fleet size, so
  it scales; what grows is the candidate pool feeding it, which the matrix above would
  solve.
- **Sessions are in-process.** Multi-turn context lives in a dict. Real deployment needs
  Redis or a database; nothing else in the design assumes a single process.
