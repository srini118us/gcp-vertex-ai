import os
from datetime import date, timedelta
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
import google.auth
from google.auth import impersonated_credentials
from google.cloud import bigquery
from google.adk.agents import LlmAgent
from google.adk.a2a.utils.agent_to_a2a import to_a2a

P = "enterprise-agent-labs-1012"
DS = f"{P}.logistics_data"

def _client():
    src, _ = google.auth.default()
    sa = os.getenv("LOGISTICS_SA")  # local: impersonate; Cloud Run: runtime identity
    creds = impersonated_credentials.Credentials(source_credentials=src, target_principal=sa,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"]) if sa else src
    return bigquery.Client(project=P, credentials=creds)

def delay_root_cause(order_id: int) -> dict:
    """Governed logistics diagnosis for one order: per item warehouse lag and transit time,
    compared with the shipping distribution center's 90 day baseline. Rules decide the cause."""
    end = date.fromisoformat(os.getenv("AS_OF_DATE", date.today().isoformat()))
    start = end - timedelta(days=90)
    sql = f"""
    WITH item AS (
      SELECT oi.id, oi.status, oi.created_at, oi.shipped_at, oi.delivered_at, dc.id AS dc_id, dc.name AS dc
      FROM `{DS}.order_items` oi
      JOIN `{DS}.inventory_items` ii ON oi.inventory_item_id = ii.id
      JOIN `{DS}.distribution_centers` dc ON ii.product_distribution_center_id = dc.id
      WHERE oi.order_id = @order_id),
    base AS (
      SELECT ii.product_distribution_center_id AS dc_id,
        AVG(TIMESTAMP_DIFF(oi.shipped_at, oi.created_at, HOUR)) AS avg_lag_h,
        AVG(TIMESTAMP_DIFF(oi.delivered_at, oi.shipped_at, HOUR)) AS avg_transit_h
      FROM `{DS}.order_items` oi JOIN `{DS}.inventory_items` ii ON oi.inventory_item_id = ii.id
      WHERE oi.delivered_at >= TIMESTAMP(@start) AND oi.delivered_at < TIMESTAMP(@end)
      GROUP BY dc_id)
    SELECT item.*, TIMESTAMP_DIFF(shipped_at, created_at, HOUR) AS lag_h,
      TIMESTAMP_DIFF(delivered_at, shipped_at, HOUR) AS transit_h, base.avg_lag_h, base.avg_transit_h
    FROM item LEFT JOIN base USING (dc_id)"""
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("order_id", "INT64", order_id),
        bigquery.ScalarQueryParameter("start", "STRING", start.isoformat()),
        bigquery.ScalarQueryParameter("end", "STRING", end.isoformat())])
    rows = [dict(r) for r in _client().query(sql, job_config=cfg).result()]
    if not rows:
        return {"order_id": order_id, "cause": "ORDER_NOT_FOUND"}
    items = []
    for r in rows:
        if r["shipped_at"] is None:
            cause = "NOT_YET_SHIPPED"
        elif r["lag_h"] > 1.5 * (r["avg_lag_h"] or 0):
            cause = "WAREHOUSE_DELAY"
        elif r["transit_h"] is not None and r["transit_h"] > 1.5 * (r["avg_transit_h"] or 0):
            cause = "TRANSIT_DELAY"
        else:
            cause = "WITHIN_NORMAL"
        items.append({"item_id": r["id"], "status": r["status"], "distribution_center": r["dc"],
            "warehouse_lag_h": r["lag_h"], "dc_avg_lag_h": round(r["avg_lag_h"] or 0, 1),
            "transit_h": r["transit_h"], "dc_avg_transit_h": round(r["avg_transit_h"] or 0, 1),
            "cause": cause})
    return {"order_id": order_id, "baseline_window": [start.isoformat(), end.isoformat()], "items": items}

root_agent = LlmAgent(
    name="logistics_agent", model="gemini-2.5-flash",
    description="Supply Chain team agent. Diagnoses why a specific order is delayed: warehouse lag versus transit time, against the distribution center baseline.",
    instruction="""You diagnose delivery delays for one order at a time. Always call delay_root_cause.
Report each item's cause exactly as returned, with the hours compared to the baseline.
Always include each item's cause code exactly, e.g. WAREHOUSE_DELAY.
Never speculate beyond the tool output. You do not handle refunds or customer communication.""",
    tools=[delay_root_cause])

a2a_app = to_a2a(root_agent, port=8001)