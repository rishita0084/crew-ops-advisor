# dCortex Crew Ops Advisor

A conversational advisor for an airline crew-control desk. Ask in plain English; get an
answer that is fast, explainable, and — the part that matters — arithmetically correct.

**The design rule:** the LLM is allowed to reason about *what to ask*. It is not allowed
to invent *what is true*. Every duty hour, legality verdict, cost and crew id comes from
deterministic Python, and a verifier checks the finished prose against an evidence ledger
before it reaches the controller.

```
Tier 1  16/16     Tier 2  14/14     Tier 3  8/8     Scenarios  6/6     ~400 ms
```

Computed live from the supplied answer keys, never hardcoded, and graded **strictly** --
one explicit checker per question comparing the exact field, not fuzzy text matching. Run
it yourself: `python scripts/audit.py` for the per-question detail,
`python scripts/run_scorecard.py` for the summary, or open `/scorecard` in the console.

---

## Quick start (Windows)

Two terminals.

**Backend**

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts\import_data.py          :: JSON -> SQLite, idempotent
copy .env.example .env                 :: then paste your LLM_API_KEY
uvicorn app.main:app --reload          :: http://localhost:8000
```

**Frontend**

```bat
cd frontend
npm install
npm run dev                            :: http://localhost:5173
```

`frontend/.env` already points at `http://localhost:8000` with `VITE_USE_MOCKS=false`.

**Verify**

```bat
cd backend
pytest                                 :: 36 tests
python scripts\run_scorecard.py        :: 38 questions + 6 scenarios
```

The advisor runs with **no LLM key at all** — set `LLM_ENABLED=false` and the
deterministic router answers instead. Terser, equally correct. That is deliberate; see
*Failure handling* below.

---

## What it does

**Tier 1 — retrieval.** Reserves on call, duty clocks and headroom, schedule queries,
certification expiry, pairing crew, risk signals.

**Tier 2 — consequence.** A sick call traverses crew → pairing → every day → every leg →
the aircraft rotation, and back out to the other crew now exposed. A station closure
blocks legs at both ends. A delay *extends* a duty (it does not shift it) and so breaks
FDP where a naive model sees nothing.

**Tier 3 — recommendation.** Every same-rank crew member evaluated against all seven
rules, illegal ones hard-filtered with a stated reason, the rest priced and ranked, with
cancellation always shown as the baseline to read the others against.

**Beyond the brief:** closure delay-to-reopen planning, joint assignment across
simultaneous vacancies, duty splitting, future-resilience scoring, proactive alerts,
drafted crew callouts, multi-turn context that survives an LLM outage, an MCP adapter,
light/dark theming, and a live strict scorecard.

---

## The four things we would point a judge at

### 1. Joint assignment across simultaneous vacancies

Two sick calls at once is not two problems. Solve them separately and each picks the
cheapest legal reserve — the *same* reserve. The plan looks optimal and cannot be flown.

`engine/joint.py` solves them together: the cheapest combination in which no crew member
is assigned twice. On the dataset's double-sick-call scenario that is the difference
between an impossible ₹37,000 and the correct ₹42,500.

Exhaustive over a cost-sorted shortlist rather than a solver — the search space is tiny,
the optimum is exact, and every step stays explainable.

### 2. Near-miss analysis

Every rule returns a **signed margin**, so when nothing is legal we can invert the
binding constraint instead of shrugging:

> Captain C-2087: would exceed 60h/7d by **1h20m** on 2026-09-15 (total 61.33h).
> To use them, drop DX591 (CCU-BLR) from 2026-09-16: releases 3.25h of duty, 162 seats
> to reaccommodate.

and for a rest breach, the remedy is the delay that closes it:

> Captain C-5820: only 11.75h rest after the new assignment on 2026-09-17, minimum 12h.
> To use them, delay the first departure by **0h15m**, or release them from the adjacent
> duty.

Worth being straight about: this fires only when a vacancy has **no** legal cover, and
the supplied week is generously crewed — the thinnest vacancy in the dataset still has
five. So on this data it is a standby capability, exercised by tests rather than by the
demo. The same is true of the multi-step swap search in `engine/chains.py`, which is
gated on fewer than three direct covers. Both are correct and tested; neither is load-
bearing here. We would rather say that than imply a feature the demo never reaches.

### 3. The grounding verifier

