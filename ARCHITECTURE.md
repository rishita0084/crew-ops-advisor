# Architecture — where the LLM stops and the arithmetic starts

The central question in the brief is *"what should the language model do, what should
deterministic code do, and how do you compose them?"* This is our answer.

**The LLM is allowed to reason about what to ask. It is not allowed to invent what is
true.** Everything below follows from that one line.

---

## 1. The boundary

```
        CONSOLE (React + TS)                    ANY MCP CLIENT
        answer · impact graph ·                 Claude Desktop, an IDE,
        ranked options · evidence               another agent
                  │                                     │
                  │ HTTP                                │ stdio
                  ▼                                     ▼
        ┌──────────────────┐                  ┌──────────────────┐
        │  FastAPI /api/*  │                  │  mcp_server/     │
        └────────┬─────────┘                  └────────┬─────────┘
                 │                                     │
    ╔════════════▼═════════════════════════════════════▼═══════════╗
    ║                     LANGUAGE  &  INTENT                       ║
    ║                                                               ║
    ║  LLM orchestrator        -- reads the question                ║
    ║  (Groq / Gemini /        -- picks tools + arguments           ║
    ║   any OpenAI-compatible) -- phrases the final answer          ║
    ║                                                               ║
    ║  Deterministic router    -- narrows which tools the model may ║
    ║  (entity + intent)          choose from, and answers alone    ║
    ║                             when there is no model at all     ║
    ╚════════════════════════════╤══════════════════════════════════╝
                                 │  15 typed tools
    ═════════════════════════════╪══════════════════════════════════
              T H E   B O U N D A R Y   --  nothing above computes
              a fact; nothing below writes prose
    ═════════════════════════════╪══════════════════════════════════
    ╔════════════════════════════▼══════════════════════════════════╗
    ║              D E T E R M I N I S T I C   C O R E              ║
    ║                                                               ║
    ║  Rules engine    7 modules, one per rule, each returning      ║
    ║                  {status, actual, limit, signed margin}       ║
    ║  Impact graph    crew -> pairing -> day -> leg -> rotation    ║
    ║  Scenario state  copy-on-write; a what-if never mutates       ║
    ║  Candidates      every same-rank crew, fully rule-checked     ║
    ║  Joint           simultaneous vacancies, no crew used twice   ║
    ║  Closure         delay-to-reopen per leg, FDP-checked         ║
    ║  Splitting       re-crew the illegal tail of a delayed duty   ║
    ║  Chains          beam search over multi-step swaps            ║
    ║  Relaxation      invert the margin: what would make it legal  ║
    ║  Cost            callout · deadhead · delay · cancellation    ║
    ║  Resilience      what recovery capacity survives the choice   ║
    ║  Ranking         hard-filter illegal, then rank legal         ║
    ╚════════════════════════════╤══════════════════════════════════╝
                                 │
                  ┌──────────────▼──────────────┐
                  │  EVIDENCE LEDGER            │
                  │  every fact and its source  │
                  └──────────────┬──────────────┘
                                 │
                  ┌──────────────▼──────────────┐
                  │  GROUNDING VERIFIER         │
                  │  every id, figure and rule  │
                  │  in the prose must appear   │
                  │  in the ledger, or it is    │
                  │  flagged and shown as such  │
                  └──────────────┬──────────────┘
                                 │
                  ┌──────────────▼──────────────┐
                  │  SQLite (16 tables)         │
                  │  rebuilt from JSON if       │
                  │  missing; loaded once into  │
                  │  memory, then read-only     │
                  └─────────────────────────────┘
```

### The store bootstraps itself

The database is a cache of the committed JSON, not a separate source of truth, so the app
imports it at startup when the file is absent rather than refusing to start. That matters
on any host with an ephemeral filesystem — a redeploy keeps the code and the dataset but
loses the generated file — and it removes the setup step a first-time reader is most
likely to miss.

### Conventions come from the data, not from the code

Four facts the engine needs are stated by the dataset, so `domain/conventions.py` derives
them at load instead of repeating them:

| Fact | Derived from |
|---|---|
| The snapshot ("now") | `duty_clocks.as_of_utc` |
| The operating week | min/max `flights.date` |
| Crew complement per aircraft type | the shapes actually rostered |
| Report / release brackets | the observed gap to first departure and last arrival |

Each derivation asserts the dataset agrees with itself and raises if it does not. Writing
any of these down in code would create a second source of truth that a new dataset could
silently invalidate — the engine would keep answering, confidently, about the wrong week.

## 2. What crosses the boundary

| Direction | Carries | Never carries |
|---|---|---|
| LLM → core | tool name + arguments (ids, dates, stations) | duty hours, costs, verdicts |
| core → LLM | a compact digest: summary, top options, rule verdicts | raw tables it might reinterpret |
| core → UI | the full structured payload | anything the model touched |

Two consequences worth stating.

**The model never sees the whole result.** `_digest()` hands it the summary, the leading
options and the rule verdicts — enough to write a sentence, not enough to re-derive one.
The full payload reaches the UI on a separate path, which is why the cost on the card and
the cost in the sentence cannot disagree.

**The deterministic layer narrows the menu before the model chooses.** `relevant_tools()`
reads the question and offers 4–7 of the 15 tools rather than all of them. Fewer
distractors, and on a free-tier token budget the schema alone had been costing ~1,560
tokens per round. Deterministic code narrows; the model picks within that.

