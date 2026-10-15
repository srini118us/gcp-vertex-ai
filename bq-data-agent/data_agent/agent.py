import google.auth, google.auth.transport.requests
from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
import os
DATASET = os.getenv("DATASET", "bigquery-public-data.thelook_ecommerce")

PROJECT = "enterprise-agent-labs-1012"
creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/bigquery"])
creds.refresh(google.auth.transport.requests.Request())


bq_mcp = McpToolset(connection_params=StreamableHTTPConnectionParams(
    url="https://bigquery.googleapis.com/mcp",
    headers={"Authorization": f"Bearer {creds.token}", "x-goog-user-project": PROJECT}),
    tool_filter=["list_dataset_ids", "list_table_ids", "get_dataset_info",
                 "get_table_info", "execute_sql_readonly"])

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

from datetime import date, timedelta

def get_analysis_window(days: int) -> dict:
    """Deterministic reporting window. Anchor is today (UTC); future dated rows are excluded."""
    end = date.fromisoformat(os.getenv("AS_OF_DATE")) if os.getenv("AS_OF_DATE") else date.today()
    return {"start_date": (end - timedelta(days=days)).isoformat(), "end_date": end.isoformat()}
from typing import Literal
from google.cloud import bigquery

PERIODS = {"last_30_days": 30, "last_90_days": 90, "last_quarter": 90, "last_year": 365}

def shipping_delay_by_category(period: Literal["last_30_days", "last_90_days", "last_quarter", "last_year"]) -> dict:
    """Governed metric: average shipped to delivered days per category,
    for items DELIVERED in the window [today minus days, today). Use this for any shipping delay question."""
    days = PERIODS[period]
    w = get_analysis_window(days)
    sql = f"""SELECT p.category AS name,
      ROUND(AVG(TIMESTAMP_DIFF(oi.delivered_at, oi.shipped_at, SECOND))/86400, 4) AS value,
      COUNT(*) AS row_count
    FROM `{DATASET}.order_items` oi
    JOIN `{DATASET}.products` p ON oi.product_id = p.id
    WHERE oi.shipped_at IS NOT NULL
      AND oi.delivered_at >= TIMESTAMP(@start) AND oi.delivered_at < TIMESTAMP(@end)
    GROUP BY name ORDER BY value DESC"""
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("start", "STRING", w["start_date"]),
        bigquery.ScalarQueryParameter("end", "STRING", w["end_date"])])
    rows = bigquery.Client(project=PROJECT).query(sql, job_config=cfg).result()
    groups = [{"name": r["name"], "value": r["value"], "rows": r["row_count"]} for r in rows]
    return {"metric": "shipping_delay_by_category", "window": w, "sql": sql,
            "groups": groups, "assessment": assess_groups(groups)}

root_agent = LlmAgent(
    name="data_analyst", model="gemini-2.5-flash", tools=[bq_mcp, get_analysis_window, shipping_delay_by_category],
    generate_content_config=types.GenerateContentConfig(
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=5, initial_delay=5,  max_delay=60))),
               instruction="""Enterprise data analyst for bigquery-public-data.thelook_ecommerce.
Inspect schema before querying. Run queries in project enterprise-agent-labs-1012.
Read only. Show only SQL that actually ran: the sql field returned by a tool, or the exact query sent to execute_sql_readonly. Never write SQL from memory. Cite exact figures from results.
If data cannot answer the question, say so; never estimate.
For any relative period, call get_analysis_window first and filter with those exact dates as literals; never use CURRENT_TIMESTAMP or MAX dates.
For shipping delay questions, use shipping_delay_by_category, not ad hoc SQL.
After any grouped query, call assess_groups with the groups list and report its flags exactly; do not compute confidence yourself.
Answer the question asked; offer alternatives in one line.""")