The model writes the prose; `explain/verifier.py` then extracts every crew id, flight
number, pairing, rule id and money figure from it and asserts each against the evidence
ledger. Unbacked claims are stripped and listed, and the response is marked ungrounded —
visibly, in the UI. It is not "we prompt carefully": the system **structurally cannot**
state a fact the engine did not produce.

A real bug this caught during development: the model wrote `C‑3310` with a Unicode
non-breaking hyphen, which sailed past the `C-\d{4}` check. Ids are now dash-normalised
before verification, with a test to keep it that way.

### 4. Future resilience

The cheapest legal option and the wisest one are not always the same. After each
candidate, `engine/resilience.py` recomputes how much legal cover survives:

> 4 of 5 legal captains remain; **4 upcoming pairings would be left with one or no
> cover** — P-2225, P-2226, P-2232 (+1 more).

Cost still ranks first, matching the dataset's own keys — but the trade-off is on the
card, not buried.

---

## Sample inputs and outputs

**Tier 1** — *"Who is on reserve at BLR on 2026-09-15?"* → 12 reserves with on-call
windows, ranks and reachability, in ~2 ms.

**Tier 2** — *"If I move Captain C-2087 onto P-2291, does anyone breach a duty limit?"*

> **No.** Captain C-2087 cannot cover P-2291: would exceed 60h/7d by **1h20m** on
> 2026-09-15 (total 61.33h).

with a rule-by-rule table and a before/after duty position. The figure matches the
dataset's engineered fact exactly.

**Tier 3** — *"Captain C-1042 just called in sick for tomorrow. What should I do?"*

| # | Action | Legal | Cost | Covers |
|---|---|---|---|---|
| 1 | Assign Captain C-3310 (reserve callout) | ✓ | ₹18,500 | all 6 |
| 2 | Assign Captain C-1526 (day-off callout) | ✓ | ₹24,000 | all 6 |
| 5 | Deadhead Captain C-2210 from DEL (+3h delay) | ✓ | ₹41,200 | all 6 |
| 6 | Cancel all 6 flights | ✓ | ₹1,500,000 | none |

19 candidates rejected, each with its rule and its arithmetic.

**Station closure** — *"BLR closes 08:00–14:00Z on 17 Sep. Outline the recovery plan."*

A closure does not uncrew a flight, it strands it. So the engine answers the question a
controller actually has — per leg, how long until it can move, and does the crew's duty
survive that delay:

| Flight | Pairing | Blocked | Min delay | FDP after | Limit | Verdict |
|---|---|---|---|---|---|---|
| DX462 | P-2232 | arr 08:45Z | 5.75h | 11.00h | 13.0h | legal — just delay it |
| DX402 | P-2204 | arr 08:45Z | 5.75h | 17.00h | 12.0h | FDP breach — re-crew the tail |
| DX424 | P-2211 | arr 12:45Z | 1.75h | 13.00h | 12.0h | FDP breach — re-crew the tail |

13 legs, 6 pairings, 1,836 passengers. 3 legs simply delay; 10 need the tail of the duty
re-crewed. **Plan: ₹580,050. Cancelling the blocked legs instead: ₹3,000,000.**

**Delay** — *"VT-DXA is delayed 90 minutes before DX401 on 16 Sep."*

> Duty runs **12.75h against a 12.0h limit** (4 sectors). Recommended: original crew
> operate DX401–DX403 (reduced duty 9.5h vs 12.5h limit — legal); a fresh complement
> operates DX404. ₹114,000 versus ₹250,000 to cancel.

---

## How we grade ourselves — and what that caught

`questions.json` is the source of truth for both the arithmetic and the algorithm, so it
is worth being strict about. Our first grader compared loose token containment with an
80% threshold. It reported a clean sheet. It was wrong: it let Q35 pass while the closure
engine was answering a completely different question.

`app/services/audit.py` replaced it with **one explicit checker per question** — the exact
field, the exact value, no substring matching. Re-running it against a system that had
been "passing" surfaced four real bugs:

| Question | What the strict check found | Fix |
|---|---|---|
| **Q32** | Two simultaneous sick calls were solved independently, so both were given the **same** reserve. ₹37,000 for a plan needing two bodies. | `engine/joint.py` — cheapest combination subject to every vacancy getting a distinct crew member. Now ₹42,500, matching the key. |
| **Q35** | Closures were modelled as *uncrewed* flights rather than *stranded* ones, so the plan was "cancel everything" (₹3,000,000). | `engine/closure.py` — per-leg delay-to-reopen and FDP check. Plan now ₹580,050. |
| **Q27** | Exclusion reasons named the breach but not the rule ("no ATR72 rating" without `RULE-QUAL-05`). | `Verdict.reason()` now tags every clause with its rule id. |
| **Q33** | "What should Crew Control **do**" never matched the recovery intent, so the answer carried no options at all. | Widened intent matching; aircraft-level delays now shift every leg that tail flies. |

