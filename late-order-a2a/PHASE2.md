# Phase 2: Cross Vendor A2A, Claude Logistics with a Reusable Skill

Phase 1 built a Customer Experience (CX) agent that delegates late order root
cause analysis to a separately owned Logistics agent over the A2A protocol, both
on Google ADK and Gemini. Phase 2 replaces only the Logistics runtime with the
Anthropic Claude API plus a reusable Delay Root Cause Skill, and proves the CX
agent reaches it over the same A2A contract with no source change.

The demonstration: **Google ADK CX Agent to A2A to Claude Logistics Agent to a
reusable deterministic diagnosis to BigQuery**. The CX agent never needs to know
whether Logistics runs on Gemini or Claude.

## Architecture view

```
 Customer service rep
          │
          ▼
 ┌──────────────────────────────┐   A2A JSON-RPC message/send over HTTP
 │ CX agent (Gemini, ADK)       │   LOGISTICS_URL selects the backend
 │  get_order_status   (code)   │ ───────────────┬───────────────────────────┐
 │  diagnose_delay     (A2A)    │                │                           │
 │  propose_compensation (code) │                ▼                           ▼
 │  issue_store_credit (code,   │   ┌───────────────────────┐   ┌───────────────────────────┐
 │    human approval at >= 20%) │   │ Logistics (Gemini,ADK)│   │ Logistics (Claude)        │
 └──────┬──────────────┬────────┘   │ to_a2a server, 8001   │   │ manual Messages loop,8002 │
        │ read         │ write      │  delay_root_cause     │   │  Skill as system prompt   │
        ▼              ▼            └───────────┬───────────┘   │  narrative guard          │
   cx_data.orders   cx_data.credits            │               └───────────┬───────────────┘
                                               │                           │
                                               ▼                           ▼
                                        logistics_core.diagnosis (one shared module)
                                               │
                                               ▼
                                        logistics_data.* in BigQuery
```

Both Logistics runtimes call the same `logistics_core.diagnosis`, so the SQL, the
90 day distribution center baseline, and the cause rules are byte identical. The
A2A interface is the stable contract; the runtime behind `LOGISTICS_URL` is
pluggable. This is the adapter pattern applied across two model vendors.

## What changed from Phase 1

| Area | Change | Why |
|---|---|---|
| Shared diagnosis | Extracted the Phase 1 `delay_root_cause` into `logistics_core` (diagnosis.py, bq.py) | One source of truth for both runtimes; no duplicated SQL or rules |
| Gemini Logistics | Now a thin wrapper importing the shared module | Same function name, signature, docstring, so the Gemini tool declaration is unchanged |
| Claude Logistics | New `logistics_claude` package: manual Anthropic Messages tool loop, A2A adapter, Skill loader | The Claude SDK ships no A2A server and no filesystem Skill execution, so both are implemented explicitly |
| Skill | New `skills/delay-root-cause` with SKILL.md and reference/cause-codes.md | Reusable by any Claude agent, not coupled to CX |
| Model migration | `gemini-2.5-flash` retired by Google, moved CX and Gemini Logistics to `gemini-3.8-flash` | Forced, not elective; see Findings |
| CX agent | Model id only; compensation logic untouched | Phase 2 scope forbids CX changes |

## How the Claude Logistics agent works

1. The A2A adapter (`a2a_server.py`) accepts the same JSON-RPC `message/send`
   request CX sends, extracts the order id from the text, and returns an A2A Task
   whose artifact text carries the diagnosis. CX reads
   `result.artifacts[].parts[].text` and `result.status.state`, so the envelope
   is a drop in replacement for the Gemini `to_a2a` server.
2. The runtime (`agent.py`) runs a manual Messages loop on `claude-haiku-5-5`.
   The model calls one tool, `delay_root_cause`, and narrates the result.
3. The Skill (`skill_loader.py`) loads SKILL.md as plain system prompt text. It
   is instruction content, not native Claude Agent Skills and not server side
   execution, and the loader documents that honestly.
