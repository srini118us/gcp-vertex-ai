# Agent Engine - Deploy Agents to Vertex AI

Deploy production-ready agents to Vertex AI Agent Engine with automatic session management.

## What You'll Learn

- Structure an agent for Agent Engine deployment
- Deploy using ADK CLI
- Manage sessions and conversations
- Test deployed agents

## Architecture

```
Local Development          Vertex AI Agent Engine
+----------------+         +----------------------+
|  stock_agent/  |  deploy |   Cloud Run          |
|  - agent.py    | ------> |   + Agent Engine     |
|  - tools.py    |         |   + Session Mgmt     |
|  - config.py   |         |   + Auto-scaling     |
+----------------+         +----------------------+
                                    |
                                    v
                           +----------------+
                           |  Gemini API    |
                           +----------------+
```

## Project Structure

```
agent-engine/
├── stock_agent/
│   ├── __init__.py      # Package exports
│   ├── agent.py         # Agent definition
│   ├── tools.py         # Tool implementations
│   └── config.py        # Configuration
└── files.zip            # Backup/archive
```

## Prerequisites

- GCP Project with Vertex AI API enabled
- Python 3.11+
- ADK CLI installed (`pip install google-adk`)
- gcloud CLI authenticated

## Setup

```bash
cd agent-engine

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
adk run stock_agent
```

## Deploy to Agent Engine

```bash
adk deploy agent_engine \
  --project=YOUR_PROJECT_ID \
  --region=us-central1 \
  --display_name="Stock Agent" \
  stock_agent
```

## Test Deployed Agent

```python
from vertexai.preview import reasoning_engines

agent = reasoning_engines.ReasoningEngine("projects/PROJECT/locations/REGION/reasoningEngines/ID")
response = agent.query(input="What's the stock price of GOOGL?")
print(response)
```

## Key Concepts

### Session Management
- Agent Engine automatically handles conversation state
- Each user gets isolated sessions
- Sessions persist across requests

### Scaling
- Automatically scales based on traffic
- No infrastructure management needed
- Pay per request

## Next Steps

1. Add more tools to the agent
2. Connect to real stock APIs
3. Add authentication
4. Monitor usage in Cloud Console
