# Design notes

`ARCHITECTURE.md` describes *what the system is*. This describes *why it is that way* —
the decisions, the trade-offs taken knowingly, and the places we changed our minds.

---

## 1. The domain model, and the one relationship that matters

The obvious model is `flight → crew`. It is wrong, and it produces the wrong answer to the
very first Tier-2 question.

Crew are not assigned to flights. They are assigned to **pairings** — a multi-day sequence
of duties that starts and ends at a base, overnighting down-route in between. So:

```
Crew ──rostered on──► Pairing ──has──► Day ──contains──► Leg ──flown by──► Aircraft
                         │                │                                    │
                         │                └── report / release bracket the duty │
                         │                                                      │
                         └──────────── overnights at the last leg's arrival ────┘
```

A captain calling in sick does not uncrew *a flight*. It breaks a pairing, and the pairing
takes three legs with it today and three more tomorrow — and the day-2 legs start at DEL
because that is where the aircraft and crew slept. Answer Q17 with a flight-level model and
you report three uncovered legs where the key expects six, split into *immediate* and
*also at risk*.

Everything downstream depends on getting this right: impact traversal, chain search,
closure planning, resilience.

**Consequence for the schema.** Sixteen normalized tables, not one wide one. The dataset
arrives fragmented across nine files precisely because the brief's thesis is that a single
answer spans all of them. Flattening it would have thrown away the structure the problem is
about.

## 2. Three time semantics that are easy to conflate, and expensive to get wrong

| Concept | What moves | What it models |
|---|---|---|
| `delay_hours` | report **and** release, together | deadhead positioning — crew reports late, finishes late, duty length unchanged |
| `extend_hours` | release only | an operational delay — crew already reported, so the duty *grows* |
| closure `min_delay` | the whole leg, then the duty stretches | the field is shut; nothing moves until it reopens |

We shipped the first version with a single `delay_hours` doing both jobs. The result: a
90-minute technical delay reported **no FDP breach at all**, because shifting report and
release together leaves duty length identical. The rule engine was correct; it was being
asked the wrong question.

The fix is two fields and a comment explaining why they are not one. `test_delay_extends_
duty_and_breaches_fdp` exists so nobody merges them again.

## 3. Signed margins, and what they unlock

Every rule returns more than a verdict:

```python
RuleResult(rule_id, status, actual, limit, margin, detail)
```

`margin` is signed headroom in the rule's own unit — negative means the size of the breach.
That one field is why three separate features are possible:

- **Explanations quantify.** "Exceeds by 1h20m", not "exceeds".
- **Near-miss analysis inverts it.** Given `-1.33h` on RULE-DUTY-02, the relaxation engine
  can search for a change worth ≥1.33h — dropping the last leg of a day releases 3.25h, so
  it proposes exactly that.
- **A duty is divisible, and the tail is a duty in its own right.** Whenever only part
  of a duty needs new crew -- a delay, a station closure, or a crew member going sick
  after the second sector -- the remaining legs are re-timed into their own duty
  period before any rule sees them. That matters: two sectors carry a 13h FDP limit
  where four carry 12h, and a later report time changes which reserves are in their
  on-call window. On P-2217 the full day is callable only by C-3305 and the tail only
  by C-3310 -- filtering the leg list instead would have reported both wrong.
- **Duty splitting binary-searches it.** The longest legal prefix of a delayed duty is
  found by walking sectors off the end until the margin turns positive.

A boolean `legal` would have made all three impossible.

## 4. Why heuristic search and not a solver

The brief permits a solver and we chose against one, twice, for the same reason.

**Recovery chains** use beam search (width 8, depth 3) over swap cascades. A CP-SAT model
would find the optimum on this data instantly. It would also produce an answer whose
justification is "the optimiser said so", and explainability is graded throughout. A beam
search yields a readable move list: *move C-2244 off P-2318 onto P-2291, backfill P-2318
with reserve C-3307* — each step individually rule-checked and quotable.

**Joint assignment** is exhaustive over a cost-sorted shortlist rather than a Hungarian
algorithm. With a handful of vacancies and six candidates each the search space is trivial,
the result is provably optimal, and the code is fifteen readable lines. Past roughly six
simultaneous vacancies this would need replacing — noted in the scaling section rather than
pre-solved.