4. Governance holds the model to the deterministic result:
   - the tool always runs with the request order id, so the model cannot
     redirect the diagnosis to another order,
   - the deterministic diagnosis runs even if the model skips the tool,
   - a strict narrative guard drops any model text that omits an authoritative
     cause code or invents one, substituting deterministic text built straight
     from the tool output,
   - errors are returned as sanitized codes (INVALID_ORDER_ID, DATA_UNAVAILABLE),
     never raw BigQuery detail.

## Interoperability results

### Direct A2A equivalence probe

`tests/compare_logistics.py` sends the identical A2A request CX sends to both
servers and compares the cause codes extracted from each reply.

| Order | Gemini codes | Claude codes | Match | Gemini ms | Claude ms |
|---|---|---|---|---|---|
| 109778 split shipment | WAREHOUSE_DELAY, TRANSIT_DELAY | WAREHOUSE_DELAY, TRANSIT_DELAY | yes | 15841 | 10997 |
| 1902 | WAREHOUSE_DELAY | WAREHOUSE_DELAY | yes | 12142 | 7600 |
| 999999999 unknown | (none) | (none) | yes | 10739 | 6969 |

Cause code equivalence holds on every order, including the unknown order error
path. Claude tokens for the three orders: 10903 in, 1209 out, about 0.0017 USD at
the Haiku 5.5 rate.

Latency note, stated honestly: these are single runs, not a benchmark, and both
times are dominated by the real BigQuery query inside the shared tool, which is
identical for both backends. The lower Claude times reflect Gemini 3.8 reasoning
overhead, not the logistics logic.

### CX runs unchanged against either backend

The Phase 1 evaluation set, switching only `LOGISTICS_URL`, truncating
`credits_eval` before each run.

| Case | Gemini tool trajectory | Claude tool trajectory | Gemini response match | Claude response match |
|---|---|---|---|---|
| case1_on_time | 1.0 | 1.0 | 0.263 | 0.250 |
| case2_split_shipment | 1.0 | 1.0 | 0.326 | 0.353 |
| case3_unknown_order | 1.0 | 1.0 | 0.400 | 0.383 |
| case4_boundary | 0.0 | 0.0 | 0.047 | 0.045 |

Tool trajectory is identical case for case, which is the interoperability proof:
CX calls the same tools with the same cause codes regardless of vendor. The
response match scores fail on both backends alike and reflect CX side 3.8 wording
drift against goldens recorded on the retired 2.5 model, not a backend
difference.

## Model and cost

Verified on docs.claude.com before coding.

| Model | API id | Input per MTok | Output per MTok | Role |
|---|---|---|---|---|
| Haiku 5.5 | `claude-haiku-5-5` | 0.10 | 0.50 | Default Logistics runtime |
| Sonnet 5.5 | `claude-sonnet-5-5` | 2.00 | 10.00 | Configurable comparison via LOGISTICS_MODEL |

Haiku 5.5 moves to 0.50 / 2.50 above 100K prompt tokens; these prompts stay far
below that. Claude 4.7 and later tokenize about 30 percent higher than older
generations, which matters when comparing raw token counts against Gemini.

### Measured Haiku versus Sonnet on the same three orders

Same probe, `LOGISTICS_MODEL` switched to `claude-sonnet-5-5`. Cause codes were
identical on both models and on Gemini, so the comparison is latency and cost
only.

| Runtime | 109778 ms | 1902 ms | unknown ms | Tokens in / out | Cost, 3 orders |
|---|---|---|---|---|---|
| Haiku 5.5 | 10997 | 7600 | 6969 | 10903 / 1209 | 0.0017 |
| Sonnet 5.5 | 18387 | 9762 | 9492 | 10903 / 1248 | 0.0343 |

