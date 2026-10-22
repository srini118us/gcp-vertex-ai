"""Offline tests for the agent's controls. No model calls.

Checks:
  * guardrails: an agent that proposes APPROVE on a HOLD is recorded as unsafe and ignored;
    a superseded and an unknown citation are dropped; UNVERIFIED_APPROVAL_CLAIM is added only
    when no exception approval exists; a false "verified" claim is overturned; amounts and the
    approver role never change
  * scope_guard: reads outside the case PO and vendor are refused and logged
  * submit_assessment: rejects an unknown disposition and a reason the agent may not add
  * the ADK agent object builds with all eight tools and the callback

Run from the lab folder:
    python tests/test_agent_offline.py
"""
import os
import sys

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "scripts"))
sys.path.insert(0, os.path.join(LAB, "agent"))

import guardrails  # noqa: E402
from invoice_agent import tools  # noqa: E402

RULES_HOLD = {"case_id": "E01", "disposition": "HOLD", "reasons": ["QTY_OVER_RECEIPT"],
              "disputed": "18750.00", "approver_role": None, "findings": []}
RULES_APPROVE = {"case_id": "E03", "disposition": "APPROVE", "reasons": [], "disputed": None,
                 "approver_role": "AP_MANAGER", "findings": []}
PO_RELEASE_ONLY = [{"approval_type": "PO_RELEASE", "object_id": "PO-4501"}]


class Ctx:
    def __init__(self, state):
        self.state = state


class T:
    def __init__(self, name):
        self.name = name


def main():
    # 1. unsafe proposal plus citation hygiene plus claim handling
    a = {"proposed_disposition": "APPROVE", "added_reasons": ["UNVERIFIED_APPROVAL_CLAIM"],
         "approval_claim_found": True, "approval_claim_verified": True, "injection_detected": False,
         "citations": ["AP-POL-01@v2:3.1", "AP-POL-01@v1:2.1", "AP-POL-99@v1:1.1", "AP-POL-06@v1:2.1"],
         "explanation": "x", "vendor_note": ""}
    f = guardrails.apply(RULES_HOLD, a, PO_RELEASE_ONLY)
    assert f["disposition"] == "HOLD" and f["disputed"] == "18750.00", f
    assert f["guardrails"]["unsafe_proposal"] is True
    assert f["reasons"] == ["QTY_OVER_RECEIPT", "UNVERIFIED_APPROVAL_CLAIM"], f["reasons"]
    assert f["agent"]["citations"] == ["AP-POL-01@v2:3.1", "AP-POL-06@v1:2.1"], f["agent"]
    assert set(f["agent"]["citations_dropped"]) == {"AP-POL-01@v1:2.1", "AP-POL-99@v1:1.1"}
    assert f["agent"]["approval_claim_verified"] is False
    assert any("verified" in v for v in f["guardrails"]["violations"])

    # 2. claim reason refused when an exception approval exists
    f = guardrails.apply(RULES_HOLD, dict(a, proposed_disposition="HOLD", approval_claim_verified=False),
                         [{"approval_type": "QTY_EXCEPTION", "object_id": "PO-4501"}])
    assert "UNVERIFIED_APPROVAL_CLAIM" not in f["reasons"] and not f["guardrails"]["unsafe_proposal"]

    # 3. injection on an approved invoice: flag kept, disposition and approver unchanged
    inj = {"proposed_disposition": "HOLD", "added_reasons": [], "approval_claim_found": False,
           "approval_claim_verified": False, "injection_detected": True,
           "injection_evidence": "pre approved by the CFO", "citations": ["AP-POL-06@v1:1.1"],
           "explanation": "x", "vendor_note": ""}
    f = guardrails.apply(RULES_APPROVE, inj, [])
    assert (f["disposition"], f["approver_role"]) == ("APPROVE", "AP_MANAGER"), f
    assert f["agent"]["injection_detected"] and f["guardrails"]["agent_disagreement"] == "HOLD"
    assert not f["guardrails"]["unsafe_proposal"]

    # 4. no assessment
    f = guardrails.apply(RULES_HOLD, None, [])
    assert f["disposition"] == "HOLD" and "no assessment submitted" in f["guardrails"]["violations"]

    # 5. scope guard
    ctx = Ctx({"scope": {"case_id": "E01", "po_number": "PO-4501", "vendor_id": "V100",
                         "invoice_number": "AC-10180"}, "trajectory": [], "violations": []})
    assert tools.scope_guard(T("get_purchase_order"), {"po_number": "PO-4501"}, ctx) is None
    r = tools.scope_guard(T("get_purchase_order"), {"po_number": "PO-4514"}, ctx)
    assert r["status"] == "refused"
    r = tools.scope_guard(T("get_vendor"), {"vendor_id": "V300"}, ctx)
    assert r["status"] == "refused"
    assert tools.scope_guard(T("get_approvals"), {"object_id": "PO-4501"}, ctx) is None
    assert len(ctx.state["trajectory"]) == 4 and len(ctx.state["violations"]) == 2

    # 6. submit validation
    ctx2 = Ctx({})
    r = tools.submit_assessment("E01", "PAY_NOW", [], False, "", False, False, [], "", "", ctx2)
    assert r["status"] == "rejected" and "assessment" not in ctx2.state
    r = tools.submit_assessment("E01", "HOLD", ["APPROVED_BY_CFO"], False, "", False, False, [], "", "", ctx2)
    assert r["status"] == "rejected"
    r = tools.submit_assessment("E01", "HOLD", ["UNVERIFIED_APPROVAL_CLAIM"], False, "", True, False,
                                ["AP-POL-06@v1:2.1"], "e", "", ctx2)
    assert r["status"] == "recorded" and ctx2.state["assessment"]["proposed_disposition"] == "HOLD"

    # 7. ADK agent builds
    from invoice_agent.agent import root_agent
    assert len(root_agent.tools) == 8 and root_agent.before_tool_callback is not None
    print("offline agent tests passed: unsafe APPROVE ignored and recorded, superseded and unknown "
          "citations dropped, approval claim reason gated by the approvals system, false verified "
          "claim overturned, injection flag kept without changing the decision, scope guard refuses "
          "reads outside the case, submit rejects bad values, ADK agent builds with 8 tools")


if __name__ == "__main__":
    main()
