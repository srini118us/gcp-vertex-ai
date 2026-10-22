"""Approval gate, idempotent executor and verifier. Deterministic, no model.

Flow for a final decision (results/decisions/agent/<case>.json):
  APPROVE                 -> approval request (PENDING) with an evidence package and its hash
  HOLD, REJECT,
  REQUEST_REVIEW          -> exception queue; there is no code path from here to a posting

  approve(rid, approver)  separation of duties: a known human; role rank at least the required
                          role; not the PO requester; service identities can never approve.
                          The approval records the evidence hash it saw.
  execute(rid, executor)  only svc-ap-executor; only APPROVED requests; the evidence must still
                          hash to what the approver saw (tamper check). The idempotency key is
                          vendor plus normalized invoice number, enforced by a UNIQUE constraint:
                            same request again        -> replay, returns the first posting
                            another invoice, same key -> duplicate blocked, alert
  verify(rid, verifier)   reads the ledger back on its own: exactly one posting for the invoice,
                          and vendor, number, amount and currency equal what was approved.
                          Anything else is a MISMATCH alert.

Every action, accepted or refused, is written to the hash chained audit log. The agent identity
(svc-ap-agent) appears nowhere in this file as an actor that can change state.
"""
import hashlib
import json
import re
import sqlite3
import time

import ap_store
from common import D

USERS = json.load(open(D("spec", "users.json"), encoding="utf-8"))
RANK = {"AP_CLERK": 1, "AP_MANAGER": 2, "CONTROLLER": 3, "CFO": 4}
EXECUTOR, VERIFIER = "svc-ap-executor", "svc-ap-verifier"


class Refused(Exception):
    pass


def norm_number(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def idempotency_key(vendor_id, invoice_number):
    """One posting per vendor and normalized invoice number, the same identity the duplicate
    rule uses (AP-POL-02). 'AC 10077' and 'AC-10077' get the same key."""
    return hashlib.sha256(f"{vendor_id}|{norm_number(invoice_number)}".encode()).hexdigest()


def evidence_hash(ev):
    return hashlib.sha256(json.dumps(ev, sort_keys=True).encode()).hexdigest()


def evidence_package(decision, verified):
    """What the approver sees and signs off on. Facts come from the verified extraction and the
    rules engine; the agent contributes only flags and an explanation."""
    f = verified["fields"]
    agent = decision.get("agent") or {}
    matrix = next((fd["detail"] for fd in decision.get("findings", []) if fd["rule"] == "APPROVAL_MATRIX"), "")
    return {"case_id": decision["case_id"], "vendor_id": verified["vendor_id"],
            "invoice_number": f["invoice_number"]["value"], "po_number": f["po_number"]["value"],
            "amount": f["total"]["value"], "currency": f["currency"]["value"],
            "required_role": decision["approver_role"], "approval_matrix": matrix,
            "rule_findings": [fd["rule"] for fd in decision.get("findings", [])],
            "agent_injection_flag": bool(agent.get("injection_detected")),
            "agent_explanation": agent.get("explanation", ""),
            "agent_citations": agent.get("citations", [])}


def submit(con, decision, verified, po_requester):
    """Route a final decision. Idempotent: submitting the same case twice changes nothing."""
    cid = decision["case_id"]
    if decision["disposition"] != "APPROVE":
        con.execute("BEGIN IMMEDIATE")
        cur = con.execute("INSERT OR IGNORE INTO exceptions VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (cid, decision["disposition"], ",".join(decision["reasons"]), decision.get("disputed"),
                           ((decision.get("agent") or {}).get("explanation") or "")[:2000], "OPEN", time.time()))
        if cur.rowcount:
            ap_store.audit(con, "workflow", "exception_queued", cid,
                           {"disposition": decision["disposition"], "reasons": decision["reasons"]}, in_tx=True)
        con.execute("COMMIT")
        return None
    rid = f"REQ-{cid}"
    ev = evidence_package(decision, verified)
    con.execute("BEGIN IMMEDIATE")
    cur = con.execute("INSERT OR IGNORE INTO approval_requests VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (rid, cid, ev["vendor_id"], ev["invoice_number"], ev["po_number"], po_requester,
                       ev["amount"], ev["currency"], ev["required_role"], evidence_hash(ev),
                       json.dumps(ev, sort_keys=True), "PENDING", time.time()))
    if cur.rowcount:
        ap_store.audit(con, "workflow", "approval_requested", cid,
                       {"request_id": rid, "required_role": ev["required_role"], "amount": ev["amount"],
                        "currency": ev["currency"], "evidence_hash": evidence_hash(ev)}, in_tx=True)
    con.execute("COMMIT")
    return rid


def _refuse(con, actor, action, cid, rid, why):
    ap_store.audit(con, actor, action, cid, {"request_id": rid, "reason": why})
    raise Refused(why)


