"""Publish the 20 Calder cases to invoice-events, plus deliberate duplicates and one poison message.

Reads the capstone's own outputs, so the events carry the decisions already scored against the key:
  results/decisions/agent/<case>.json   disposition (rules decide, guardrails applied)
  results/verified/<case>.json          vendor, invoice number, total, currency
Extras, to prove the pipeline controls:
  three APPROVE cases published twice (supplier resend)       -> duplicate_blocked
  one approved case under another spelling of its number      -> duplicate_blocked (business key)
  one poison message (simulate_error)                          -> 5 attempts, then the dead letter topic

Run from the lab folder, after: pip install google-cloud-pubsub
    python pipeline/publish_cases.py            prints the plan and asks before publishing
Writes results/pipeline_expected.json (what the ledger must contain afterwards).
"""
import json
import os
import sys

from google.cloud import pubsub_v1

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT, TOPIC = "geap-ai-usecases-494501", "invoice-events"


def load(*parts):
    with open(os.path.join(LAB, *parts), encoding="utf-8") as fh:
        return json.load(fh)


def events():
    out = []
    for f in sorted(os.listdir(os.path.join(LAB, "results", "decisions", "agent"))):
        cid = f[:-5]
        d, v = load("results", "decisions", "agent", f), load("results", "verified", f)
        fl = v["fields"]
        out.append({"case_id": cid, "disposition": d["disposition"], "vendor_id": v["vendor_id"],
                    "invoice_number": fl["invoice_number"]["value"], "amount": fl["total"]["value"],
                    "currency": fl["currency"]["value"]})
    return out


def main():
    base = events()
    approved = [e for e in base if e["disposition"] == "APPROVE"]
    extras = [dict(e, case_id=e["case_id"] + "-resend") for e in approved[:3]]
    if approved:
        e = approved[-1]
        extras.append(dict(e, case_id=e["case_id"] + "-respelled",
                           invoice_number=e["invoice_number"].replace("-", " ")))
    extras.append({"case_id": "POISON-1", "disposition": "APPROVE", "simulate_error": True})
    plan = base + extras
    expected = {"postings": sorted(e["case_id"] for e in approved),
                "duplicates_blocked": sorted(e["case_id"] for e in extras if e["case_id"] != "POISON-1"),
                "exceptions": sorted(e["case_id"] for e in base if e["disposition"] != "APPROVE"),
                "dead_lettered": ["POISON-1"]}
    print(f"cases {len(base)} (approve {len(approved)}, exceptions {len(base) - len(approved)}), "
          f"extras {len(extras)}, total messages {len(plan)}")
    for k, v in expected.items():
        print(f"  expected {k}: {v}")
    if input("publish? (yes/no) ").strip() != "yes":
        sys.exit("nothing published")
    with open(os.path.join(LAB, "results", "pipeline_expected.json"), "w", encoding="utf-8") as fh:
        json.dump(expected, fh, indent=1)
    pub = pubsub_v1.PublisherClient()
    path = pub.topic_path(PROJECT, TOPIC)
    for e in plan:
        mid = pub.publish(path, json.dumps(e).encode(), case_id=e["case_id"]).result()
        print(f"  {e['case_id']:<14} {e.get('disposition', ''):<15} message {mid}")


if __name__ == "__main__":
    main()