The general principle: **prefer the algorithm a controller could follow on paper**, until
scale forces otherwise.

## 5. Why the LLM is fenced the way it is

Three fences, each answering a specific failure we either hit or expected.

**The digest** (`_digest()`). The model receives a summary, the leading options and the rule
verdicts — never the full payload. Partly a token budget (the free tier caps at 8,000/min),
mostly a principle: the less raw data the model sees, the less it can reinterpret. The UI
gets the complete result on a separate path.

**Tool narrowing** (`relevant_tools()`). The deterministic router reads the question and
offers 4–7 tools instead of 15. This started as a token optimisation and turned out to
improve accuracy — with all 15 available the model would explore one candidate at a time
instead of calling the tool that does the whole job.

**The verifier** (`explain/verifier.py`). Every crew id, flight number, pairing, rule id and
money figure in the finished prose is checked against the evidence ledger. This is the fence
that catches what prompting cannot: the model once wrote `C‑3310` with a Unicode
non-breaking hyphen, which sailed past a `C-\d{4}` regex. Ids are now dash-normalised before
checking, with a test.

There is also a fourth, quieter one: **if the model answers without calling any tool, that
answer is discarded** and the deterministic router responds instead. An answer produced
without consulting the engine is ungrounded by construction, regardless of whether it
happens to be right.

## 6. The fallback is a design feature, not a safety net

`app/fallback/structured_query.py` answers the same 16 tools with regex intent matching and
entity extraction. It exists for three reasons, in order of importance:

1. **The desk cannot go dark.** A crew controller at 05:00 whose advisor is down because an
   API key expired has been given a liability, not a tool.
2. **It is the reference implementation of intent.** When the LLM path and the router
   disagree about what a question means, one of them is wrong, and the router is inspectable.
3. **It is what the strict audit runs against.** All 38 questions are graded through the
   deterministic path, so the score measures the *engine*, not the model's mood on the day.

It also carries conversation context: when the LLM fails mid-thread, recent turns are handed
to the router so a pronoun-only follow-up still resolves.

## 7. Decisions we changed

Recorded because the reasoning matters more than the outcome.

**RULE-CERT-06 checks expiry only.** 150 of 600 supplied certification records carry a
`valid_from` in the future — a generator artifact. Enforcing it failed roughly a quarter of
the fleet against a roster the dataset guarantees is legal. The dataset's own `validate.py`
ignores `valid_from` too, so we matched the data's actual semantics and documented it in the
rule module rather than "fixing" the data.

**Closures were modelled as crew shortages.** Wrong, and expensively so: the recovery plan
was to cancel thirteen legs (₹3,000,000) when three could simply be delayed and ten needed
only a fresh crew for the tail of the duty (₹580,050). A closure strands a flight; it does
not empty a seat. `engine/closure.py` now computes, per leg, the minimum delay to reopen and
whether the crew's FDP survives it.

**Simultaneous vacancies were solved independently.** Each picked the cheapest legal reserve
— the same reserve. The plan looked optimal and could not be flown. `engine/joint.py` solves
them together with a distinctness constraint.

**The grader was too kind.** Loose token containment at an 80% threshold reported a clean
sheet while concealing all of the above. Replacing it with one explicit checker per question
surfaced four defects immediately. A weak test is worse than no test, because it converts
"unknown" into "verified".

**The legality matrix was never built.** Planned as a performance optimisation, documented
as if it existed, and then found to be an empty table nothing referenced. Rather than build
it to match the documentation, we removed the table and corrected the documentation —
Tier-3 answers land in 10–40 ms computing from scratch, so it would have been an index
solving nothing.

## 7b. Nothing operational is written down twice

Four facts the engine needs are stated by the dataset, so `domain/conventions.py` derives
them at load rather than repeating them in code:

| Fact | Derived from |
|---|---|
| The snapshot ("now") | `duty_clocks.as_of_utc` — identical on all 150 records |
| The operating week | min/max `flights.date` |
| Crew complement per aircraft type | the shapes actually rostered (A320 1/1/1/3, ATR72 1/1/1/1) |
| Report / release brackets | the observed gap to first departure and last arrival (60 / 30 min) |

