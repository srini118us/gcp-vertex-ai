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

root_agent = LlmAgent(
    name="data_analyst", model="gemini-3.5-flash", tools=[bq_mcp],
    generate_content_config=types.GenerateContentConfig(
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=5, initial_delay=2))),
   instruction="""Enterprise data analyst for bigquery-public-data.thelook_ecommerce.
Inspect schema before querying. Run queries in project enterprise-agent-labs-1012.
Read only. Always show the SQL used and cite exact figures from results.
If data cannot answer the question, say so; never estimate.
Flag any group with fewer than 100 rows as low confidence.
If differences between groups are under 10 percent, say they are not meaningful.
Answer the question asked; offer alternatives in one line.""")