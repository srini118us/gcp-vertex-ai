# GCP Vertex AI Labs

Hands-on labs exploring Google Cloud Vertex AI capabilities including Agent Development Kit (ADK), Pipelines, Agent-to-Agent (A2A) protocol, and Model Context Protocol (MCP) integration.

## Labs Overview

| Lab | Description | Key Technologies |
|-----|-------------|------------------|
| [adk](./adk/) | Agent Development Kit fundamentals | ADK, Gemini, Python |
| [pipelines](./pipelines/) | Vertex AI ML Pipelines | Kubeflow, TFX |
| [agent-engine](./agent-engine/) | Deploy agents to Vertex AI Agent Engine | Agent Engine, Cloud Run |
| [sap-assistant](./sap-assistant/) | SAP Landscape RAG Assistant with document search | RAG, Discovery Engine, Gemini |
| [a2a-finops](./a2a-finops/) | Agent-to-Agent FinOps orchestration | A2A Protocol, Multi-Agent |
| [mcp-incident-manager](./mcp-incident-manager/) | MCP Server for incident management | MCP, Kubernetes, FastAPI |

## Prerequisites

- GCP Project with billing enabled
- Python 3.11+
- gcloud CLI authenticated
- Vertex AI API enabled

## Quick Start

```bash
# Clone the repository
git clone https://github.com/srini118us/gcp-vertex-ai.git
cd gcp-vertex-ai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate   # Windows

# Install base dependencies
pip install -r requirements.txt

# Authenticate with GCP
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

## Environment Setup

Copy the template and fill in your values:

```bash
cp .env.template .env
```

Required environment variables:
```
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=true
```

## Lab Details

### ADK - Agent Development Kit
Build AI agents using Google's Agent Development Kit with tool integration.

### Pipelines
Create and run ML pipelines on Vertex AI for training and deployment workflows.

### Agent Engine
Deploy production-ready agents to Vertex AI Agent Engine with session management.

### SAP Assistant
RAG-powered assistant that searches SAP documentation using Discovery Engine and provides synthesized answers with citations.

### A2A FinOps
Multi-agent system demonstrating Agent-to-Agent protocol for financial operations orchestration between SAP and GCP agents.

### MCP Incident Manager
Model Context Protocol server deployed on Kubernetes for incident management integration with Claude and other AI assistants.

## Project Structure

```
gcp-vertex-ai/
├── adk/                    # ADK fundamentals lab
├── pipelines/              # Vertex AI Pipelines lab
├── agent-engine/           # Agent Engine deployment lab
├── sap-assistant/          # SAP RAG Assistant lab
├── a2a-finops/             # A2A Protocol lab
├── mcp-incident-manager/   # MCP Server lab
├── .env.template           # Environment template
├── .gitignore              # Git ignore rules
├── requirements.txt        # Base Python dependencies
└── README.md               # This file
```

## Resources

- [Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [Agent Development Kit](https://google.github.io/adk-docs/)
- [Discovery Engine API](https://cloud.google.com/discovery-engine/docs)
- [A2A Protocol](https://github.com/google/A2A)
- [Model Context Protocol](https://modelcontextprotocol.io/)

## Author

**Srinivasa Dasari**  
Solution Architect, Deloitte US  
April 2026

---

*Part of the AI/ML learning journey - GCP track*
