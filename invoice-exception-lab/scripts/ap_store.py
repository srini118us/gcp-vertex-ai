"""Transactional store for the production layer: approval requests, approvals, the ERP ledger
(simulated), the exception queue, and a hash chained audit log.

Lab: SQLite file results/ap.db. Production: Cloud SQL for PostgreSQL (adr/ADR-002). The schema
uses only portable features: primary keys, UNIQUE constraints and transactions.

Idempotency rests on the UNIQUE constraint on ledger.idempotency_key. The database enforces it,
not application code, so two executors racing on the same invoice cannot both post. The ledger is
seeded with the invoice history (already posted or paid invoices), so the same constraint also
stops a duplicate that the rules engine missed: a second line of defense.

Audit log: append only; each row stores the hash of the previous row (a hash chain). Editing or
deleting a past row breaks the chain, and verify_audit_chain() returns where. Actions that change
state write their audit row in the same transaction as the change, so a state change without an
audit row cannot happen. In production the table would also be write only for the app identity
(INSERT granted, UPDATE and DELETE revoked) and exported to a locked bucket.
"""
import csv
import hashlib
import json
import os
import sqlite3
import time

from common import D

DB_PATH = os.getenv("INV_AP_DB", D("results", "ap.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS approval_requests (
  request_id TEXT PRIMARY KEY, case_id TEXT NOT NULL UNIQUE, vendor_id TEXT NOT NULL,
  invoice_number TEXT NOT NULL, po_number TEXT NOT NULL, requester TEXT,
  amount TEXT NOT NULL, currency TEXT NOT NULL, required_role TEXT NOT NULL,
  evidence_hash TEXT NOT NULL, evidence_json TEXT NOT NULL,
  status TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS approvals (
  request_id TEXT NOT NULL, approver TEXT NOT NULL, approver_role TEXT NOT NULL,
  approved_hash TEXT NOT NULL, simulated INTEGER NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS ledger (
  posting_id INTEGER PRIMARY KEY AUTOINCREMENT, idempotency_key TEXT NOT NULL UNIQUE,
  request_id TEXT, case_id TEXT, vendor_id TEXT NOT NULL, invoice_number TEXT NOT NULL,
  amount TEXT NOT NULL, currency TEXT NOT NULL, posted_by TEXT NOT NULL, posted_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS exceptions (
  case_id TEXT PRIMARY KEY, disposition TEXT NOT NULL, reasons TEXT NOT NULL,
  disputed TEXT, summary TEXT, status TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, actor TEXT NOT NULL,
  action TEXT NOT NULL, case_id TEXT, detail TEXT NOT NULL, prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL);
"""


def connect(path=None):
    path = path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path, timeout=30, isolation_level=None)  # explicit transactions only
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def seed_history(con, key_fn):
    """Load already posted or paid invoices into the ledger (idempotent)."""
    with open(D("data", "invoice_history.csv"), encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        con.execute("INSERT OR IGNORE INTO ledger (idempotency_key, vendor_id, invoice_number, amount, "
                    "currency, posted_by, posted_at) VALUES (?, ?, ?, ?, 'USD', 'legacy_history', ?)",
                    (key_fn(r["vendor_id"], r["invoice_number"]), r["vendor_id"], r["invoice_number"],
                     r["total"], time.time()))
    return len(rows)


def _row_hash(prev, at, actor, action, case_id, detail):
    payload = json.dumps([prev, repr(at), actor, action, case_id, detail])
    return hashlib.sha256(payload.encode()).hexdigest()


def audit(con, actor, action, case_id, detail, in_tx=False):
    """Append one audit row. in_tx=True: the caller already holds a write transaction and the
    row commits or rolls back with the caller's change."""
    detail_s = json.dumps(detail, sort_keys=True, default=str)
    if not in_tx:
        con.execute("BEGIN IMMEDIATE")
    try:
        last = con.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else "GENESIS"
        at = time.time()
        con.execute("INSERT INTO audit (at, actor, action, case_id, detail, prev_hash, hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (at, actor, action, case_id, detail_s, prev, _row_hash(prev, at, actor, action, case_id, detail_s)))
        if not in_tx:
            con.execute("COMMIT")
    except Exception:
        if not in_tx:
            con.execute("ROLLBACK")
        raise


def verify_audit_chain(con):
    """Returns (ok, first_bad_seq or None). Detects edited rows, deleted rows and reordering."""
    prev = "GENESIS"
    for r in con.execute("SELECT * FROM audit ORDER BY seq"):
        if r["prev_hash"] != prev or _row_hash(prev, r["at"], r["actor"], r["action"],
                                               r["case_id"], r["detail"]) != r["hash"]:
            return False, r["seq"]
        prev = r["hash"]
    return True, None
