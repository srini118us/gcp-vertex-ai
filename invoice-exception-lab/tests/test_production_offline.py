"""Adversarial offline tests for the production layer. No cloud, no model. Each test uses its own
temporary SQLite file.

Checks:
  * happy path: approve, post, verify OK
  * replay of the same request returns the first posting; a concurrent race posts exactly once
  * duplicate defense in depth: a planted APPROVE for R07 (AC 10077, already posted as AC-10077)
    is blocked by the ledger constraint, not by the rules
  * approval refused for: a lower role, the PO requester (separation of duties), a service
    identity, an unknown user, an unknown requester; a request cannot be approved twice
  * execution refused for: a non executor identity, an unapproved request, evidence changed
    after approval
  * HOLD and REJECT go to the exception queue and can never be posted
  * the verifier raises MISMATCH for a planted extra posting and for an altered amount
  * the audit chain detects an edited row and a deleted row; refusals are audited too
  * submission is idempotent

Run from the lab folder:
    python tests/test_production_offline.py
"""
import json
import os
import sys
import tempfile
import threading

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "scripts"))

import ap_store  # noqa: E402
import ap_workflow as wf  # noqa: E402

KEY = json.load(open(os.path.join(LAB, "spec", "key.json"), encoding="utf-8"))
REQUESTER = {"PO-4502": "m.lindqvist", "PO-4503": "j.okafor", "PO-4504": "r.castillo",
             "PO-4511": "j.okafor", "PO-4501": "j.okafor"}
results = []


def check(name, cond, detail=""):
    cond = bool(cond)
    results.append(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not cond else ""))


def fixture(cid, disposition=None, role=None):
    k = KEY[cid]
    decision = {"case_id": cid, "disposition": disposition or k["disposition"], "reasons": k["reasons"],
                "disputed": k["disputed"], "approver_role": role or k["approver_role"], "findings": [],
                "agent": None}
    verified = {"vendor_id": k["vendor_id"], "fields": {
        "invoice_number": {"value": k["invoice_number"]}, "po_number": {"value": k["po_number"]},
        "total": {"value": k["printed"]["total"]}, "currency": {"value": k["printed"]["currency"]}}}
    return decision, verified, REQUESTER.get(k["po_number"])


def fresh_db():
    path = os.path.join(tempfile.mkdtemp(prefix="ap_test_"), "ap.db")
    con = ap_store.connect(path)
    ap_store.seed_history(con, wf.idempotency_key)
    return con, path


