# Lab 03: ADK — SAP Basis Agent

## What You'll Learn

- Create an agent with custom tools (function calling)
- Define tool schemas for Gemini
- Handle tool execution and responses
- Build an interactive CLI agent

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    SAP Basis Agent                       │
├─────────────────────────────────────────────────────────┤
│  User Query                                              │
│       ↓                                                  │
│  Gemini 2.5 Flash (with tools)                          │
│       ↓                                                  │
│  Tool Selection                                          │
│       ↓                                                  │
│  ┌─────────────┬─────────────┬─────────────────┐        │
│  │get_tcode_info│get_failed_jobs│check_system_health│   │
│  └─────────────┴─────────────┴─────────────────┘        │
│       ↓                                                  │
│  Tool Execution (mock data or real API)                 │
│       ↓                                                  │
│  Gemini formats final response                          │
│       ↓                                                  │
│  Response to User                                        │
└─────────────────────────────────────────────────────────┘
```

## Tools Included

| Tool | Description |
|------|-------------|
| `get_tcode_info` | Get info about SAP transaction codes |
| `get_failed_jobs` | List failed background jobs (mock) |
| `check_system_health` | Check system status (mock) |

## Setup

```bash
cd lab-03-adk
pip install -r requirements.txt
copy .env.example .env
# Edit .env and add your GOOGLE_API_KEY
```

## Run

```bash
python sap_basis_agent.py
```

## Example Interactions

```
You: What is SM58 used for?
🔧 Agent calling tool: get_tcode_info
   Arguments: {'tcode': 'SM58'}
📋 Agent Response: SM58 is the tRFC Monitor...

You: Check the health of PRD system
🔧 Agent calling tool: check_system_health
   Arguments: {'system_id': 'PRD'}
📋 Agent Response: PRD system status is WARNING...

You: Show me failed jobs in PRD
🔧 Agent calling tool: get_failed_jobs
   Arguments: {'system_id': 'PRD', 'hours': 24}
📋 Agent Response: Found 3 failed jobs...
```

## System Design Concepts

### Function Calling Pattern
1. User sends query
2. LLM decides which tool to call (if any)
3. Tool executes and returns data
4. LLM formats response using tool data

### Tool Schema Design
- Clear, descriptive names
- Precise parameter types
- Good descriptions for LLM understanding

### Next Steps
- Connect to real SAP OData APIs (replace mock data)
- Add more tools (ST22 dumps, SM12 locks, etc.)
- Deploy to Vertex AI Agent Engine
