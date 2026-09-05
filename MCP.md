# Connecting the advisor over MCP

The engine is reachable two ways from one implementation: **HTTP** for our own console, and
**MCP** for anything else. This page is the runbook for the second — what it is, why you
would want it, how to connect, and what breaks.

---

## What MCP is, in one paragraph

The Model Context Protocol is a standard way to hand a set of tools to an AI client. It is
a *plug shape*, not a reasoning layer — the way USB-C is a standard for chargers without
being a charger. A client (Claude Desktop, an IDE, another agent) launches the server,
asks what tools exist, and calls them. All the thinking about crew legality still happens
in our Python; MCP is only how somebody else's assistant reaches it.

---

## Why you would want this

**Because a crew desk does not want another tab.** Controllers already work across
several screens — that is the pain the brief opens with. Our console is a good screen, but
it is still one more. MCP lets the advisor appear *inside* whatever the controller already
has open.

**Because it makes this a system of action, not a demo.** The same engine that answers our
web UI can answer an ops assistant, a scheduling tool, or an agent doing something we never
anticipated. We did not have to predict the client to serve it.

**Because it is the shape the market is already paying for.** Airlines are funding
MCP-exposed crew tooling today — qualification and pay servers exist. What nobody has put
behind that interface is the *recovery reasoning*: consequence traversal, ranked legal
options, cost. That is the layer this project adds, and exposing it over MCP means it drops
into an existing stack rather than asking for a new one.

**Because it costs almost nothing.** `mcp_server/index.py` contains no logic. Every
function is a two-line typed wrapper that forwards to the same `dispatch()` the REST API
calls:

```python
def recommend_recovery(pairing_id: str, role: str, crew_out: str | None = None) -> str:
    return _run("recommend_recovery", pairing_id=pairing_id, role=role, crew_out=crew_out)
```

One rules engine, one cost model, one source of truth — two doors. A test asserts both
doors return identical answers to the same question, so they cannot drift apart.

---

## Connecting it

### 1. Install

`mcp` is already pinned in `backend/requirements.txt`, so a normal setup has it:

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts\import_data.py
```

### 2. Configure your client

Claude Desktop on Windows reads `%APPDATA%\Claude\claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`). In the app it
is **Settings → Developer → Edit Config**.

```json
{
  "mcpServers": {
    "crew-ops": {
      "command": "C:\\path\\to\\repo\\backend\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\repo\\backend\\mcp_server\\index.py"]
    }
  }
}
```

Use the venv's `python.exe`, not a bare `python` — the client does not inherit your shell,
so it will not find an activated environment.

### 3. Restart the client properly

The config is read once at launch. On Windows, closing the window does **not** quit Claude
Desktop: right-click the tray icon → **Quit**, then reopen.

### 4. Confirm and ask

The tools icon near the chat input should list **crew-ops** with 15 tools. Then:

> Using crew-ops, Captain C-1042 just called in sick for tomorrow. What should I do?

Expect *Assign Captain C-3310 (reserve callout), ₹18,500, covers all 6 legs*, with the
rejected candidates and their rules. Naming the server in the first message of a thread
matters — without it a client will sometimes answer from general knowledge instead of
reaching for the tools, which looks like a failure and is not one.

**The API server does not need to be running.** The client launches its own copy of the
Python process and talks over stdin/stdout, so MCP works even with `uvicorn` stopped.

---

## The 15 tools

| Tool | Tier | Returns |
|---|---|---|
| `get_crew_profile` | 1 | rank, base, ratings, reachability, reserve window, clocks, risk |
| `search_crew` | 1 | crew filtered by rank / base / rating |
| `get_reserves` | 1 | reserves on call, optionally narrowed to a callout time |
| `get_duty_clock` | 1 | 7-day duty and 28-day block hours, with headroom per rule |
| `find_crew_near_duty_limit` | 1 | crew at or above a duty threshold |
| `search_flights` | 1 | schedule by date / station / flight number / tail |
| `get_expiring_certifications` | 1 | certificates lapsing inside a window |
| `get_pairing` | 1 | a pairing's crew, roles, days and legs |
| `get_earliest_report` | 1 | earliest legal next report after a release (RULE-REST-04) |
| `analyse_disruption` | 2/3 | what a sick call / closure / delay breaks; closures come back as a full costed plan |
| `check_assignment_legality` | 2 | rule-by-rule verdict with actuals, limits, margins, before/after |
| `get_cancellation_impact` | 2 | passengers and direct cost of cancelling legs |
| `recommend_recovery` | 3 | ranked legal options with cost, coverage, resilience, and why each rejection was rejected |
| `get_alerts` | 2 | proactive signals: duty headroom, expiry, reserve depth, risk |
| `draft_crew_notification` | 3 | the callout message, per-day, from the roster |

Every result carries its **evidence** — the facts used and where each came from — so an MCP
client can audit an answer, not just read it.

---

## Transport: stdio, and why

`mcp_server/index.py` runs `server.run(transport="stdio")`. The client spawns the process
and speaks newline-delimited JSON-RPC over its pipes:

```
Claude Desktop --spawns--> python mcp_server/index.py
               --stdin---> {"jsonrpc":"2.0","method":"tools/call", ...}
               <--stdout-- {"jsonrpc":"2.0","result":{...}}
               (process dies when the client quits)
