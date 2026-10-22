"""Guardrails between the agent's assessment and the final decision. Deterministic, no model.

What the agent CAN change:
  * add UNVERIFIED_APPROVAL_CLAIM, but only if code confirms there is no matching exception
    approval in the approvals system (AP-POL-06@v1:2.1). It never changes the disposition.
  * attach an injection flag, an explanation, valid citations and a vendor note for the approver.

What the agent can NOT change, whatever it submits:
  * the disposition, the disputed amount, the approver role. These stay exactly as the rules
    engine decided. A different proposal is recorded as a disagreement for the human; a proposal
    to APPROVE something the rules held, rejected or deferred is recorded as an UNSAFE proposal.
  * citations: unknown clause ids and SUPERSEDED clauses are removed and counted as violations.
  * a claim that an approval was verified, when no record exists, is overturned and counted.
"""
import copy

import policy_store

EXCEPTION_APPROVAL_TYPES = {"QTY_EXCEPTION", "PRICE_EXCEPTION", "INVOICE_EXCEPTION"}


def apply(rules, assessment, approvals_rows, scope_violations=()):
    final = copy.deepcopy({k: rules.get(k) for k in ("case_id", "disposition", "reasons",
                                                     "disputed", "approver_role", "findings")})
    final["engine"] = "rules_plus_agent"
    violations = list(scope_violations)
    notes = []
    if not assessment:
        final.update(agent=None, guardrails={"violations": violations + ["no assessment submitted"],
                                             "notes": notes, "agent_disagreement": None,
                                             "unsafe_proposal": False})
        return final

    proposed = assessment.get("proposed_disposition")
    disagreement = proposed if proposed != rules["disposition"] else None
    unsafe = proposed == "APPROVE" and rules["disposition"] != "APPROVE"
    if unsafe:
        violations.append(f"UNSAFE proposal: agent proposed APPROVE, rules decided {rules['disposition']}")

    has_exception_approval = any(r.get("approval_type") in EXCEPTION_APPROVAL_TYPES for r in approvals_rows)
    claim_verified = bool(assessment.get("approval_claim_verified"))
    if claim_verified and not has_exception_approval:
        violations.append("agent reported an approval claim as verified, but no exception approval exists")
        claim_verified = False
    for reason in assessment.get("added_reasons", []):
        if reason == "UNVERIFIED_APPROVAL_CLAIM":
            if has_exception_approval:
                violations.append("UNVERIFIED_APPROVAL_CLAIM rejected: an exception approval exists")
            elif not assessment.get("approval_claim_found"):
                violations.append("UNVERIFIED_APPROVAL_CLAIM rejected: agent reported no claim found")
            elif reason not in final["reasons"]:
                final["reasons"].append(reason)
                notes.append("added UNVERIFIED_APPROVAL_CLAIM (no exception approval on record); "
                             "outcome unchanged per AP-POL-06@v1:2.1")

    valid, dropped = [], []
    for c in assessment.get("citations", []):
        info = policy_store.clause(c)
        if not info["found"]:
            dropped.append(c)
            violations.append(f"citation {c} does not exist")
        elif info["status"] != "CURRENT":
            dropped.append(c)
            violations.append(f"citation {c} is SUPERSEDED")
        elif c not in valid:
            valid.append(c)

    final["agent"] = {
        "proposed_disposition": proposed, "injection_detected": bool(assessment.get("injection_detected")),
        "injection_evidence": assessment.get("injection_evidence", ""),
        "approval_claim_found": bool(assessment.get("approval_claim_found")),
        "approval_claim_verified": claim_verified, "citations": valid, "citations_dropped": dropped,
        "explanation": assessment.get("explanation", ""), "vendor_note": assessment.get("vendor_note", "")}
    final["guardrails"] = {"violations": violations, "notes": notes,
                           "agent_disagreement": disagreement, "unsafe_proposal": unsafe}
    return final
