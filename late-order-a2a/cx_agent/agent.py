from typing import Literal
import os
import uuid, httpx
from datetime import date, timedelta
import google.auth
from google.auth import impersonated_credentials
from google.cloud import bigquery
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool, ToolContext

Cause = Literal["NOT_YET_SHIPPED", "WAREHOUSE_DELAY", "TRANSIT_DELAY", "WITHIN_NORMAL"]

P = "enterprise-agent-labs-1012"
SLA_DAYS = 5  # business rule: promised delivery within 5 days of order
CREDITS = os.getenv("CREDITS_TABLE", "credits")
LOGISTICS_URL = os.getenv("LOGISTICS_URL", "http://localhost:8001")

def diagnose_delay(order_id: int) -> dict:
    """Asks the remote Supply Chain Logistics agent, over A2A, for the delay root cause of one order."""
    payload = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "message/send",
               "params": {"message": {"role": "user", "messageId": str(uuid.uuid4()),
                          "parts": [{"kind": "text", "text": f"Diagnose delay for order_id={order_id}"}]}}}
    r = httpx.post(LOGISTICS_URL, json=payload, timeout=120)
    r.raise_for_status()
    result = r.json().get("result", {})
    texts = [p.get("text", "") for a in result.get("artifacts", []) for p in a.get("parts", []) if p.get("kind") == "text"]
    if not texts:
        texts = [p.get("text", "") for p in result.get("parts", []) if p.get("kind") == "text"]
    return {"order_id": order_id, "a2a_state": result.get("status", {}).get("state"), "logistics_reply": "\n".join(texts)}

def _client():
    src, _ = google.auth.default()
    sa = os.getenv("CX_SA")
    creds = impersonated_credentials.Credentials(source_credentials=src, target_principal=sa,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"]) if sa else src
    return bigquery.Client(project=P, credentials=creds)

def get_order_status(order_id: int) -> dict:
    """Customer facing order status from CX data, with days late versus the delivery promise."""
    sql = f"""SELECT order_id, status, created_at, shipped_at, delivered_at, num_of_item
              FROM `{P}.cx_data.orders` WHERE order_id = @id"""
    cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("id", "INT64", order_id)])
    rows = [dict(r) for r in _client().query(sql, job_config=cfg).result()]
    if not rows:
        return {"order_id": order_id, "found": False}
    o = rows[0]
    as_of = date.fromisoformat(os.getenv("AS_OF_DATE", date.today().isoformat()))
    promised = o["created_at"].date() + timedelta(days=SLA_DAYS)
    actual = o["delivered_at"].date() if o["delivered_at"] else as_of
    return {"order_id": order_id, "found": True, "status": o["status"], "items": o["num_of_item"],
            "ordered": o["created_at"].date().isoformat(), "promised_by": promised.isoformat(),
            "delivered": o["delivered_at"].date().isoformat() if o["delivered_at"] else None,
            "days_late": max((actual - promised).days, 0)}

def propose_compensation(causes: list[Cause], days_late: int) -> dict:
    """Deterministic policy. causes: every item cause from the Logistics agent. Most severe wins."""
    bad = [c for c in causes if c not in ("NOT_YET_SHIPPED", "WAREHOUSE_DELAY", "TRANSIT_DELAY", "WITHIN_NORMAL")]
    if bad: return {"error": f"Unknown cause codes {bad}; use the exact codes from logistics_agent"}
    rates = {"NOT_YET_SHIPPED": 20, "WAREHOUSE_DELAY": 15, "TRANSIT_DELAY": 10}
    actionable = [c for c in causes if c in rates]
    if days_late == 0 or not actionable:
        return {"offer": "none", "credit_pct": 0, "requires_approval": False}
    driver = max(actionable, key=rates.get)
    pct = min(rates[driver] + 5 * max(days_late - 3, 0), 30)
    return {"offer": f"{pct}% store credit", "credit_pct": pct, "driver": driver,
            "all_causes": causes, "requires_approval": pct >= 20}

def _offer(order_id: int, causes: list) -> dict:
    return propose_compensation(causes, get_order_status(order_id)["days_late"])

def _already_issued(order_id: int) -> bool:
    return list(_client().query(
        f"SELECT COUNT(*) n FROM `{P}.cx_data.{CREDITS}` WHERE order_id = @id",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("id", "INT64", order_id)])).result())[0].n > 0

def needs_approval(order_id: int, causes: list, tool_context: ToolContext = None) -> bool:
    return not _already_issued(order_id) and _offer(order_id, causes)["requires_approval"]

def issue_store_credit(order_id: int, causes: list[Cause]) -> dict:
    """Issues the policy credit. Recomputes days late and the offer itself; never trusts a model supplied amount."""
    if _already_issued(order_id):
        return {"issued": False, "reason": "credit already issued for this order"}
    o = _offer(order_id, causes)
    if o.get("error") or o["credit_pct"] == 0:
        return {"issued": False, "reason": o.get("error", "no compensation due")}
    sql = f"""INSERT `{P}.cx_data.{CREDITS}` (order_id, credit_pct, driver, approval, issued_at)
              VALUES (@id, @pct, @drv, @appr, CURRENT_TIMESTAMP())"""
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("id", "INT64", order_id),
        bigquery.ScalarQueryParameter("pct", "INT64", o["credit_pct"]),
        bigquery.ScalarQueryParameter("drv", "STRING", o["driver"]),
        bigquery.ScalarQueryParameter("appr", "STRING", "human_confirmed" if o["requires_approval"] else "auto_policy")])
    _client().query(sql, job_config=cfg).result()
    return {"issued": True, "credit_pct": o["credit_pct"], "driver": o["driver"]}

root_agent = LlmAgent(
    name="cx_agent", model="gemini-2.5-flash",
    instruction="""You are the Customer Experience agent for late order inquiries.
1. Call get_order_status. If not late, say so and stop.
2. If late, call diagnose_delay with the order_id.
3. Call propose_compensation with the cause and days_late; never invent offers.
4. If an offer exists, call issue_store_credit once with the order_id and all cause codes. Approval, when required, is requested automatically; never claim a credit was issued unless the tool returns issued true.""",
    tools=[get_order_status, propose_compensation, diagnose_delay,
           FunctionTool(issue_store_credit, require_confirmation=needs_approval)],
)