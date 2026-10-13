import google.auth, google.auth.transport.requests
from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

PROJECT = "enterprise-agent-labs-1012"
creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/bigquery"])
creds.refresh(google.auth.transport.requests.Request())

bq_mcp = McpToolset(connection_params=StreamableHTTPConnectionParams(
    url="https://bigquery.googleapis.com/mcp",
    headers={"Authorization": f"Bearer {creds.token}", "x-goog-user-project": PROJECT}))

def assess_groups(groups: list[dict]) -> dict:
    """Deterministic confidence check. groups: [{"name": str, "value": float, "rows": int}].
    Flags groups under 100 rows and marks differences under 10 percent as not meaningful."""
    MIN_ROWS, MIN_DIFF = 100, 0.10
    valid = [g for g in groups if g["rows"] >= MIN_ROWS]
    out = {"low_confidence": [g["name"] for g in groups if g["rows"] < MIN_ROWS]}
    if len(valid) >= 2:
        top = max(valid, key=lambda g: g["value"])
        out["top_reliable"] = top["name"]
        out["comparisons"] = [{"vs": g["name"],
            "diff_pct": round((top["value"] - g["value"]) / top["value"] * 100, 2),
            "meaningful": (top["value"] - g["value"]) / top["value"] >= MIN_DIFF}
            for g in valid if g is not top]
    return out

root_agent = LlmAgent(
    name="data_analyst", model="gemini-3.5-flash", tools=[bq_mcp, assess_groups],
    generate_content_config=types.GenerateContentConfig(
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=5, initial_delay=2))),
       instruction="""Enterprise data analyst for bigquery-public-data.thelook_ecommerce.
Inspect schema before querying. Run queries in project enterprise-agent-labs-1012.
Read only. Always show the SQL used and cite exact figures from results.
If data cannot answer the question, say so; never estimate.
After any grouped query, call assess_groups with the results and report its flags exactly; do not compute confidence yourself.
Answer the question asked; offer alternatives in one line.""")