Sonnet is about 1.7 times slower and about 20 times the cost for the same cause
codes. For a governed relay where the deterministic tool owns the answer and the
guard constrains narration, the extra model capability buys nothing. Haiku 5.5 is
the right default; Sonnet is kept only as a configurable comparison. Probe times
varied run to run (for example 15.8 s and 28.4 s on order 109778 across two runs),
so these are directional, not a controlled benchmark, and BigQuery query time
dominates every call.

## Security and business controls

- BigQuery isolation intact. The Claude runtime calls the same `logistics_core`,
  which impersonates the logistics service account. It has no path to `cx_data`
  or the credits table.
- No compensation authority on the Logistics side, Gemini or Claude.
- The Agent Card is curated: no internal instructions, no SQL, no credentials.
- Deterministic results cannot be overridden by model text, enforced by the guard.
- Human approval at or above 20 percent remains a CX side control, unchanged.

## Findings

1. **A forced model migration can break a prompt enforced guardrail.** Google
   retired `gemini-2.5-flash`. Under `gemini-3.8-flash` the CX boundary case
   (case4: refuse a request for raw warehouse records) regressed: the agent ran
   the full tool chain and emitted raw records in prose. The refusal was prompt
   enforced on 2.5 and 3.8 does not comply. It fails identically on both logistics
   backends, which localizes it to CX and the model, not logistics. Kept frozen
   per Phase 2 scope and documented here rather than fixed.
2. **Prose across an agent boundary stays brittle.** Both runtimes reply in prose
   that contains the codes, and CX extracts codes from prose. A structured
   DataPart remains the stronger future contract.
3. **A deterministic boundary survives a model swap; a prompt does not.** The
   logistics narrative guard, which is code, held across the vendor change. The CX
   refusal, which is a prompt, did not. The durable lesson for governance is to
   enforce boundaries in code at the tool interface, not in model instructions.

## Open gaps and remaining work

- Restore the CX boundary refusal with a code level guard at the tool interface,
  outside Phase 2 scope.
- Return cause codes as a structured A2A DataPart, not only text.
- Re record the evaluation goldens against `gemini-3.8-flash` so response match
  reflects the current model.
- Run the Sonnet 5.5 comparison via `LOGISTICS_MODEL` and record the cost delta.
- Deploy the Claude Logistics server to Cloud Run with the same IAM invoker
  restriction used for the Gemini deployment.
- Retire the duplicate `deploy_logistics` copy after a staged Gemini build.

## Run it

Both logistics servers call BigQuery through the logistics service account, so set
ADC in each server window first.

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="$env:APPDATA\gcloud\application_default_credentials.json"
$env:GOOGLE_CLOUD_PROJECT="<project>"
```

Claude Logistics needs `logistics_claude/.env` with `ANTHROPIC_API_KEY` and
`LOGISTICS_MODEL=claude-haiku-5-5`.

```powershell
# window 1: Gemini Logistics
uvicorn logistics_agent.agent:a2a_app --port 8001
# window 2: Claude Logistics
uvicorn logistics_claude.a2a_server:a2a_app --port 8002
# window 3: direct equivalence probe
python tests\compare_logistics.py
```

Offline tests, no key or network:

```powershell
python -m pytest tests\test_claude_guard.py tests\test_claude_a2a_contract.py -q
```

CX against either backend, switch only `LOGISTICS_URL` in `cx_agent\.env`:

```powershell
bq query --use_legacy_sql=false "TRUNCATE TABLE ``<project>.cx_data.credits_eval``"
adk eval cx_agent cx_agent\late_order_core.evalset.json --print_detailed_results
```

## Files

Created: `logistics_core/` (diagnosis.py, bq.py), `logistics_claude/` (agent.py,
a2a_server.py, skill_loader.py, .env.example), `skills/delay-root-cause/`
(SKILL.md, reference/cause-codes.md), `tests/test_claude_guard.py`,
`tests/test_claude_a2a_contract.py`, `tests/compare_logistics.py`,
`scripts/stage_build.py`.

Modified: `logistics_agent/agent.py` (thin wrapper, model id),
`cx_agent/agent.py` (model id only; compensation logic untouched).
