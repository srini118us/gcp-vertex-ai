# Agentic Hub — Gemini Enterprise Agent Platform Labs

Hands-on labs exploring Google Cloud's **Gemini Enterprise Agent Platform** (also referenced as "Agentspace" in some materials — confirm the canonical product name for your engagement). Several use cases here focus on **SAP integration scenarios** (combining the platform with SAP backends like S/4HANA, BTP, Joule, BDC).

Each subfolder is a self-contained lab with its own venv, README, and `requirements.txt`, following the same conventions as the sibling labs ([adk](../adk/), [agent-engine](../agent-engine/), [sap-assistant](../sap-assistant/)).

## Platform concepts (from official docs)

| Concept | Purpose |
|---|---|
| **Agents** | AI systems using reasoning + tools for enterprise tasks |
| **Sessions** | Conversation history for a single user-agent thread |
| **Memory Bank** | Long-term personalized memory across sessions |
| **Agent Registry** | Catalog of your, Google's, and third-party agents |
| **Agent Identity** | SPIFFE-formatted IDs (per-agent, not shared service accounts) |
| **Agent Runtime** | Execution environment for deployed agents |
| **Model Garden** | 200+ foundation models (Google + partners + OSS) |

## Supported SDKs / frameworks

- **ADK** (Agent Development Kit) — primary toolkit. Two surfaces exist (see below).
- **LangChain, LangGraph, AG2, LlamaIndex** — alternative agent frameworks
- **Agent2Agent (A2A)** — multi-agent orchestration (pattern reused from [../a2a-finops/](../a2a-finops/))
- **RAG Engine** — retrieval workflows

## Two ADK paths — pick one per lab

The official docs offer two quickstarts. They use **different import paths and target different deployment surfaces** — don't mix them in the same lab.

| | Path A: Agents CLI | Path B: Vertex AI SDK |
|---|---|---|
| **Install** | `uvx google-agents-cli setup` | `pip install "google-cloud-aiplatform[agent_engines,adk]>=1.112"` |
| **Import** | `from adk import Agent` | `from google.adk.agents import Agent` |
| **Scaffold** | `agents-cli create <name> --prototype` | hand-written Python |
| **Run local** | `agents-cli run "..."` | `app.async_stream_query(...)` |
| **Eval** | built-in `agents-cli eval run` | DIY |
| **Deploy** | `agents-cli deploy` → **Cloud Run** | `client.agent_engines.create(...)` → **Agent Runtime** |
| **Claude Code support** | explicitly listed as a supported AI dev tool | use as a general code editor |
| **Best for** | Scaffolded labs, eval-driven dev, business demos | Tight integration with existing Vertex AI code, A2A patterns |

