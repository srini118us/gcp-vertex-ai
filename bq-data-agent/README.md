# BigQuery Data Analyst Agent

Governed enterprise data agent built with Google Agent Development Kit (ADK), Gemini, and the Google hosted BigQuery MCP server.

Data source: `bigquery-public-data.thelook_ecommerce` (public, simulated ecommerce data).

## Business problem

Business users ask plain English questions such as "Which product categories had the longest shipping delay in the last 90 days?" A useful answer must be grounded in real data, repeatable across runs, and honest about weak evidence. A plain "chat with SQL" agent fails on all three: it writes different SQL each time, ranks statistical noise, and can invent its own audit trail.

## Architecture view

```
                         User question
                               │
                               ▼
                 ┌───────────────────────────┐
                 │  ADK LlmAgent (Gemini)    │  interprets intent,
                 │  data_analyst             │  picks tools, explains
                 └─────────────┬─────────────┘
          ┌──────────────┬─────┴────────┬──────────────────────┐
          ▼              ▼              ▼                      ▼
 ┌────────────────┐ ┌──────────────┐ ┌────────────────────┐ ┌──────────────────┐
 │ BigQuery MCP   │ │ get_analysis │ │ shipping_delay_by_ │ │ assess_groups    │
 │ (Google hosted)│ │ _window      │ │ category           │ │                  │
 │ ad hoc, read   │ │ code defines │ │ governed metric:   │ │ code enforces    │
 │ only SQL       │ │ "last N days"│ │ fixed parameterized│ │ confidence rules │
 └───────┬────────┘ └──────────────┘ │ SQL, returns its   │ └──────────────────┘
         │                           │ own SQL as evidence│
         ▼                           └─────────┬──────────┘
 ┌──────────────────────────────────────────────▼─────────┐
 │                BigQuery (thelook_ecommerce)            │
 └────────────────────────────────────────────────────────┘
```

Responsibility split:

| Layer | Owner | Examples |
|---|---|---|
| Interpretation and explanation | LLM (Gemini) | map wording to a tool and parameters, write the narrative |
| Data access | MCP | schema discovery, `execute_sql_readonly` for exploratory questions |
| Business definitions | Code | reporting window, metric SQL |
| Business rules | Code | under 100 rows means low confidence; under 10 percent difference is not meaningful |

## Build journey

| Step | Change | Why |
|---|---|---|
| 5 | ADK agent plus BigQuery MCP | baseline: agent discovers schema and writes its own SQL |
| 5b | `assess_groups` tool | confidence thresholds moved from prompt into code |
| 5c | `get_analysis_window` tool | "last 90 days" anchored in code; earlier runs anchored to today in one session and to the latest delivery in another |
| 5d | `shipping_delay_by_category` governed metric | two sessions filtered on different columns and gave different answers for the same question |
| 5e | tool returns its SQL; model switched to `gemini-2.5-flash` | the agent displayed SQL it never ran; newest model hit capacity limits |

## Design decisions

| Decision | Options considered | Choice | Trade off |
|---|---|---|---|
| Data access | direct BigQuery client only; MCP only; both | both: MCP for exploration, client library inside governed metrics | two data paths to audit |
| Business rules | chat message; system instruction; code | code (`assess_groups`) | rules change needs a code release, which is the point |
| Metric definitions | LLM writes SQL each time; fixed SQL templates | fixed parameterized SQL for known KPIs | each new KPI needs a new tool (a small semantic layer) |
| Routing | LLM first; deterministic router first | LLM first for this lab | flexible wording, but costs a model call; known KPIs could use an ADK SequentialAgent instead |
| Audit evidence | LLM restates SQL; tool returns SQL | tool returns SQL | slightly larger tool payloads |
| Model project | same project as data; separate | Gemini billed to a project with quota, BigQuery to the lab project | cross project configuration to manage |

## Findings

1. **Prompt rules are not persistent.** Rules typed into chat vanish in a new session; the agent still replied "noted and fully understood."
2. **Code governs numbers, not narrative.** After 5d, numbers were identical across sessions and across a model change (Socks & Hosiery: 2.6244 days, n=174 in every run). The explanation still varied: `gemini-2.5-flash` compared against the wrong baseline group when paraphrasing `assess_groups` output.
3. **LLMs fabricate audit trails.** With "always show the SQL" in the instruction and no SQL returned by the tool, Gemini wrote plausible SQL that would not even run (`AS rows` is a reserved word in BigQuery).
4. **Capacity is an architecture concern.** A brand new project returned 429 RESOURCE_EXHAUSTED for hours; the same code worked from an older project. Retry policy helps with bursts, not with missing quota.
5. **Read only enforced by the server.** The MCP tool used was `execute_sql_readonly`, so read only access does not depend on the prompt.

## Measurements

| Metric | 5 (LLM writes SQL) | 5d (governed metric) |
|---|---|---|
| Events per question | 22 to 32 | 8 |
| Ad hoc SQL calls for a KPI question | several | 0 |
| Same numbers across two sessions | no | yes |
| Same numbers across two models | not tested | yes |

## Open architecture gaps

* **Evaluation:** no automated check yet that the narrative matches tool output (next step: ADK eval set).
* **Structured final answer:** a response schema would stop narrative drift.
* **Credential lifecycle:** the MCP bearer token is fetched once and expires after about an hour; production needs refresh or Agent Identity.
* **Cost guardrail:** no `maximum_bytes_billed` on either query path.
* **Observability:** traces visible in the ADK UI only, not exported to Cloud Trace.
* **Model fallback:** one hardcoded model; production needs a fallback chain.
* **Data quality:** the dataset has both "Suits" and "Suits & Sport Coats"; a real semantic layer would reconcile categories.

## Run it

```powershell
cd bq-data-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
gcloud auth application-default login
adk web --port 8080 .
```

`data_agent/.env` (not committed):

```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=<project with Gemini quota>
GOOGLE_CLOUD_LOCATION=global
```

Open http://127.0.0.1:8080, select `data_agent`, ask a shipping delay question.

## References

* BigQuery MCP server: https://docs.cloud.google.com/bigquery/docs/use-bigquery-mcp
* ADK documentation: https://google.github.io/adk-docs/
* Vertex AI 429 guidance: https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429
