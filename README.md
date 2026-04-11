# SAP Landscape Documentation Assistant

An AI-powered assistant that answers SAP setup and integration questions by searching through actual SAP documentation using RAG (Retrieval-Augmented Generation).

## 🎯 What It Does

- Searches through indexed SAP PDFs (Joule, BDC, AI Core, IAS)
- Provides synthesized answers with source citations
- Runs on Vertex AI Agent Engine with automatic session management

## 🏗️ Architecture

```
User Query → Agent Engine → Gemini 2.0 Flash → search_sap_docs tool → Discovery Engine → Data Store (PDFs)
```

## 📁 Project Structure

```
sap_landscape_agent/
├── __init__.py          # Package exports (root_agent)
├── agent.py             # Agent definition with system instruction
├── tools.py             # RAG search tool using Discovery Engine API
├── config.py            # Configuration (project ID, data store ID)
├── requirements.txt     # Dependencies
└── .env                 # Environment variables
```

## 🚀 Quick Start

### Prerequisites

- GCP Project with billing enabled
- Python 3.11+
- gcloud CLI authenticated

### 1. Install Dependencies

```bash
pip install google-adk google-cloud-aiplatform google-cloud-discoveryengine
```

### 2. Authenticate

```bash
gcloud auth application-default login
gcloud config set project genai-2222026
```

### 3. Set Environment Variables

**PowerShell:**
```powershell
$env:GOOGLE_GENAI_USE_VERTEXAI = "true"
$env:GOOGLE_CLOUD_PROJECT = "genai-2222026"
$env:GOOGLE_CLOUD_LOCATION = "us-central1"
```

**Bash:**
```bash
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT=genai-2222026
export GOOGLE_CLOUD_LOCATION=us-central1
```

### 4. Run Locally

```bash
adk run sap_landscape_agent
```

### 5. Test Queries

```
How to setup Joule?
What are prerequisites for BDC integration?
How to configure Identity Authentication Service?
```

### 6. Deploy to Agent Engine

```bash
adk deploy agent_engine \
  --project=genai-2222026 \
  --region=us-central1 \
  --display_name="SAP Landscape Assistant" \
  sap_landscape_agent
```

## ⚙️ Configuration

| Setting | Value |
|---------|-------|
| GCP Project | `genai-2222026` |
| Region | `us-central1` |
| Data Store | `sap-landscape-docs_1775532657104` |
| Model | `gemini-2.0-flash` |
| GCS Bucket | `gs://srini118bucket/` |

## 📚 Documents Indexed

| Document | Topics |
|----------|--------|
| Joule_Onboarding.pdf | Joule setup, BTP booster |
| SAP_BDC_Admin.pdf | Business Data Cloud |
| SAP_AI_CORE.pdf | AI Core, ML deployment |
| Identity_Authentication_en.pdf | IAS, SSO |

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| `No API key` error | Set `GOOGLE_GENAI_USE_VERTEXAI=true` |
| `Permission denied` | Grant `discoveryengine.viewer` to service accounts |
| `429 Rate Limit` | Wait 1-2 minutes between requests |
| Empty search results | Ensure `ContentSearchSpec` includes `extractive_content_spec` |

## 📖 Key Learnings

1. **Can't mix tool types** - Use custom Python functions instead of `VertexAiSearchTool`
2. **ContentSearchSpec is required** - Without it, only document titles are returned
3. **Three service accounts need permissions** - Compute, AI Platform, and AI Platform RE

## 🔗 Resources

- [Vertex AI Agent Engine](https://cloud.google.com/vertex-ai/docs/agents)
- [Discovery Engine API](https://cloud.google.com/discovery-engine/docs)
- [Google ADK Documentation](https://google.github.io/adk-docs/)

## 👤 Author

**Srinivasa Dasari**  
Solution Architect, Deloitte SA  
April 2026

---

*Part of the GCP Vertex AI Learning Path - Lab 06*
