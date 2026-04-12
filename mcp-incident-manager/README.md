# MCP Incident Manager - Model Context Protocol Server

MCP server for incident management integration with Claude and other AI assistants.

## What You'll Learn

- Model Context Protocol (MCP) fundamentals
- Building MCP servers with Python
- Deploying MCP to Kubernetes
- Integrating with Claude Desktop

## Architecture

```
+------------------+     MCP Protocol     +------------------+
|  Claude Desktop  | <------------------> |   MCP Server     |
|  or AI Client    |                      |   (FastAPI)      |
+------------------+                      +--------+---------+
                                                   |
                                          +--------+---------+
                                          |   Orchestrator   |
                                          +--------+---------+
                                                   |
                              +--------------------+--------------------+
                              |                    |                    |
                              v                    v                    v
                       +------------+       +------------+       +------------+
                       | ServiceNow |       |   Slack    |       |  PagerDuty |
                       +------------+       +------------+       +------------+
```

## Project Structure

```
mcp-incident-manager/
├── config/
│   └── kubeconfig.yaml      # Kubernetes config (if deploying)
├── mcp_servers/
│   ├── server.py            # MCP server implementation
│   └── tools.py             # Tool definitions
├── orchestrator/
│   └── main.py              # Orchestration logic
├── test_demo.py             # Test script
└── requirements.txt
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `create_incident` | Create new incident |
| `get_incident` | Retrieve incident details |
| `update_incident` | Update incident status |
| `list_incidents` | List all open incidents |
| `escalate_incident` | Escalate to on-call |

## Setup

```bash
cd mcp-incident-manager

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt
```

## Run Locally

```bash
python mcp_servers/server.py
```

## Configure Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "incident-manager": {
      "command": "python",
      "args": ["path/to/mcp_servers/server.py"],
      "env": {
        "SERVICENOW_URL": "your-instance.service-now.com",
        "SERVICENOW_USER": "username",
        "SERVICENOW_PASS": "password"
      }
    }
  }
}
```

## Deploy to Kubernetes

```bash
# Apply configurations
kubectl apply -f config/deployment.yaml
kubectl apply -f config/service.yaml

# Verify
kubectl get pods -l app=mcp-incident-manager
```

## Example Usage (in Claude)

```
Create an incident for the payment gateway outage affecting production

Get details for incident INC0012345

Escalate INC0012345 to the platform team
```

## Key Concepts

### MCP Protocol
- JSON-RPC based communication
- Tool discovery and execution
- Resource management
- Prompt templates

### Server Implementation
- FastAPI for HTTP handling
- SSE for streaming responses
- Tool registration with schemas

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | Check server is running on correct port |
| Tool not found | Verify tool registration in server.py |
| Auth errors | Check ServiceNow credentials |

## Next Steps

1. Add more incident management tools
2. Integrate with additional platforms
3. Add incident analytics
4. Deploy with HTTPS/authentication
