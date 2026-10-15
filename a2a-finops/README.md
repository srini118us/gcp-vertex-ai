# A2A FinOps - Agent-to-Agent Protocol

Orchestrator coordinating SAP and GCP specialist agents using A2A style agent cards. Agents run in one process over mock data; a networked A2A implementation lives in the next lab.

## What You'll Learn

* A2A Protocol fundamentals
* Multi-agent orchestration patterns
* Cross-platform agent communication (SAP + GCP)
* FinOps automation use cases

## Architecture

```
                    +------------------+
                    |   Orchestrator   |
                    |     Agent        |
                    +--------+---------+
                             |
            +----------------+----------------+
            |                                 |
            v                                 v
    +---------------+                 +---------------+
    |  SAP Agents   |                 |  GCP Agents   |
    +---------------+                 +---------------+
    | - Cost Agent  |                 | - BigQuery    |
    | - Budget Agent|                 | - Billing     |
    | - Forecast    |                 | - Recommender |
    +---------------+                 +---------------+
            |                                 |
            v                                 v
    +---------------+                 +---------------+
    |   SAP BTP     |                 | Google Cloud  |
    |   Systems     |                 |   APIs        |
    +---------------+                 +---------------+
```

## Project Structure

```
a2a-finops/
├── a2a\_protocol/      # A2A protocol implementation
├── gcp\_agents/        # GCP-specific agents (Billing, BigQuery)
├── sap\_agents/        # SAP-specific agents (Cost, Budget)
└── orchestrator/      # Main orchestrator agent
```

## Key Concepts

### A2A Protocol

* Standardized agent communication
* Agent discovery and capabilities
* Request/response patterns
* Error handling across agents

### Agent Types

|Agent|Platform|Purpose|
|-|-|-|
|Cost Agent|SAP|Retrieve cost center data|
|Budget Agent|SAP|Budget tracking and alerts|
|Billing Agent|GCP|Cloud billing analysis|
|Recommender Agent|GCP|Cost optimization suggestions|

## Setup

```bash
cd a2a-finops

# Install dependencies (each subfolder has requirements.txt)
pip install -r orchestrator/requirements.txt

# Set environment variables
export GOOGLE\_CLOUD\_PROJECT=your-project-id
export SAP\_API\_ENDPOINT=your-sap-endpoint
```

## Run

```bash
# Start orchestrator
python orchestrator/main.py

# Example queries:
# "What's our total cloud spend this month?"
# "Compare SAP vs GCP costs for Q1"
# "Get cost optimization recommendations"
```

## Use Cases

### 1\. Cross-Platform Cost Analysis

Query both SAP and GCP for unified cost reporting

### 2\. Budget Monitoring

Alert when combined cloud spend exceeds thresholds

### 3\. Optimization Recommendations

Aggregate suggestions from multiple platforms

## A2A Message Format

```json
{
  "agent\_id": "gcp-billing-agent",
  "capability": "get\_monthly\_costs",
  "parameters": {
    "project\_id": "my-project",
    "month": "2026-04"
  },
  "correlation\_id": "req-12345"
}
```

## Next Steps

1. Add more agent capabilities
2. Implement agent discovery
3. Add authentication between agents
4. Deploy to Cloud Run
5. Add monitoring and logging

