"""Offline A2A contract tests.

Replicates the exact extraction the CX agent uses on the Logistics reply, so a
pass here means CX would read the Claude server with no code change. The model
call is monkeypatched out; this tests only the A2A envelope and the Agent Card.
"""
import json

import logistics_claude.a2a_server as srv
from starlette.testclient import TestClient

PAYLOAD = {
    "jsonrpc": "2.0", "id": "req-1", "method": "message/send",
    "params": {"message": {
        "role": "user", "messageId": "m1",
        "parts": [{"kind": "text", "text": "Diagnose delay for order_id=109778"}],
    }},
}


def _cx_extract(result: dict) -> str:
    # copied from cx_agent.agent.diagnose_delay
    texts = [p.get("text", "") for a in result.get("artifacts", [])
             for p in a.get("parts", []) if p.get("kind") == "text"]
    if not texts:
        texts = [p.get("text", "") for p in result.get("parts", [])
                 if p.get("kind") == "text"]
    return "\n".join(texts)


def test_response_matches_cx_parser(monkeypatch):
    monkeypatch.setattr(srv, "diagnose", lambda oid: {
        "order_id": oid,
        "text": "Item 159064 WAREHOUSE_DELAY; item 159065 TRANSIT_DELAY.",
        "result": {}, "guard": {},
    })
    client = TestClient(srv.a2a_app)
    r = client.post("/", json=PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "req-1"
    result = body["result"]
    assert result["status"]["state"] == "completed"
    reply = _cx_extract(result)
    assert "WAREHOUSE_DELAY" in reply and "TRANSIT_DELAY" in reply


def test_missing_order_id_is_rejected(monkeypatch):
    monkeypatch.setattr(srv, "diagnose", lambda oid: {"text": "should not run"})
    client = TestClient(srv.a2a_app)
    bad = dict(PAYLOAD)
    bad["params"] = {"message": {"parts": [{"kind": "text", "text": "no id here"}]}}
    r = client.post("/", json=bad)
    assert r.json()["result"]["status"]["state"] == "rejected"


def test_agent_card_has_no_internal_instructions():
    client = TestClient(srv.a2a_app)
    r = client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    card = r.json()
    blob = json.dumps(card).lower()
    assert "always call" not in blob
    assert "instruction" not in blob
    assert card["skills"] and card["url"]
