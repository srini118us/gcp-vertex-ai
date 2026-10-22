"""Run the production layer over the final decisions: route, approve (SIMULATED), post, verify.

Input:  results/decisions/agent/<case>.json  (default; INV_ENGINE=baseline uses the rules only)
        results/verified/<case>.json          (verified extraction: vendor, number, amount)
Output: results/ap.db                         (SQLite: requests, approvals, ledger, exceptions, audit)
        results/production_summary.json

Approvals are SIMULATED. A routing table assigns a first approver per required role, the way a
workflow tool would. AP_MANAGER requests go first to r.castillo, who is also a PO requester, so
the separation of duties refusal and the re-route to the next eligible approver show up in a
normal run, not only in tests.

Safe to run twice: submission, approval and posting are all idempotent; a second run reports
replays and posts nothing new. Delete results/ap.db to start over.

Run from the lab folder:
    python scripts/run_production.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ap_store  # noqa: E402
import ap_workflow as wf  # noqa: E402
from common import D  # noqa: E402
from repository import get_repo  # noqa: E402

ROUTING = {"AP_CLERK": ["k.ito", "d.whitfield"], "AP_MANAGER": ["r.castillo", "d.whitfield"],
           "CONTROLLER": ["s.navarro", "m.osei"], "CFO": ["m.osei"]}


def main():
    engine = os.getenv("INV_ENGINE", "agent")
    dec_dir = D("results", "decisions", engine)
    if not os.path.isdir(dec_dir):
        raise SystemExit(f"{dec_dir} not found, run the {engine} step first")
    repo = get_repo()
    con = ap_store.connect()
    seeded = ap_store.seed_history(con, wf.idempotency_key)
    print(f"engine {engine}, data {repo.name}, db {ap_store.DB_PATH}, history rows in ledger {seeded}")
    summary = {"posted": [], "replayed": [], "duplicate_blocked": [], "exceptions": [], "refusals": [],
               "verification": {}, "audit_chain_ok": None}
    for fname in sorted(os.listdir(dec_dir)):
        if not fname.endswith(".json"):
            continue
        decision = json.load(open(os.path.join(dec_dir, fname), encoding="utf-8"))
        cid = decision["case_id"]
        verified = json.load(open(D("results", "verified", f"{cid}.json"), encoding="utf-8"))
        po = verified["fields"]["po_number"]["value"]
        lines = repo.po_lines(po)
        requester = lines[0].get("requester") if lines else None
        rid = wf.submit(con, decision, verified, requester)
        if rid is None:
            summary["exceptions"].append(cid)
            print(f"{cid}: {decision['disposition']} {','.join(decision['reasons'])} -> exception queue, no posting")
            continue
        req = con.execute("SELECT status, required_role FROM approval_requests WHERE request_id = ?", (rid,)).fetchone()
        if req["status"] == "PENDING":
            for approver in ROUTING[req["required_role"]]:
                try:
                    wf.approve(con, rid, approver, simulated=True)
                    print(f"{cid}: approved by {approver} (SIMULATED, needs {req['required_role']})")
                    break
                except wf.Refused as e:
                    summary["refusals"].append(f"{cid}: {e}")
                    print(f"{cid}: approval by {approver} refused: {e}; routing to next approver")
        try:
            res = wf.execute(con, rid)
        except wf.Refused as e:
            summary["refusals"].append(f"{cid}: {e}")
            print(f"{cid}: execution refused: {e}")
            continue
        bucket = {"posted": "posted", "already_posted": "replayed", "duplicate_blocked": "duplicate_blocked"}[res["status"]]
        summary[bucket].append(cid)
        v = wf.verify(con, rid)
        summary["verification"][cid] = v["status"]
        print(f"{cid}: {res['status']} posting {res['posting_id']}, verify {v['status']}"
              + (f" {v['problems']}" if v["problems"] else ""))
    ok, bad = ap_store.verify_audit_chain(con)
    summary["audit_chain_ok"] = ok
    n_audit = con.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    n_post = con.execute("SELECT COUNT(*) FROM ledger WHERE posted_by = ?", (wf.EXECUTOR,)).fetchone()[0]
    print(f"\nposted this run {len(summary['posted'])}, replays {len(summary['replayed'])}, "
          f"duplicates blocked {len(summary['duplicate_blocked'])}, exceptions {len(summary['exceptions'])}, "
          f"refusals {len(summary['refusals'])}")
    print(f"ledger postings by executor {n_post}, audit rows {n_audit}, audit chain "
          f"{'OK' if ok else f'BROKEN at seq {bad}'}")
    with open(D("results", "production_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)


if __name__ == "__main__":
    main()
