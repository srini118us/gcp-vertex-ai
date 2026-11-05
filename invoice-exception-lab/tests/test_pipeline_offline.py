"""Scored evaluation gate for the B1 pipeline consumer. Offline: SQLite stands in for Cloud SQL.

Replays the 20 Calder cases from the frozen key through the real consumer handler (main.py), plus
the same extras the publisher sends: 3 resends, 1 respelled invoice number, 1 poison message, and
a redelivery of an already processed message. Then scores the ledger against the key.

Critical failures (any one fails the gate):
  * a posting for a case the key does not APPROVE          (money paid that should not be)
  * an APPROVE case with no posting                         (supplier not paid)
  * more than one posting for the same invoice               (double payment)
  * a poison or malformed message acknowledged as success    (silent loss)

Run from the lab folder:
    python tests/test_pipeline_offline.py
"""
import base64
import json
import os
import sys

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "pipeline", "consumer"))
os.environ.setdefault("INSTANCE", "offline:test:none")
os.environ.setdefault("DB_USER", "offline-test")

import sqlalchemy  # noqa: E402

import main  # noqa: E402

SCHEMA = [
    "CREATE TABLE processed_events (message_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, outcome TEXT NOT NULL)",
    "CREATE TABLE ledger (posting_id INTEGER PRIMARY KEY AUTOINCREMENT, idempotency_key TEXT NOT NULL UNIQUE,"
    " case_id TEXT NOT NULL, vendor_id TEXT NOT NULL, invoice_number TEXT NOT NULL, amount TEXT NOT NULL,"
    " currency TEXT NOT NULL)",
]


def main_gate():
    key = json.load(open(os.path.join(LAB, "spec", "key.json"), encoding="utf-8"))
    main.engine = sqlalchemy.create_engine("sqlite://", connect_args={"check_same_thread": False},
                                           poolclass=sqlalchemy.pool.StaticPool)
    with main.engine.begin() as c:
        for s in SCHEMA:
            c.exec_driver_sql(s)
    client = main.app.test_client()

    def push(message_id, event):
        data = base64.b64encode(json.dumps(event).encode()).decode()
        return client.post("/", json={"message": {"messageId": message_id, "data": data},
                                      "deliveryAttempt": 1}).status_code

    events = [{"case_id": c, "disposition": v["disposition"], "vendor_id": v["vendor_id"],
               "invoice_number": v["invoice_number"], "amount": v["printed"]["total"],
               "currency": v["printed"]["currency"]} for c, v in sorted(key.items())]
    approved = [e for e in events if e["disposition"] == "APPROVE"]
    extras = [dict(e, case_id=e["case_id"] + "-resend") for e in approved[:3]]
    extras.append(dict(approved[-1], case_id=approved[-1]["case_id"] + "-respelled",
                       invoice_number=approved[-1]["invoice_number"].replace("-", " ")))

    statuses = {}
    for i, e in enumerate(events + extras):
        statuses[e["case_id"]] = push(f"m{i}", e)
    redelivery = push("m0", events[0])
    poison = push("poison", {"case_id": "POISON-1", "disposition": "APPROVE", "simulate_error": True})
    malformed = client.post("/", json={"message": {"messageId": "bad", "data": "not base64 json"}}).status_code

    with main.engine.begin() as c:
        rows = c.exec_driver_sql("SELECT case_id, vendor_id, invoice_number FROM ledger").fetchall()
        outcomes = dict(c.exec_driver_sql("SELECT case_id, outcome FROM processed_events").fetchall())

    posted = {r[0].split("-")[0] for r in rows}
    should_post = {e["case_id"] for e in approved}
    critical = []
    for cid in sorted(posted - should_post):
        critical.append(f"{cid} posted but the key says {key[cid]['disposition']}")
    for cid in sorted(should_post - posted):
        critical.append(f"{cid} approved but not posted")
    seen = {}
    for cid, vid, num in rows:
        k = main.idempotency_key(vid, num)
        if k in seen:
            critical.append(f"double posting: {cid} and {seen[k]}")
        seen[k] = cid
    if poison < 400:
        critical.append(f"poison message acknowledged with {poison}")
    if malformed < 400:
        critical.append(f"malformed message acknowledged with {malformed}")

    checks = [
        ("every message handled with 2xx", all(s < 300 for s in statuses.values())),
        ("postings equal the key's APPROVE cases (6)", posted == should_post and len(rows) == 6),
        ("exceptions queued, no posting (14)", sum(o == "exception_queued" for o in outcomes.values()) == 14),
        ("duplicates blocked (3 resends + 1 respelled)", sum(o == "duplicate_blocked" for o in outcomes.values()) == 4),
        ("redelivered message ignored with 2xx", redelivery < 300),
        ("poison message rejected for retry (5xx)", poison >= 500),
        ("malformed message rejected (4xx)", 400 <= malformed < 500),
    ]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"\ncritical failures: {len(critical)}")
    for c in critical:
        print(f"  CRITICAL  {c}")
    gate = not critical and all(ok for _, ok in checks)
    print(f"GATE {'PASSED' if gate else 'FAILED'}")
    sys.exit(0 if gate else 1)


if __name__ == "__main__":
    main_gate()