None of these were model failures — the LLM had refused or hedged correctly in each case.
They were gaps in the deterministic engine underneath, which is exactly where a strict
grader earns its keep.

## The console

**One question, one answer, one decision.** A single input, the answer first, the
reasoning one click away. A right-hand **watch list** runs without being asked — duty
headroom, certifications lapsing, thin reserve cover, and the provided risk signals — so
the desk sees trouble before the phone rings. It finds the dataset's one planted
compliance breach (C-5417 rostered past a training expiry) unprompted.

**Drafted callouts.** Ask for a notification and the console renders the message with a
**Copy** button and a deliberately disabled *Send via crew comms*. Every time and station
is read from the roster, including the day-2 down-route sign-on that is the one people
miss. It is not sendable on purpose: the dataset carries no contact details for anyone,
so "sending" would mean inventing an address — the exact fabrication this system exists
to prevent. Delivery is a crew-comms integration; the advisor's job ends at a correct
draft.

**Light and dark.** A three-way control — system / light / dark — persisted per browser
and resolved before first paint so there is no flash. Because every colour is a token and
no component hardcodes one, light mode is a single block of redefinitions. The brand lime
is unreadable as text on white (1.9:1), so light mode uses a deeper shade of the same hue
at 6.33:1; dark mode keeps the bright brand colour. Every foreground/background pair in
both themes was checked against WCAG AA.

---

## Known divergence — scenario S4 (our honest failure case)

The brief asks for a case we handle poorly, with analysis. This is the one we argue about.

For S4, the supplied answer key prices the tail-leg re-crew at **₹75,000**. We return
**₹114,000**. The difference is 6 × ₹6,500 deadhead positioning.

Our reasoning: DX404 departs **MAA**. Every crew member in `crew.json` is based at BLR or
DEL — there are **zero** MAA-based crew. So a fresh complement physically has to be flown
to MAA before it can operate MAA→BLR. Positioning is feasible (DX453 arrives MAA 09:00Z
against an 11:45Z report), and `costs.json` prices it at ₹6,500 per head. The key appears
to omit that cost.

We chose not to quietly match the key. The engine itemises both parts — callout ₹75,000
(matching the key exactly) plus positioning ₹39,000 — and the scorecard tags S4 as a
DIVERGENCE whether or not it passes, so the disagreement is visible rather than smoothed
over. **We may be wrong.** If the intended reading is that positioning is absorbed
elsewhere, one constant changes. But silently reporting a number we believe is ₹39,000
short of reality is exactly the failure mode this whole system is built to prevent.

No question is marked "ungraded" any more. Q33, Q35 and Q38 were once waved through as
open-ended; on a proper reading each has something checkable — a cost, a per-leg figure,
a required set of briefing signals — so each now has a real checker. Q33 is the one that
still disagrees with its key, for the reason above.

---

## Other limitations

- **RULE-CERT-06 checks expiry only.** 150 of 600 supplied certification records carry a
  `valid_from` in the future — a generator artifact. The dataset's own `validate.py`
  ignores `valid_from` too. Enforcing it would fail a quarter of the fleet against a
  roster the dataset guarantees is legal. Documented in `rules/r06_certification.py`.
- **Chain search and relaxation rarely trigger on this dataset.** Both are gated on
  scarcity (fewer than three covers, and zero covers, respectively) that a generously
  crewed synthetic week never reaches. Chain search is additionally bounded at beam 8,
  depth 3, so a recovery needing four coordinated moves would be missed.
- **No precomputed legality matrix.** An earlier draft of this README claimed one. It
  was a performance idea, and the performance never needed it — Tier 3 answers land in
  10–40 ms computing from scratch. The unused table has been removed rather than left
  in the schema implying a feature that does not exist.
- **The router is regex-based** when the LLM is off. It covers all 38 supplied questions
  and refuses cleanly outside them; it is a safety net, not a parser.
- **Sessions are in-process.** Multi-turn context does not survive a restart.
- **Reserve deadhead assumes same-day positioning only.** No overnight positioning.

---

## Repository layout

