# ADK - Agent Development Kit

Build AI agents with custom tools using Google's Agent Development Kit.

## What You'll Learn

- Create an agent with custom tools (function calling)
- Define tool schemas for Gemini
- Handle tool execution and responses
- Build an interactive CLI agent

## Architecture

```
User Query
    |
    v
Gemini 2.5 Flash (with tools)
    |
    v
Tool Selection
    |
    +---> get_tcode_info
    +---> get_failed_jobs
    +---> check_system_health
    |
    v
Tool Execution (mock data or real API)
    |
    v
Gemini formats final response
    |
    v
Response to User
```

## Tools Included

| Tool | Description |
|------|-------------|
| `get_tcode_info` | Get info about SAP transaction codes |
| `get_failed_jobs` | List failed background jobs (mock) |
| `check_system_health` | Check system status (mock) |

## Files

| File | Purpose |
|------|---------|
| `sap_basis_agent.py` | Main SAP Basis agent with tools |
| `stockagent.py` | Alternative stock market agent example |
| `requirements.txt` | Python dependencies |

## Setup

```bash
cd adk
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows
pip install -r requirements.txt

# Set environment variables
export GOOGLE_API_KEY=your-api-key
# or create .env file
```

## Run

```bash
python sap_basis_agent.py
```

## Example Interactions

```
You: What is SM58 used for?
Agent: SM58 is the tRFC Monitor...

You: Check the health of PRD system
Agent: PRD system status is WARNING...

You: Show me failed jobs in PRD
Agent: Found 3 failed jobs...
```

## Key Concepts

### Function Calling Pattern
1. User sends query
2. LLM decides which tool to call
3. Tool executes and returns data
4. LLM formats response using tool data

### Tool Schema Design
- Clear, descriptive names
- Precise parameter types
- Good descriptions for LLM understanding

## Next Steps

- Connect to real SAP OData APIs
- Add more tools (ST22 dumps, SM12 locks)
- Deploy to Vertex AI Agent Engine
