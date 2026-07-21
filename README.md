# GCP Vertex AI — Agent, Pipeline, and SAP Integration Labs

Hands-on labs exploring Google Cloud Vertex AI for enterprise and SAP-oriented AI: the Agent Development Kit (ADK), Vertex ML Pipelines, Agent Engine deployment, RAG assistants over SAP documentation, Agent-to-Agent (A2A) orchestration, Model Context Protocol (MCP) servers, and the Gemini Enterprise Agent Platform.

> Lab and prototype implementations using synthetic, SAP-like data. All system identifiers are non-production examples.

---

## Labs

| Lab | Description | Key Technology |
|---|---|---|
| `adk/` | Agent Development Kit fundamentals — custom tools, function calling, interactive CLI agents | ADK, Gemini |
| `pipelines/` | Vertex AI ML pipelines — components, artifacts, compiled pipeline runs | Kubeflow Pipelines SDK |
| `agent-engine/` | Deploying agents to Vertex AI Agent Engine with managed sessions and auto-scaling | Agent Engine, Cloud Run |
| `sap-assistant/` | SAP landscape RAG assistant — answers SAP setup and integration questions with cited sources | RAG, Discovery Engine, Gemini |
| `a2a-finops/` | Agent-to-Agent FinOps — multi-agent orchestration across SAP and GCP for cross-platform cost analysis | A2A protocol, multi-agent |
| `mcp-incident-manager/` | MCP server for incident management, integrating with ServiceNow, Slack, and PagerDuty | MCP, FastAPI, Kubernetes |
| `agentic-hub/` | Gemini Enterprise Agent Platform labs with SAP integration scenarios (S/4HANA, BTP, Joule, BDC) | Agent Platform, ADK, Gemini |

---

## Technology

| Layer | Tools |
|---|---|
| Agents / Orchestration | Google ADK, A2A protocol, MCP |
| LLMs | Gemini (Vertex AI) |
| ML Pipelines | Kubeflow Pipelines SDK, Vertex AI Pipelines |
| Deployment | Vertex AI Agent Engine, Cloud Run, Kubernetes |
| Retrieval | Discovery Engine (RAG) |
| Languages | Python |

---

## Prerequisites

- GCP project with billing enabled and Vertex AI API enabled
- Python 3.11+
- gcloud CLI authenticated

---

## Related Repositories

- **SAP AI Journey** — the primary portfolio: SAP AI Core, BDC/Databricks ML, HANA Cloud RAG, Joule Studio, agentic AI: https://github.com/srini118us/sap-ai-journey
- **AWS Bedrock Labs** — SAP-style procurement agents and enterprise guardrails on the Bedrock Converse API

## Author

[Srinivas](https://github.com/srini118us)