Quickstarts:
- Path A: [Build an agent with ADK and Agents CLI](https://docs.cloud.google.com/gemini-enterprise-agent-platform/agents/quickstart-adk)
- Path B: [Quickstart: Develop with ADK on Agent Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk)

> The existing [../agent-engine/](../agent-engine/) lab uses the **older** `adk deploy agent_engine` CLI. Path B's `client.agent_engines.create()` is the current programmatic equivalent.

## Why a separate hub

This platform sits a level above raw ADK / Agent Engine — it bundles agent registry, memory bank, identity, and a model garden as managed services. The other labs in this repo build agents from primitives; this folder explores how the managed platform assembles them for enterprise use. Keeping it separate avoids muddling the "build from scratch" labs with the "consume the managed platform" ones.

## What's planned

| Lab | Status | Description |
|-----|--------|-------------|
| _TBD_ | planned | First Agentspace use case — to be defined |
| _TBD_ | planned | SAP × Agentspace integration scenario |

> Add a row per use case as you scaffold it. Delete this note once the table fills in.

### Candidate SAP-combination ideas
Use these as seed prompts; pick whichever matches what you actually need to demo. (The official docs reference generic connectors like Drive/Jira/Slack — SAP integration will be via custom ADK tools / OData calls / BTP destinations.)

- **Enterprise search over SAP knowledge base** — index SAP Help / Joule onboarding docs, expose as an internal Q&A agent in the registry.
- **Agent calling S/4HANA OData** — purchase-order lookup, sales-order status, master-data queries via a custom ADK tool.
- **Agent + SAP BTP destinations** — connect via BTP Destination service so on-prem S/4 systems are reachable from the agent runtime.
- **Multi-agent: Gemini Agent × Joule** — compare/contrast the two agent frontends for the same business task (e.g. cost-center inquiry) using A2A.
- **Memory Bank + SAP user context** — personalize an internal-help agent with each user's SAP role/recent transactions.

## Conventions (inherited from the parent repo)

Each lab follows the same shape:

```
<lab-name>/
├── README.md              # What it builds, how to run, deploy steps
├── requirements.txt       # Pinned Python deps for this lab
├── .env                   # Local config (gitignored — never commit)
├── venv/                  # Per-lab virtual env (gitignored)
└── <package_name>/        # Agent code as an importable package
    ├── __init__.py
    ├── agent.py
    ├── tools.py
    └── config.py
```

## Prerequisites

- GCP project with **billing enabled**
- Python 3.11+
- `gcloud` CLI authenticated: `gcloud auth application-default login`
- For Path A: install [uv](https://docs.astral.sh/uv/)
- For Path B: `pip install --upgrade "google-cloud-aiplatform[agent_engines,adk]>=1.112"`

### APIs to enable
- Agent Platform API (`aiplatform.googleapis.com`)
- Cloud Storage API (`storage.googleapis.com`)

```bash
gcloud services enable aiplatform.googleapis.com storage.googleapis.com
```

### IAM roles (on your user or service account)
- `roles/aiplatform.user` — Agent Platform User
- `roles/storage.admin` — Storage Admin (Path B needs a staging bucket)

Project-wide env vars (see [../.env.template](../.env.template)):

```bash
GOOGLE_CLOUD_PROJECT=<your-project-id>
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=true
```

## Starting a new use case

**Path A (Agents CLI — recommended for new labs):**
```bash
cd agentic-hub
uvx google-agents-cli setup           # one-time per machine
agents-cli create <new-use-case> --prototype --yes
cd <new-use-case> && agents-cli install
agents-cli run "test prompt"
```

**Path B (Vertex AI SDK — when integrating with existing Vertex code):**
```bash
cd agentic-hub
mkdir <new-use-case> && cd <new-use-case>
python -m venv venv && source venv/bin/activate
pip install "google-cloud-aiplatform[agent_engines,adk]>=1.112"
# Then ask Claude Code to scaffold agent.py following the Path B quickstart.
```

## Notes

- Default model: `gemini-2.5-flash` unless a specific lab needs Pro.
- Region: `us-central1` (matches existing labs — pick a different region only if a feature requires it).
- Cost: agent labs are typically a few cents per run; deployed Agent Runtime instances and Memory Bank/data stores bill while running — tear them down when done.
- Platform prerequisite: confirm the Gemini Enterprise Agent Platform / Agentspace is enabled on your GCP project or org (separately provisioned, not a default Vertex AI API).
- Naming caveat: official docs use "Gemini Enterprise Agent Platform" / "Agent Platform"; "Agentspace" appears in some marketing and earlier materials. Treat as the same product family until confirmed otherwise.

## Reference

- [Gemini Enterprise Agent Platform docs](https://docs.cloud.google.com/gemini-enterprise-agent-platform/agents) — concepts, ADK quickstarts, Agent Runtime
- Agent Development Kit — `pip install google-adk` (same toolkit used in [../adk/](../adk/))
- For SAP-side integration, cross-reference patterns in [../../sap-ai-journey/](../../sap-ai-journey/) (SAP AI Core, MCP, BTP destinations).