def approve(con, rid, approver, simulated=True):
    con.execute("BEGIN IMMEDIATE")  # re-check and change under one lock: no double approval race
    req = con.execute("SELECT * FROM approval_requests WHERE request_id = ?", (rid,)).fetchone()
    user = USERS["users"].get(approver)
    why = None
    if req is None:
        why = f"no request {rid}"
    elif approver in USERS["service_identities"]:
        why = f"{approver} is a service identity and cannot approve"
    elif user is None:
        why = f"unknown approver {approver}"
    elif req["status"] != "PENDING":
        why = f"request is {req['status']}, not PENDING"
    elif not req["requester"]:
        why = "PO requester unknown, separation of duties cannot be checked (fail closed)"
    elif approver == req["requester"]:
        why = f"separation of duties: {approver} requested {req['po_number']}"
    elif RANK[user["role"]] < RANK[req["required_role"]]:
        why = f"{approver} is {user['role']}, request needs {req['required_role']} or higher"
    if why:
        con.execute("ROLLBACK")
        _refuse(con, approver, "approval_refused", req["case_id"] if req else None, rid, why)
    con.execute("UPDATE approval_requests SET status = 'APPROVED' WHERE request_id = ?", (rid,))
    con.execute("INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?)",
                (rid, approver, user["role"], req["evidence_hash"], int(simulated), time.time()))
    ap_store.audit(con, approver, "approved", req["case_id"],
                   {"request_id": rid, "role": user["role"], "approved_hash": req["evidence_hash"],
                    "simulated": simulated}, in_tx=True)
    con.execute("COMMIT")


def execute(con, rid, executor=EXECUTOR):
    req = con.execute("SELECT * FROM approval_requests WHERE request_id = ?", (rid,)).fetchone()
    cid = req["case_id"] if req else None
    appr = con.execute("SELECT * FROM approvals WHERE request_id = ?", (rid,)).fetchone()
    why = None
    if executor != EXECUTOR:
        why = f"{executor} may not execute"
    elif req is None:
        why = f"no request {rid}"
    elif req["status"] not in ("APPROVED", "POSTED") or appr is None:
        why = f"request is {req['status']}, not APPROVED"
    elif evidence_hash(json.loads(req["evidence_json"])) != appr["approved_hash"]:
        why = "evidence changed after approval"
    if why:
        _refuse(con, executor, "execution_refused", cid, rid, why)
    ev = json.loads(req["evidence_json"])
    key = idempotency_key(ev["vendor_id"], ev["invoice_number"])
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("INSERT INTO ledger (idempotency_key, request_id, case_id, vendor_id, invoice_number, "
                    "amount, currency, posted_by, posted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (key, rid, cid, ev["vendor_id"], ev["invoice_number"], ev["amount"], ev["currency"],
                     executor, time.time()))
    except sqlite3.IntegrityError:
        con.execute("ROLLBACK")
        first = con.execute("SELECT * FROM ledger WHERE idempotency_key = ?", (key,)).fetchone()
        if first["request_id"] == rid:
            ap_store.audit(con, executor, "replay_blocked", cid, {"request_id": rid, "posting_id": first["posting_id"]})
            return {"status": "already_posted", "posting_id": first["posting_id"]}
        ap_store.audit(con, executor, "duplicate_blocked", cid,
                       {"request_id": rid, "existing_posting": first["posting_id"],
                        "existing_invoice": first["invoice_number"], "posted_by": first["posted_by"]})
        return {"status": "duplicate_blocked", "posting_id": first["posting_id"]}
    pid = con.execute("SELECT posting_id FROM ledger WHERE idempotency_key = ?", (key,)).fetchone()["posting_id"]
    con.execute("UPDATE approval_requests SET status = 'POSTED' WHERE request_id = ?", (rid,))
    ap_store.audit(con, executor, "posted", cid,
                   {"request_id": rid, "posting_id": pid, "amount": ev["amount"], "currency": ev["currency"]}, in_tx=True)
    con.execute("COMMIT")
    return {"status": "posted", "posting_id": pid}


def verify(con, rid, verifier=VERIFIER):
    """Independent read back. Matches by normalized invoice number so a near duplicate posting
    under a different spelling is also counted."""
    req = con.execute("SELECT * FROM approval_requests WHERE request_id = ?", (rid,)).fetchone()
    ev = json.loads(req["evidence_json"])
    want = norm_number(ev["invoice_number"])
    rows = [r for r in con.execute("SELECT * FROM ledger WHERE vendor_id = ?", (ev["vendor_id"],))
            if norm_number(r["invoice_number"]) == want]
    problems = []
    if len(rows) != 1:
        problems.append(f"{len(rows)} postings found for {ev['vendor_id']} {ev['invoice_number']}, expected 1")
    for r in rows:
        if r["request_id"] != rid:
            problems.append(f"posting {r['posting_id']} belongs to {r['request_id'] or r['posted_by']}, not {rid}")
        for k in ("amount", "currency", "vendor_id", "invoice_number"):
            if str(r[k]) != str(ev[k]):
                problems.append(f"posting {r['posting_id']} {k} {r[k]} != approved {ev[k]}")
    status = "OK" if not problems else "MISMATCH"
    ap_store.audit(con, verifier, "verified" if status == "OK" else "verification_alert",
                   req["case_id"], {"request_id": rid, "status": status, "problems": problems})
    return {"status": status, "problems": problems}
