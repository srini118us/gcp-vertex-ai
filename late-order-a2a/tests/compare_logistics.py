"""Stage D interoperability probe: Gemini Logistics versus Claude Logistics.

Sends the SAME A2A message/send request the CX agent sends, to both the Gemini
server (8001) and the Claude server (8002), for a set of orders. Compares the
cause codes extracted from each reply, records latency, and reads Claude token
usage and cost from the A2A result.metadata the Claude server now returns.

This isolates the logistics interop from the CX model, so cause-code equivalence
is measured directly. The CX level run (switching LOGISTICS_URL only) is the
separate proof that CX needs no change.

Run on the laptop with both servers up and ADC plus ANTHROPIC_API_KEY set:
    python tests\compare_logistics.py
Env overrides: GEMINI_URL, CLAUDE_URL, COMPARE_ORDERS (comma separated ids).

Offline self test of the parsing and table logic (no servers needed):
    python tests\compare_logistics.py --selftest
"""
import os
import sys
import json
import time
import uuid

CAUSE_CODES = ["NOT_YET_SHIPPED", "WAREHOUSE_DELAY", "TRANSIT_DELAY", "WITHIN_NORMAL"]

GEMINI_URL = os.getenv("GEMINI_URL", "http://localhost:8001")
CLAUDE_URL = os.getenv("CLAUDE_URL", "http://localhost:8002")
DEFAULT_ORDERS = "109778,1902,999999999"
ORDERS = [int(x) for x in os.getenv("COMPARE_ORDERS", DEFAULT_ORDERS).split(",") if x.strip()]

# Verified Haiku 5.5 standard rates, USD per million tokens, prompts under 100K.
IN_RATE = float(os.getenv("CLAUDE_IN_RATE", "0.10"))
OUT_RATE = float(os.getenv("CLAUDE_OUT_RATE", "0.50"))


def _payload(order_id: int) -> dict:
    return {
        "jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "message/send",
        "params": {"message": {
            "role": "user", "messageId": str(uuid.uuid4()),
            "parts": [{"kind": "text", "text": f"Diagnose delay for order_id={order_id}"}],
        }},
    }


def _codes_from_reply(reply: str) -> list:
    return sorted({c for c in CAUSE_CODES if c in reply})


def _extract(result: dict) -> tuple:
    texts = [p.get("text", "") for a in result.get("artifacts", [])
             for p in a.get("parts", []) if p.get("kind") == "text"]
    if not texts:
        texts = [p.get("text", "") for p in result.get("parts", [])
                 if p.get("kind") == "text"]
    reply = "\n".join(texts)
    return reply, _codes_from_reply(reply), result.get("status", {}).get("state")


def probe(url: str, order_id: int) -> dict:
    import httpx
    t0 = time.perf_counter()
    r = httpx.post(url, json=_payload(order_id), timeout=120)
    r.raise_for_status()
    ms = round((time.perf_counter() - t0) * 1000, 1)
    result = r.json().get("result", {})
    reply, codes, state = _extract(result)
    meta = result.get("metadata", {}) or {}
    return {"ms": ms, "codes": codes, "state": state,
            "usage": meta.get("usage"), "reply": reply}


def run(orders):
    rows = []
    for oid in orders:
        g = probe(GEMINI_URL, oid)
        c = probe(CLAUDE_URL, oid)
        rows.append({"order_id": oid, "gemini": g, "claude": c,
                     "codes_match": g["codes"] == c["codes"]})
    return rows


def summarize(rows):
    print(f"{'order':>10} | {'gemini codes':<28} | {'claude codes':<28} | match | "
          f"{'g ms':>7} | {'c ms':>7}")
    print("-" * 100)
    cl_in = cl_out = 0
    for row in rows:
        g, c = row["gemini"], row["claude"]
        print(f"{row['order_id']:>10} | {','.join(g['codes']) or '(none)':<28} | "
              f"{','.join(c['codes']) or '(none)':<28} | {str(row['codes_match']):>5} | "
              f"{g['ms']:>7} | {c['ms']:>7}")
        u = c.get("usage") or {}
        cl_in += u.get("input_tokens", 0)
        cl_out += u.get("output_tokens", 0)
    all_match = all(r["codes_match"] for r in rows)
    cost = cl_in / 1_000_000 * IN_RATE + cl_out / 1_000_000 * OUT_RATE
    print("-" * 100)
    print(f"cause-code equivalence: {'ALL MATCH' if all_match else 'MISMATCH, see rows'}")
    print(f"claude tokens: in={cl_in} out={cl_out}  est cost (haiku 5.5) ${cost:.6f}")
    return all_match


def selftest():
    # Canned Claude style envelope with metadata, and a Gemini style one without.
    claude = {"result": {"status": {"state": "completed"}, "artifacts": [{"parts": [
        {"kind": "text", "text": "Item A WAREHOUSE_DELAY, item B TRANSIT_DELAY"}]}],
        "metadata": {"usage": {"input_tokens": 1200, "output_tokens": 300}}}}
    gemini = {"result": {"status": {"state": "completed"}, "artifacts": [{"parts": [
        {"kind": "text", "text": "Item A WAREHOUSE_DELAY and item B TRANSIT_DELAY"}]}]}}
    _, gc, gs = _extract(gemini["result"])
    rep, cc, cs = _extract(claude["result"])
    assert gc == cc == ["TRANSIT_DELAY", "WAREHOUSE_DELAY"], (gc, cc)
    assert gs == cs == "completed"
    rows = [{"order_id": 109778,
             "gemini": {"ms": 210.0, "codes": gc, "state": gs, "usage": None, "reply": ""},
             "claude": {"ms": 980.0, "codes": cc, "state": cs,
                        "usage": claude["result"]["metadata"]["usage"], "reply": rep},
             "codes_match": gc == cc}]
    assert summarize(rows) is True
    print("SELFTEST OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    rows = run(ORDERS)
    ok = summarize(rows)
    out_path = os.path.join("docs", "phase2", "runbook", "stage_d_compare.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, default=str)
    print(f"saved {out_path}")
    sys.exit(0 if ok else 1)