def refused(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except wf.Refused as e:
        return str(e)


def executor_postings(con):
    return con.execute("SELECT COUNT(*) FROM ledger WHERE posted_by = ?", (wf.EXECUTOR,)).fetchone()[0]


def main():
    # happy path and replay
    con, _ = fresh_db()
    rid = wf.submit(con, *fixture("R01"))
    wf.approve(con, rid, "k.ito")
    r1 = wf.execute(con, rid)
    check("R01 posts after a valid approval", r1["status"] == "posted")
    check("verifier reads back OK", wf.verify(con, rid)["status"] == "OK")
    r2 = wf.execute(con, rid)
    check("replay returns the first posting, no second posting",
          r2["status"] == "already_posted" and r2["posting_id"] == r1["posting_id"] and executor_postings(con) == 1)
    check("submitting the same case again changes nothing",
          wf.submit(con, *fixture("R01")) == rid
          and con.execute("SELECT status FROM approval_requests WHERE request_id = ?", (rid,)).fetchone()[0] == "POSTED")

    # concurrent race: two executors, two connections, same request
    con, path = fresh_db()
    rid = wf.submit(con, *fixture("R01"))
    wf.approve(con, rid, "k.ito")
    barrier, outcomes = threading.Barrier(2), []

    def worker():
        c = ap_store.connect(path)
        barrier.wait()
        outcomes.append(wf.execute(c, rid)["status"])

    ts = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    check("concurrent executors post exactly once", sorted(outcomes) == ["already_posted", "posted"]
          and executor_postings(con) == 1, str(outcomes))

    # duplicate that the rules would have caught, planted as APPROVE
    con, _ = fresh_db()
    rid = wf.submit(con, *fixture("R07", disposition="APPROVE", role="AP_CLERK"))
    wf.approve(con, rid, "k.ito")
    r = wf.execute(con, rid)
    v = wf.verify(con, rid)
    check("planted APPROVE of duplicate 'AC 10077' blocked by the ledger key",
          r["status"] == "duplicate_blocked" and executor_postings(con) == 0, str(r))
    check("verifier flags the duplicate request as MISMATCH", v["status"] == "MISMATCH")

    # approval refusals
    con, _ = fresh_db()
    r02 = wf.submit(con, *fixture("R02"))   # needs CONTROLLER
    r03 = wf.submit(con, *fixture("R03"))   # needs AP_MANAGER, PO requested by r.castillo
    why = refused(wf.approve, con, r02, "d.whitfield")
    check("AP_MANAGER cannot approve a CONTROLLER request", why and "needs CONTROLLER" in why, why)
    why = refused(wf.approve, con, r03, "r.castillo")
    check("PO requester cannot approve (separation of duties)", why and "separation of duties" in why, why)
    for ident in ("svc-ap-agent", "svc-ap-executor"):
        why = refused(wf.approve, con, r03, ident)
        check(f"service identity {ident} cannot approve", why and "service identity" in why, why)
    why = refused(wf.approve, con, r03, "mallory")
    check("unknown user cannot approve", why and "unknown approver" in why, why)
    check("refused requests stay PENDING",
          {r[0] for r in con.execute("SELECT status FROM approval_requests")} == {"PENDING"})
    wf.approve(con, r03, "d.whitfield")
    why = refused(wf.approve, con, r03, "s.navarro")
    check("a request cannot be approved twice", why and "not PENDING" in why, why)
    d, ver, _ = fixture("R01")
    rq = wf.submit(con, d, ver, None)
    why = refused(wf.approve, con, rq, "k.ito")
    check("unknown PO requester fails closed", why and "fail closed" in why, why)

    # execution refusals
    why = refused(wf.execute, con, r02)
    check("unapproved request cannot be executed", why and "not APPROVED" in why, why)
    why = refused(wf.execute, con, r03, executor="svc-ap-agent")
    check("the agent identity cannot execute", why and "may not execute" in why, why)
    ev = json.loads(con.execute("SELECT evidence_json FROM approval_requests WHERE request_id = ?", (r03,)).fetchone()[0])
    ev["amount"] = "99999.00"
    con.execute("UPDATE approval_requests SET evidence_json = ? WHERE request_id = ?", (json.dumps(ev, sort_keys=True), r03))
    why = refused(wf.execute, con, r03)
    check("evidence changed after approval blocks posting", why and "changed after approval" in why
          and executor_postings(con) == 0, why)

    # HOLD and REJECT never post
    con, _ = fresh_db()
    check("HOLD goes to the exception queue", wf.submit(con, *fixture("E01")) is None)
    check("REJECT goes to the exception queue", wf.submit(con, *fixture("R07")) is None)
    why = refused(wf.execute, con, "REQ-E01")
    check("a HOLD case has no request to execute", why and "no request" in why, why)
    check("exception queue holds both, ledger has no executor postings",
          con.execute("SELECT COUNT(*) FROM exceptions").fetchone()[0] == 2 and executor_postings(con) == 0)

    # verifier catches planted and altered postings
    con, _ = fresh_db()
    rid = wf.submit(con, *fixture("R01"))
    wf.approve(con, rid, "k.ito")
    wf.execute(con, rid)
    check("clean posting verifies OK", wf.verify(con, rid)["status"] == "OK")
    con.execute("INSERT INTO ledger (idempotency_key, vendor_id, invoice_number, amount, currency, posted_by, "
                "posted_at) VALUES ('planted', 'V600', 'FW 3388', '1466.97', 'USD', 'unknown', 0)")
    v = wf.verify(con, rid)
    check("planted second posting under another spelling raises MISMATCH",
          v["status"] == "MISMATCH" and any("2 postings" in p for p in v["problems"]), str(v))
    con.execute("DELETE FROM ledger WHERE idempotency_key = 'planted'")
    con.execute("UPDATE ledger SET amount = '1566.97' WHERE request_id = ?", (rid,))
    v = wf.verify(con, rid)
    check("altered posted amount raises MISMATCH", v["status"] == "MISMATCH"
          and any("amount" in p for p in v["problems"]), str(v))

    # audit chain
    actions = [r[0] for r in con.execute("SELECT action FROM audit ORDER BY seq")]
    check("audit has the full trail including alerts",
          {"approval_requested", "approved", "posted", "verified", "verification_alert"} <= set(actions), str(actions))
    ok, _ = ap_store.verify_audit_chain(con)
    check("audit chain verifies before tampering", ok)
    con.execute("UPDATE audit SET detail = '{\"amount\": \"1.00\"}' WHERE seq = 3")
    ok, bad = ap_store.verify_audit_chain(con)
    check("edited audit row is detected", not ok and bad == 3, f"ok={ok} bad={bad}")
    con2, _ = fresh_db()
    rid = wf.submit(con2, *fixture("R01"))
    refused(wf.approve, con2, rid, "svc-ap-agent")
    wf.approve(con2, rid, "k.ito")
    check("refusals are audited", con2.execute(
        "SELECT COUNT(*) FROM audit WHERE action = 'approval_refused'").fetchone()[0] == 1)
    con2.execute("DELETE FROM audit WHERE seq = 2")
    ok, bad = ap_store.verify_audit_chain(con2)
    check("deleted audit row is detected", not ok and bad == 3, f"ok={ok} bad={bad}")

    print(f"\n{sum(results)} of {len(results)} checks passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