```

Verified rather than assumed: connecting opens **no listening socket**, and the server is a
child of the client.

That has three practical consequences:

- **Nothing is exposed on the network.** No port, no firewall rule, no auth surface — which
  matters more than it sounds on venue wifi.
- **It is per-client and disposable.** Each client gets its own process, killed on exit.
- **`stdout` is the protocol.** Anything printed there corrupts the stream, which is why
  every diagnostic in the server writes to `stderr`.

The SDK also offers `sse` and `streamable-http`, so making the server remote is one
argument:

```python
server.run(transport="streamable-http")   # client then connects by URL
```

We stayed on stdio because everything here is local and stdio needs no configuration.
Streamable HTTP earns its place when one deployed instance serves several people — the same
tools, a different transport, and then authentication becomes a real requirement rather
than an out-of-scope one.

---

## Troubleshooting

**"Server disconnected" immediately.** Almost always the config. Use the **absolute script
path**, not `-m mcp_server.index`:

```json
"args": ["C:\\path\\to\\backend\\mcp_server\\index.py"]     // correct
"args": ["-m", "mcp_server.index"], "cwd": "..."            // fails
```

Claude Desktop does not apply the `cwd` key, so the module form cannot resolve the package,
Python exits with `ModuleNotFoundError`, and the client can only report the symptom. The
script form works from any directory because everything the server touches resolves from
`__file__`. *(We shipped the broken form first and had to debug exactly this.)*

**"No operational database at ..."** — run `python scripts/import_data.py`. The server
checks for the database at startup and says so on `stderr` rather than dying silently.

**The API breaks after installing `mcp`.** The MCP SDK needs `starlette` 1.x, which FastAPI
below 0.141 rejects with `Router.__init__() got an unexpected keyword argument
'on_startup'`. `requirements.txt` pins `fastapi==0.141.1` so both resolve together —
install from it rather than one package at a time.

**Nothing appears in the tools list.** Config is read at launch; quit from the tray icon
rather than closing the window. Then check **Settings → Developer** for the server's stderr.

**Sanity-check the server alone:**

```bat
cd backend
.venv\Scripts\python.exe mcp_server\index.py
```

It should sit silently waiting for input — that is correct. A traceback means something
moved; the config hardcodes absolute paths, so renaming or moving the repo breaks it.

---

## What this is not

- **Not a second implementation.** No rule, cost or traversal logic lives in
  `mcp_server/`. If the two doors ever disagree, that is a bug, and a test watches for it.
- **Not authenticated.** Out of scope per the brief, and unnecessary while the transport is
  a local pipe. A remote transport would change that immediately.
- **Not a way to send anything.** `draft_crew_notification` drafts; the dataset carries no
  contact details and delivery is an airline-system integration.