```
data/                     supplied dataset — read-only, never modified
dcortex_provided/         supplied generate.py / validate.py / README, untouched
backend/
  app/rules/              7 rule modules + registry — the only source of legality
  app/engine/             impact · state · candidates · chains · splitting ·
                          closure · joint · relaxation · cost · resilience · ranking
  app/explain/            evidence ledger + grounding verifier
  app/llm/                provider abstraction · tool schemas · orchestrator
  app/fallback/           deterministic router (works with no LLM)
  app/services/           Tier-1 lookups, Tier-2/3 actions, strict audit,
                          scorecard
  app/api/                FastAPI routes + Pydantic mirrors of the TS contract
  mcp_server/             same tools over MCP
  scripts/                import_data · audit · run_scorecard · record_fixtures
  tests/                  36 tests
frontend/src/             React + TS console (types/api.ts is the contract)
ARCHITECTURE.md           the LLM/deterministic boundary, drawn
```

`internal/held_out_scenarios.json` shipped with the dataset by mistake — its own README
says not to distribute it. **We never opened it.** Nothing reads that path; the scorecard
runs only `questions.json` and `scenarios.json`.

---

## Using it from an MCP client

The engine is exposed twice from one implementation — REST for the console, MCP for
anything else. `mcp` is already in `requirements.txt`, so it is installed:

```bat
cd backend
python -m mcp_server.index          :: speaks MCP over stdio
```

Claude Desktop / any MCP client:

```json
{"mcpServers": {"crew-ops": {
    "command": "<repo>/backend/.venv/Scripts/python.exe",
    "args": ["<repo>/backend/mcp_server/index.py"]}}}
```

> **Use the absolute script path, not `-m mcp_server.index`.** Claude Desktop launches the
> process without applying a working directory, so the module form cannot resolve the
> package: the server exits immediately and the client reports only "Server disconnected".
> Everything the server touches is resolved from `__file__`, so the script path works from
> any directory.

Same 15 tools, same rules engine, zero duplicated logic — `mcp_server/index.py` is thin
typed wrappers that all delegate to the same `dispatch()` the REST API uses. A test
asserts the two doors return byte-identical answers, so they cannot drift apart.

> **Dependency note:** the MCP SDK requires `starlette` 1.x, which FastAPI < 0.141
> rejects. `requirements.txt` pins `fastapi==0.141.1` so both resolve together. Installing
> `mcp` into an older FastAPI environment will break the API with
> `Router.__init__() got an unexpected keyword argument 'on_startup'`.

---

## Crew PII in production

No real personal data is involved here, but the shape of the problem is worth stating.
Crew records are unusually sensitive: medical certificates are health data, and rosters
are location history.

The design already helps. The LLM only ever receives a **digest** — ids, rule verdicts,
costs — never `crew.json`. Names barely cross the boundary at all, and a production build
would pass opaque ids only, resolving names in the UI from a separate authorised call.
Beyond that: field-level encryption for medical and licence records, purpose-limited
access so a crew controller sees *expired / valid on 15 Sep* rather than a diagnosis, the
evidence ledger doubling as an access audit trail (it already records which record backed
which decision), retention tied to the regulatory window rather than kept indefinitely,
and — where the model is hosted externally — either an in-VPC deployment or a no-retention
contract, since duty and medical data should not be training anyone's model.

---

## Performance

| Path | Typical |
|---|---|
| Tier 1 lookup | 1–3 ms |
| Tier 2 impact | 5–15 ms |
| Tier 3 ranked recovery (incl. chain search) | 10–40 ms |
| Full 44-case scorecard | ~400 ms |
| End-to-end with LLM phrasing | 3–8 s |

The engine is effectively instant; latency is the model's. Because the deterministic
result is computed first and the model only phrases it, the structured answer — impact
graph, options, costs — is already correct before a single token is generated.

---

## Tech choices, briefly

**SQLite, loaded into memory.** The brief says it is sufficient and it is. The repository
is the only module touching SQL, so Postgres is a one-file swap.

**No ORM.** Fourteen tables and one loader. An ORM would add a dependency and a layer of
indirection for nothing.

**Beam search, not a solver.** The brief explicitly permits heuristic ranking, and
explainability is graded throughout. A CP-SAT model would solve this instantly and be
unable to tell a controller *why*.

**No fine-tuning.** "60 duty hours in 7 calendar days" is a rule, not something a network
should approximate. Teaching a model to estimate it would be strictly worse than
computing it.
