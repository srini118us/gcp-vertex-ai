# Late Order Resolution: Networked A2A Between Two Team Owned Agents

A Customer Experience (CX) agent resolves late order inquiries by delegating root cause analysis to a separately owned Supply Chain Logistics agent over the A2A protocol, across a real network and IAM boundary, with deterministic business rules, a human approval gate for larger credits, and an evaluation set that runs against the deployed version.

Built with Google Agent Development Kit (ADK), Gemini, BigQuery, and Cloud Run. Data: a snapshot of `bigquery-public-data.thelook_ecommerce` (public, simulated ecommerce data).

## Why A2A here (and not a tool call)

The two agents belong to different teams with different data:

| | CX agent (Customer Experience team) | Logistics agent (Supply Chain team) |
|---|---|---|
| Reads | `cx_data` (orders, users) | `logistics_data` (order items, inventory, distribution centers) |
| Writes | `cx_data.credits` only | nothing |
| Identity | `cx-agent` service account | `logistics-agent` service account |
| Runs on | ADK web (supervisor approval UI) | Cloud Run, private, A2A server |

The CX identity is denied on logistics data (proven by `test_boundary.py`). The only way CX can learn why an order is late is to ask the Logistics agent. That data boundary and team ownership, not convenience, is the justification for A2A.

## Architecture view

```
 Customer service rep
          │
          ▼
 ┌──────────────────────────────┐        A2A (JSON-RPC message/send over HTTPS)
 │ CX agent (Gemini, ADK)       │        identity token for cx-agent
 │  get_order_status   (code)   │ ─────────────────────────────────────────────┐
 │  diagnose_delay     (A2A)    │                                               ▼
 │  propose_compensation (code) │                          ┌──────────────────────────────────┐
 │  issue_store_credit (code,   │                          │ Logistics agent (Gemini, ADK)    │
 │    human approval at >= 20%) │                          │ Cloud Run, invoker: cx-agent only│
 └──────┬──────────────┬────────┘                          │  delay_root_cause (code rules)   │
        │ read         │ write (one table)                 └───────────────┬──────────────────┘
        ▼              ▼                                                   │ read
   cx_data.orders   cx_data.credits                                         ▼
                                                                 logistics_data.*
```

Flow for a late order: CX reads the order and computes days late against a 5 day delivery promise; calls Logistics over A2A with a fixed message (`order_id=N`); Logistics classifies each item as `WAREHOUSE_DELAY`, `TRANSIT_DELAY`, `NOT_YET_SHIPPED`, or `WITHIN_NORMAL` against its distribution center's 90 day baseline; CX applies the compensation policy in code; credits of 20 percent or more pause for supervisor approval; the credit write is idempotent.

## Build journey

| Step | Change | Why |
|---|---|---|
| 1 | Two datasets, two service accounts, SQL `GRANT`s | Make the team boundary real; dataset level IAM via `bq` was gated, SQL `GRANT` worked |
| 2 | Boundary test by impersonation | Proved each identity reads only its own dataset |
| 3 | Logistics as an A2A server (`to_a2a`) | Real agent card over HTTP |
| 4 | CX with `RemoteA2aAgent` as a sub agent | Worked, but transfer is a handoff: Logistics took over and compensation never ran |
| 5 | `AgentTool` delegation | Control returned to CX |
| 6 | Policy takes all causes, most severe wins | With a split shipment, Gemini called the policy twice and silently picked one |
| 7 | Cause codes as a `Literal` enum; fail loud on unknown codes | The A2A reply was prose; CX passed "warehouse lag" and the policy silently returned no credit |
| 8 | `issue_store_credit` with ADK tool confirmation | A real write that cannot run without a human click above the threshold |
| 9 | Credit amount recomputed inside the write tool | Neither the model nor a prompt injection can choose the percentage |
| 10 | Idempotency guard, and no approval request when already issued | A second approval would have inserted a second credit |
| 11 | Direct JSON-RPC `message/send` instead of `AgentTool` | `AgentTool` lets Gemini word the A2A message; free text varies per run and breaks eval matching |
| 12 | Configurable credits table, `credits_eval` reset before runs | Evals of agents that write need isolated, resettable state |
| 13 | Logistics deployed to Cloud Run, invoker restricted to `cx-agent` | Real network and IAM boundary; anonymous calls get 403 |

## Design decisions

| Decision | Options | Choice | Trade off |
|---|---|---|---|
| Delegation style | Handoff (`sub_agents`); delegation (`AgentTool`); direct protocol call | Direct protocol call | Deterministic and testable; the ADK graph no longer shows Logistics as an agent, so cross service tracing is needed |
| A2A contract | Free text; structured codes | Codes enforced at the CX tool interface (`Literal`) | Logistics replies remain prose; a structured data part would be stronger |
| Compensation | LLM judgment; code policy | Code policy, most severe cause wins, capped at 30 percent | Policy changes need a release |
| Approval | Prompt instruction; tool confirmation | `FunctionTool(require_confirmation=callable)` | Not supported with managed Agent Runtime sessions today; production approvals would move to an asynchronous queue |
| Write safety | Trust model arguments; recompute | Recompute amount, idempotency check | Extra queries per write |
| Data access | One identity; one per agent | One per agent, least privilege, grants as SQL in the repo | More identities to manage |
| Hosting | Cloud Run; Agent Runtime | Cloud Run for Logistics | Explicit IAM and plain HTTP; Agent Runtime would add managed sessions and native governance |

