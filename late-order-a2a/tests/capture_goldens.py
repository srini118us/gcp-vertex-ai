"""Capture live goldens from the Phase 1 delay_root_cause (loaded from git, so the refactor cannot influence it).

    .venv\\Scripts\\python tests\\capture_goldens.py            (needs ADC; impersonates LOGISTICS_SA from logistics_agent/.env)

Writes tests/golden/delay_root_cause_live.json: fixed cases plus one order per behavior, found by sampling.
Data is the public, simulated thelook snapshot; no credentials or identities are written.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from legacy import LEGACY_COMMIT, load_legacy

AS_OF = "2026-10-14"
OUT = Path(__file__).parent / "golden" / "delay_root_cause_live.json"
FIXED = [("split_shipment_warehouse_and_transit", 109778), ("cx_on_time", 1902),
         ("approval_case", 38629), ("missing_order", 999999999)]
SAMPLE = 60

def labels(result):
    items = result.get("items", [])
    codes = {i["cause"] for i in items}
    out = []
    if len(items) >= 3: out.append("multiple_items")
    for code in ("NOT_YET_SHIPPED", "WAREHOUSE_DELAY", "TRANSIT_DELAY", "WITHIN_NORMAL"):
        if codes == {code}: out.append(f"only_{code.lower()}")
    if any(i["status"] == "Shipped" and i["transit_h"] is None and i["cause"] != "NOT_YET_SHIPPED" for i in items):
        out.append("shipped_undelivered")
    if any((i["warehouse_lag_h"] or 0) < 0 or (i["transit_h"] or 0) < 0 for i in items):
        out.append("negative_duration")
    return out

def main():
    os.environ["AS_OF_DATE"] = AS_OF
    legacy = load_legacy()
    from google.cloud import bigquery
    client = legacy._client()
    sample_sql = f"""
      SELECT order_id FROM (
        SELECT order_id, COUNTIF(shipped_at IS NULL) unshipped, COUNTIF(shipped_at IS NOT NULL AND delivered_at IS NULL) in_transit, COUNT(*) n
        FROM `{legacy.DS}.order_items` WHERE created_at < TIMESTAMP(@end)
        GROUP BY order_id)
      WHERE TRUE
      QUALIFY ROW_NUMBER() OVER (PARTITION BY unshipped > 0, in_transit > 0, n >= 3 ORDER BY FARM_FINGERPRINT(CAST(order_id AS STRING))) <= 8
      ORDER BY FARM_FINGERPRINT(CAST(order_id AS STRING)) LIMIT {SAMPLE}"""
    cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("end", "STRING", AS_OF)])
    sampled = [r.order_id for r in client.query(sample_sql, job_config=cfg).result()]

    cases, wanted = [], {"multiple_items", "only_not_yet_shipped", "only_warehouse_delay", "only_transit_delay",
                         "only_within_normal", "shipped_undelivered", "negative_duration"}
    for label, oid in FIXED:
        cases.append({"label": label, "order_id": oid, "result": legacy.delay_root_cause(oid)})
    for oid in sampled:
        result = legacy.delay_root_cause(oid)
        new = [l for l in labels(result) if l in wanted]
        if new:
            cases.append({"label": "+".join(new), "order_id": oid, "result": result})
            wanted -= set(new)
        if not wanted:
            break
    doc = {"legacy_commit": LEGACY_COMMIT, "as_of_date": AS_OF,
           "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "missing_behaviors": sorted(wanted), "cases": cases}
    OUT.write_text(json.dumps(doc, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"{len(cases)} cases -> {OUT}")
    for c in cases:
        print(f"  {c['order_id']:>10}  {c['label']:45} {[i['cause'] for i in c['result'].get('items', [])] or c['result'].get('cause')}")
    if wanted:
        print("not found in sample:", sorted(wanted))

if __name__ == "__main__":
    main()
