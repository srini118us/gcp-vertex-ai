"""Evidence for CX side contract weaknesses. CX is out of scope in Phase 2: these tests pin today's behavior
against the unmodified cx_agent/agent.py, so a future CX fix shows up as a deliberate test change."""
import httpx
import pytest
from cx_agent import agent as cx

FAILED_TASK = {"jsonrpc": "2.0", "id": "1", "result": {
    "kind": "task", "id": "t1", "contextId": "c1",
    "status": {"state": "failed", "message": {"kind": "message", "messageId": "m1", "role": "agent",
               "parts": [{"kind": "text", "text": "ACCESS_DENIED: logistics data access denied"}]}}}}
RPC_ERROR = {"jsonrpc": "2.0", "id": "1", "error": {"code": -32603, "message": "Internal error"}}

@pytest.fixture
def a2a_reply(monkeypatch):
    def set_reply(body):
        req = httpx.Request("POST", "http://logistics.test/")
        monkeypatch.setattr(cx, "_auth_header", lambda: {})
        monkeypatch.setattr(cx.httpx, "post", lambda *a, **k: httpx.Response(200, json=body, request=req))
    return set_reply

def test_weakness_failed_task_is_returned_as_data_and_reason_is_dropped(a2a_reply):
    a2a_reply(FAILED_TASK)
    assert cx.diagnose_delay(109778) == {"order_id": 109778, "a2a_state": "failed", "logistics_reply": ""}

def test_weakness_jsonrpc_error_is_silent(a2a_reply):
    a2a_reply(RPC_ERROR)
    assert cx.diagnose_delay(109778) == {"order_id": 109778, "a2a_state": None, "logistics_reply": ""}

def test_weakness_credit_write_does_not_depend_on_a_diagnosis(monkeypatch):
    """issue_store_credit trusts model supplied causes; nothing ties them to a completed, verified diagnosis.
    After a failed diagnosis, a model that supplies codes anyway gets a credit written (here 15%, auto approved)."""
    writes = []
    class FakeBQ:
        def query(self, sql, job_config=None):
            writes.append(sql)
            return type("Job", (), {"result": lambda self: []})()
    monkeypatch.setattr(cx, "_already_issued", lambda order_id: False)
    monkeypatch.setattr(cx, "get_order_status", lambda order_id: {"days_late": 3})
    monkeypatch.setattr(cx, "_client", lambda: FakeBQ())
    assert cx.needs_approval(109778, ["WAREHOUSE_DELAY"]) is False
    assert cx.issue_store_credit(109778, ["WAREHOUSE_DELAY"]) == {"issued": True, "credit_pct": 15, "driver": "WAREHOUSE_DELAY"}
    assert len(writes) == 1 and writes[0].lstrip().startswith("INSERT")

def test_unknown_codes_are_rejected_by_policy():
    assert "error" in cx.propose_compensation(["warehouse lag"], 3)
    assert "error" in cx.propose_compensation(["ORDER_NOT_FOUND"], 3)