## Evaluation

Four independent cases in `cx_agent/late_order_core.evalset.json`, run against `credits_eval` after a truncate:

| Case | Behavior under test |
|---|---|
| case1_on_time (order 1902) | No A2A call, no credit |
| case2_split_shipment (order 109778) | A2A call, both causes, 15 percent issued automatically |
| case3_unknown_order | Clean stop, nothing invented |
| case4_boundary | Refuses raw warehouse data; CX has no direct access |

Results: **4 of 4 tool trajectory passes on the first scored run**, both against the local Logistics server and against the Cloud Run deployment. Side effect verified separately: exactly one credit row after each run.

The 30 percent approval case (order 38629) is a scripted manual test, since automated evals cannot click Approve. Verified: reject writes nothing; approve writes exactly one `human_confirmed` row.

## Findings

1. **Transfer and delegation are different contracts.** `sub_agents` hands the conversation to the remote agent; `AgentTool` returns control. Choosing wrong silently skipped the compensation step.
2. **Prose across an agent boundary loses meaning.** Codes became "warehouse lag", and the policy returned no credit without any error. Enforcing an enum at the interface turned a silent failure into a contract.
3. **The LLM fills every undefined rule.** With two causes and no rule, it called the policy twice and picked one.
4. **Evals need clean state, at recording time too.** One case was recorded against a dirty table and captured "already issued" as the expected answer.
5. **The wrong interpreter looks like a configuration bug.** A server started from the global Python produced an authentication error that pointed at environment variables; the traceback path revealed the real cause.
6. **The auto generated agent card leaks and misdirects.** It publishes the full internal instruction and advertises `http://localhost:8001` even on Cloud Run.
7. **Remote narratives drift too.** The Logistics reply mislabeled a difference as a baseline; CX should rely on codes, not prose.
8. **Simulated data has defects.** A warehouse lag of minus 6 hours (shipped before ordered) passed through unflagged.

## Open gaps

* **Agent card:** publish a curated card with the real HTTPS URL and no internal instructions
* **Data validation:** flag negative durations in `delay_root_cause`
* **Structured A2A reply:** return codes as a data part, not only text
* **Race condition:** the idempotency check and insert are not atomic; use `MERGE` or a unique key
* **Cross service tracing:** one trace spanning CX and Logistics
* **Single source:** `deploy_logistics/logistics_agent` duplicates `logistics_agent`; generate it at deploy time
* **Runtime parity:** the container ran Python 3.14 while local used 3.11; pinned for the next deploy
* **CX deployment:** behind a real UI with an asynchronous approval queue
* **Experimental API:** ADK's A2A integration is flagged experimental (the A2A protocol itself is stable)

## Run it

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
(Get-Command python).Source        # must point into this .venv
gcloud auth application-default login
```

Local Logistics (optional when using Cloud Run):
```powershell
uvicorn logistics_agent.agent:a2a_app --port 8001
```

CX:
```powershell
python -m google.adk.cli web --port 8080 .
```

`cx_agent/.env` (not committed):
```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=<project with Gemini quota>
GOOGLE_CLOUD_LOCATION=global
AS_OF_DATE=2026-10-14
CX_SA=cx-agent@<project>.iam.gserviceaccount.com
CREDITS_TABLE=credits_eval
LOGISTICS_URL=https://<logistics-service>.run.app
```

Deploy Logistics:
```powershell
gcloud run deploy logistics-agent --source deploy_logistics --region us-central1 `
  --service-account logistics-agent@<project>.iam.gserviceaccount.com --no-allow-unauthenticated `
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=<gemini project>,GOOGLE_CLOUD_LOCATION=global,AS_OF_DATE=2026-10-14"
gcloud run services add-iam-policy-binding logistics-agent --region us-central1 `
  --member="serviceAccount:cx-agent@<project>.iam.gserviceaccount.com" --role=roles/run.invoker
```

Evaluate:
```powershell
bq query --use_legacy_sql=false "TRUNCATE TABLE ``<project>.cx_data.credits_eval``"
```
Then Evals tab, `late_order_core`, Run All, Tool Trajectory threshold 1.0.

## References

* ADK A2A exposing: https://google.github.io/adk-docs/a2a/quickstart-exposing
* ADK A2A consuming: https://adk.dev/a2a/quickstart-consuming/
* ADK tool confirmation: https://adk.dev/tools-custom/confirmation/
* Cloud Run authentication: https://cloud.google.com/run/docs/authenticating/service-to-service
