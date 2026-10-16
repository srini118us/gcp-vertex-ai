"""Deterministic delay root cause diagnosis shared by every Logistics runtime (ADK Gemini, Claude).

Single source for the SQL, the 90 day distribution center baseline and the cause rules.
Runtimes call delay_root_cause() and must not recompute or override its result.
Behavior is kept identical to the Phase 1 implementation, including its edge cases:
  * no baseline for a DC: the average counts as 0, so any positive lag is WAREHOUSE_DELAY
  * negative durations pass through unflagged
  * shipped but undelivered items are only checked for warehouse lag
  * one cause per item, first match wins: NOT_YET_SHIPPED, WAREHOUSE_DELAY, TRANSIT_DELAY, WITHIN_NORMAL
"""
import logging
import os
from datetime import date, timedelta
import google.auth.exceptions
from google.api_core import exceptions as gexc
from google.cloud import bigquery
from .bq import DS, logistics_client

log = logging.getLogger(__name__)

CAUSE_CODES = ("NOT_YET_SHIPPED", "WAREHOUSE_DELAY", "TRANSIT_DELAY", "WITHIN_NORMAL")
ORDER_NOT_FOUND = "ORDER_NOT_FOUND"  # order level result, not an item cause
BASELINE_DAYS = 90
DELAY_FACTOR = 1.5
_INT64_MAX = 2**63 - 1

SQL = f"""
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


class DiagnosisError(Exception):
    """Base for diagnosis failures. Messages are fixed text, safe to return across the A2A boundary."""
    code = "DIAGNOSIS_FAILED"

    def __init__(self, detail: str):
        super().__init__(f"{self.code}: {detail}")

class InvalidOrderId(DiagnosisError, ValueError):
    code = "INVALID_ORDER_ID"

class LogisticsDataAccessDenied(DiagnosisError):
    code = "ACCESS_DENIED"

class LogisticsDataUnavailable(DiagnosisError):
    code = "DATA_UNAVAILABLE"


def validate_order_id(order_id) -> int:
    """Positive INT64 order id. Accepts int, integral float (model JSON), or a digit string; never echoes input."""
    if isinstance(order_id, bool):
        raise InvalidOrderId("order_id must be a positive integer")
    if isinstance(order_id, float) and order_id.is_integer():
        order_id = int(order_id)
    elif isinstance(order_id, str) and order_id.strip().isascii() and order_id.strip().isdigit():
        order_id = int(order_id.strip())
    if not isinstance(order_id, int) or not 0 < order_id <= _INT64_MAX:
        raise InvalidOrderId("order_id must be a positive integer")
    return order_id

def baseline_window(as_of: date | None = None) -> tuple[date, date]:
    end = as_of or date.fromisoformat(os.getenv("AS_OF_DATE", date.today().isoformat()))
    return end - timedelta(days=BASELINE_DAYS), end

def classify_item(r: dict) -> str:
    if r["shipped_at"] is None:
        return "NOT_YET_SHIPPED"
    if r["lag_h"] > DELAY_FACTOR * (r["avg_lag_h"] or 0):
        return "WAREHOUSE_DELAY"
    if r["transit_h"] is not None and r["transit_h"] > DELAY_FACTOR * (r["avg_transit_h"] or 0):
        return "TRANSIT_DELAY"
    return "WITHIN_NORMAL"

def diagnose_rows(order_id: int, rows: list[dict], start: date, end: date) -> dict:
    """Pure rules over query rows; the response shape is the Phase 1 contract."""
    if not rows:
        return {"order_id": order_id, "cause": ORDER_NOT_FOUND}
    items = [{"item_id": r["id"], "status": r["status"], "distribution_center": r["dc"],
              "warehouse_lag_h": r["lag_h"], "dc_avg_lag_h": round(r["avg_lag_h"] or 0, 1),
              "transit_h": r["transit_h"], "dc_avg_transit_h": round(r["avg_transit_h"] or 0, 1),
              "cause": classify_item(r)} for r in rows]
    return {"order_id": order_id, "baseline_window": [start.isoformat(), end.isoformat()], "items": items}

def query_rows(order_id: int, start: date, end: date, client: bigquery.Client | None = None) -> list[dict]:
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("order_id", "INT64", order_id),
        bigquery.ScalarQueryParameter("start", "STRING", start.isoformat()),
        bigquery.ScalarQueryParameter("end", "STRING", end.isoformat())])
    try:
        return [dict(r) for r in (client or logistics_client()).query(SQL, job_config=cfg).result()]
    except (gexc.Forbidden, gexc.Unauthorized, google.auth.exceptions.GoogleAuthError) as e:
        log.warning("logistics data access denied: %s", e)
        raise LogisticsDataAccessDenied("logistics data access denied") from e
    except (gexc.GoogleAPIError, TimeoutError, ConnectionError) as e:
        log.warning("logistics data query failed: %s", e)
        raise LogisticsDataUnavailable("logistics data temporarily unavailable") from e

def delay_root_cause(order_id, *, client: bigquery.Client | None = None, as_of: date | None = None) -> dict:
    """Governed logistics diagnosis for one order: per item warehouse lag and transit time,
    compared with the shipping distribution center's 90 day baseline. Rules decide the cause."""
    oid = validate_order_id(order_id)
    start, end = baseline_window(as_of)
    return diagnose_rows(oid, query_rows(oid, start, end, client), start, end)