Each derivation asserts the dataset agrees with itself and raises if not — two different
complements for one aircraft type is something a controller should be told about, not
quietly averaged away.

Rule limits already came from the `rules` table and costs from `costs.json`. What remains
hardcoded is only what genuinely is not in the data: search bounds (`BEAM_WIDTH`,
`SHORTLIST`), alert thresholds (`DUTY_WARN_RATIO`), timeouts, and float epsilons. Those
are engineering choices, not facts about the airline.

The single exception is `REOPEN_BUFFER_MINUTES` in the closure engine. The dataset never
states a reopening buffer, but its answer key implies one: every per-leg delay equals
(reopen + 30 min) minus the leg's scheduled time at the closed station, across all 13
legs. We inferred the rule that produces the answers rather than hardcoding the answers,
and a test pins all 13.

A test also asserts the engine never reads the wall clock. Exactly one file may —
`scorecard.py`, stamping when a run happened. Mixing real time with the frozen snapshot
would produce answers that look plausible and are silently wrong.

## 7c. The database is a cache, not a source of truth

The SQLite file is generated from the committed JSON, so the app imports it at startup
when it is missing rather than refusing to start. Two consequences worth having:

- **Ephemeral hosting works.** A redeploy keeps the code and the dataset but loses the
  generated file. Refusing to boot in that situation would be treating a cache like state.
- **One less setup step to miss.** A first-time reader who skips `import_data.py` gets a
  working app and a log line explaining what happened, rather than a stack trace.

The guard after the rebuild is deliberate: if the import runs and the file still is not
there, that is a real failure and it raises. Silently continuing to `get_repository()`
would turn a missing dataset into a confusing error much further downstream.

Contributed by an outside PR, which is a fair signal that the deployment story was the
weakest part of the setup.

## 8. What we deliberately did not build

- **A prediction model.** `risk_signals.json` is a provided input and the brief says treat
  it as a forecast. The system decides what to do about it; it does not produce it.
- **Sending notifications.** The dataset has no contact details for anyone, so "sending"
  would mean inventing an address — the exact class of fabrication the verifier exists to
  prevent. The advisor drafts; delivery is an airline-system integration.
- **Authentication, deployment, CI.** Explicitly out of scope in the brief.
- **An ORM.** Sixteen tables and one loader. An ORM adds a dependency and an indirection
  layer for nothing.
- **Fine-tuning.** "60 duty hours in 7 calendar days" is a rule, not something a network
  should approximate. Teaching a model to estimate it would be strictly worse than
  computing it.

## 9. Extension points

Where a reviewer would add things, and what it costs:

| Change | Touch | Cost |
|---|---|---|
| New legality rule | one module in `app/rules/` + registry entry | ~30 lines |
| Change a limit (60h → 55h) | `rules.json` only | data change, no code |
| New LLM provider | one class behind `llm/provider.py` | ~40 lines |
| Postgres instead of SQLite | `db/repository.py` only | one file |
| New disruption type | an event on `OperationalState` + a recovery path | ~80 lines |
| Remote MCP | `transport="streamable-http"` | one line |

Every rule that carries a numeric limit — FDP-01, DUTY-02, FLT-03, REST-04 — reads it from
the `rules` table rather than hardcoding it, so a regulator changing a limit is a data edit.
The other three (QUAL-05, CERT-06, BASE-07) are structural and have no parameters to read.
Rule *logic* is one file per rule, so adding one cannot disturb the others.

## 10. Known weaknesses

- **Chain search and relaxation rarely trigger** on this dataset — both are gated on
  scarcity a generously crewed synthetic week never reaches (the thinnest vacancy still has
  five legal covers). Correct and tested; not load-bearing here.
- **The router is regex-based.** It covers all 38 supplied questions and refuses cleanly
  outside them, but it is a safety net, not a parser.
- **Scenario grading is still value-containment**, unlike question grading. Fair there
  because those keys enumerate every legal option rather than one expected shape, but it is
  the weaker of the two harnesses.
- **One open disagreement with the answer key** (S4/Q33): we charge ₹114,000 where the key
  says ₹75,000, because DX404 departs MAA, no crew are MAA-based, and a fresh complement has
  to be positioned there. Reported as a divergence rather than quietly matched. We may be
  wrong; the argument is in the README so a reviewer can judge it.
