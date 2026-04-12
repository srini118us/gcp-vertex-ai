# SAP Assistant - RAG Documentation Search

AI-powered assistant that answers SAP setup and integration questions using RAG (Retrieval-Augmented Generation) with Discovery Engine.

## What You'll Learn

- Build RAG applications with Discovery Engine
- Create custom search tools for agents
- Index and search PDF documents
- Deploy to Vertex AI Agent Engine

## Architecture

```
User Query
    |
    v
Agent Engine
    |
    v
Gemini 2.0 Flash
    |
    v
search_sap_docs tool
    |
    v
Discovery Engine API
    |
    v
Data Store (PDFs)
    |
    v
Synthesized Answer with Citations
```

## Project Structure

```
sap-assistant/
└── sap_landscape_agent/
    ├── __init__.py          # Package exports (root_agent)
    ├── agent.py             # Agent definition with system instruction
    ├── tools.py             # RAG search tool using Discovery Engine
    ├── config.py            # Configuration (project ID, data store ID)
    └── requirements.txt     # Dependencies
```

## Documents Indexed

| Document | Topics |
|----------|--------|
| Joule_Onboarding.pdf | Joule setup, BTP booster |
| SAP_BDC_Admin.pdf | Business Data Cloud |
| SAP_AI_CORE.pdf | AI Core, ML deployment |
| Identity_Authentication_en.pdf | IAS, SSO |

## Configuration

| Setting | Value |
|---------|-------|
| GCP Project | `your-project-id` |
| Region | `us-central1` |
| Data Store | `your-data-store-id` |
| Model | `gemini-2.0-flash` |

## Setup

```bash
cd sap-assistant

pip install google-adk google-cloud-aiplatform google-cloud-discoveryengine

# Authenticate
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID

# Set environment variables
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_CLOUD_LOCATION=us-central1
```

## Run Locally

```bash
adk run sap_landscape_agent
```

## Example Queries

```
How to setup Joule?
What are prerequisites for BDC integration?
How to configure Identity Authentication Service?
```

## Deploy to Agent Engine

```bash
adk deploy agent_engine \
  --project=YOUR_PROJECT_ID \
  --region=us-central1 \
  --display_name="SAP Landscape Assistant" \
  sap_landscape_agent
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `No API key` error | Set `GOOGLE_GENAI_USE_VERTEXAI=true` |
| `Permission denied` | Grant `discoveryengine.viewer` role |
| `429 Rate Limit` | Wait 1-2 minutes between requests |
| Empty search results | Add `extractive_content_spec` to ContentSearchSpec |

## Key Learnings

1. **Can't mix tool types** - Use custom Python functions, not VertexAiSearchTool
2. **ContentSearchSpec required** - Without it, only document titles returned
3. **Service account permissions** - Compute, AI Platform, and AI Platform RE all need access

## Resources

- [Vertex AI Agent Engine](https://cloud.google.com/vertex-ai/docs/agents)
- [Discovery Engine API](https://cloud.google.com/discovery-engine/docs)
- [Google ADK Documentation](https://google.github.io/adk-docs/)