## 3. One request, end to end

> *"Captain C-1042 just called in sick for tomorrow. What should I do?"*

```
 1  LLM reads the question, calls recommend_recovery(pairing=P-2291, role=Captain,
                                                     crew_out=C-1042)
 2  Impact graph   C-1042 -> P-2291 -> 6 legs over 2 days -> 486 pax on day 1
 3  Candidates     24 active captains evaluated against all 7 rules
 4  Hard filter    19 rejected, each with its rule and its arithmetic:
                     C-2087  RULE-DUTY-02  would exceed 60h/7d by 1h20m (61.33h)
                     C-2091  RULE-QUAL-05  no A320 rating (holds ATR72)
                     C-3305  RULE-BASE-07  on-call 00:00-05:30Z vs 06:00Z report
 5  Cost           reserve 18,500 · day-off 24,000 · DEL deadhead 41,200
 6  Resilience     "4 of 5 legal captains remain; 4 upcoming pairings would be
                    left with one or no cover"
 7  Rank           5 legal options + cancellation (1,500,000) as the baseline
 8  Ledger         33 evidence rows recorded
 9  LLM writes     "Assign Captain C-3310 (reserve callout) - INR 18,500 ..."
10  Verifier       C-3310 ok · 18,500 ok · 24,000 ok · all 7 rule ids ok -> grounded
```

Steps 2–8 are pure Python. Steps 1 and 9 are the only places the model appears.

## 4. Two doors, one engine

The console talks HTTP to FastAPI. Any MCP client talks stdio to `mcp_server/index.py`.
Both land on the same `tools.dispatch()`, so there is one rules engine, one cost model and
one source of truth behind both.

```
Claude Desktop --spawns--> python mcp_server/index.py
               --stdin---> {"method":"tools/call", ...}
               <--stdout-- {"result": {...}}
```

Nothing listens on a port for MCP: the client owns the process and kills it on exit, which
is also why MCP keeps working when the API server is down. A test asserts both doors return
identical answers to the same question, so they cannot drift apart. Moving to a remote
server is a one-line transport change (`stdio` → `streamable-http`).

## 5. Properties that fall out of the design

**It cannot state an ungrounded fact.** Not "it is prompted not to" — the verifier extracts
every crew id, flight number, pairing, rule id and money figure from the finished prose and
asserts each against the ledger. Unicode dashes are normalised first, because a model
writing `C‑3310` with a non-breaking hyphen would otherwise slip past the check that exists
to catch it. That was a real escape, not a hypothetical.

**It cannot go dark.** The deterministic router answers the same 15 tools with no model at
all. Set `LLM_ENABLED=false` and the console still works — terser, still correct. When the
model is present but fails mid-conversation, the router is handed the recent turns, so a
pronoun-only follow-up ("why not the cheapest option?") still resolves.

**A what-if cannot change the roster.** `OperationalState` is frozen; every event returns a
new state. Scenarios branch from the base snapshot and cannot contaminate each other, which
is also why simultaneous disruptions are layered onto one state and solved jointly rather
than one at a time.

**Each disruption is modelled as what it actually is.** A sick call empties a seat. A
closure strands a flight. A delay stretches a duty rather than moving it. Collapsing these
into one "something broke" shape is what produces confidently wrong plans — cancelling
thirteen legs when three needed only a delay and ten needed a fresh crew for the tail.

## 6. How we know it is right

`questions.json` is the source of truth for both the arithmetic and the algorithm, so the
grader has to be strict. `app/services/audit.py` holds **one explicit checker per
question** — the exact field, the exact value, no substring matching.

That distinction is not academic. The first grader compared loose token containment at an
80% threshold, reported a clean sheet, and was concealing four real defects: simultaneous
vacancies assigned to one person, closures modelled as crew shortages, exclusion reasons
missing their rule ids, and a recovery intent that never matched. Every one surfaced the
moment the checks became exact.

```
Tier 1 16/16 · Tier 2 14/14 · Tier 3 8/8 · Scenarios 6/6 · 38 tests · ~460 ms
```

Answer keys are fixtures only. No application code reads them and nothing caches their
answers — every case is computed live, then compared.

## 7. Where it would strain at real scale

Honest limits, since the brief asks:

- **Loading the whole operation into memory** is right for 150 crew and 147 legs and wrong
  for 15,000 crew. The repository is the single seam: it is the only module that touches
  SQL, so Postgres plus per-query loading replaces it without the engine noticing.
- **Candidate enumeration is O(crew × rules)** — 2 ms here, minutes at fleet scale. The fix
  is a precomputed legality matrix (every crew × pairing-day, maintained incrementally on
  roster change). We deliberately did **not** build it: it answers a performance problem
  this dataset does not have, and an unused index is worse than none. It is the first thing
  we would add at real scale.
- **Beam search over swap chains** is bounded by width and depth, not by fleet size, so it
  scales; what grows is the candidate pool feeding it, which the matrix above would solve.
- **Joint assignment is exhaustive** over a cost-sorted shortlist — exact and instant for a
  handful of simultaneous vacancies. A fleet-wide event would need a wider shortlist and,
  past roughly six vacancies, a real assignment algorithm.
- **Sessions are in-process.** Multi-turn context lives in a dict. Real deployment needs
  Redis or a database; nothing else in the design assumes a single process.
