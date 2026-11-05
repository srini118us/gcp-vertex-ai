"""Pub/Sub push consumer: records each invoice event once and posts approved invoices once.

Two idempotency layers, both enforced by the database, not by this code:
  processed_events.message_id  PRIMARY KEY   a redelivered Pub/Sub message is ignored
  ledger.idempotency_key       UNIQUE        the same invoice arriving as a new message never posts twice
Return 2xx = acknowledge (done). Return 5xx = Pub/Sub retries, then dead letters after max attempts.
Logs in to Cloud SQL as its own service account (IAM database authentication, no password).
"""
import base64
import hashlib
import json
import logging
import os
import re

import sqlalchemy
from flask import Flask, request
from google.cloud.sql.connector import Connector, IPTypes

INSTANCE = os.environ["INSTANCE"]   # project:region:instance
DB_USER = os.environ["DB_USER"]     # ap-consumer@<project>.iam
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")
_connector = None


def _getconn():
    global _connector
    if _connector is None:  # created on first use, so the module imports without credentials
        _connector = Connector(refresh_strategy="lazy")
    return _connector.connect(INSTANCE, "pg8000", user=DB_USER, db="ap",
                              enable_iam_auth=True, ip_type=IPTypes.PUBLIC)


engine = sqlalchemy.create_engine("postgresql+pg8000://", creator=_getconn, pool_size=2, max_overflow=0)


def idempotency_key(vendor_id, invoice_number):
    """Same rule as the capstone (ADR-003): 'AC 10077' and 'AC-10077' are one invoice."""
    norm = re.sub(r"[^A-Z0-9]", "", invoice_number.upper())
    return hashlib.sha256(f"{vendor_id}|{norm}".encode()).hexdigest()


def log(**fields):
    logging.info(json.dumps(fields))  # one JSON line per event; Cloud Logging parses it


@app.post("/")
def handle():
    envelope = request.get_json(silent=True) or {}
    msg = envelope.get("message", {})
    message_id = msg.get("messageId")
    attempt = envelope.get("deliveryAttempt")
    try:
        event = json.loads(base64.b64decode(msg.get("data", "")))
        case_id = event["case_id"]
    except Exception:
        log(outcome="malformed", message_id=message_id, attempt=attempt)
        return ("malformed message", 400)   # 4xx is still a failure: retried, then dead lettered

    if event.get("simulate_error"):        # test hook for the dead letter path
        log(outcome="simulated_error", case_id=case_id, message_id=message_id, attempt=attempt)
        return ("simulated failure", 500)

    with engine.begin() as conn:           # one transaction: both inserts commit together or not at all
        first = conn.execute(sqlalchemy.text(
            "INSERT INTO processed_events (message_id, case_id, outcome) VALUES (:m, :c, 'pending') "
            "ON CONFLICT (message_id) DO NOTHING RETURNING message_id"),
            {"m": message_id, "c": case_id}).first()
        if first is None:
            log(outcome="redelivery_ignored", case_id=case_id, message_id=message_id, attempt=attempt)
            return ("", 204)

        if event["disposition"] != "APPROVE":
            outcome, posting_id = "exception_queued", None
        else:
            row = conn.execute(sqlalchemy.text(
                "INSERT INTO ledger (idempotency_key, case_id, vendor_id, invoice_number, amount, currency) "
                "VALUES (:k, :c, :v, :n, :a, :cur) ON CONFLICT (idempotency_key) DO NOTHING RETURNING posting_id"),
                {"k": idempotency_key(event["vendor_id"], event["invoice_number"]), "c": case_id,
                 "v": event["vendor_id"], "n": event["invoice_number"], "a": event["amount"],
                 "cur": event["currency"]}).first()
            outcome, posting_id = ("posted", row[0]) if row else ("duplicate_blocked", None)

        conn.execute(sqlalchemy.text("UPDATE processed_events SET outcome = :o WHERE message_id = :m"),
                     {"o": outcome, "m": message_id})
    log(outcome=outcome, case_id=case_id, message_id=message_id, attempt=attempt, posting_id=posting_id)
    return ("", 204)
