"""Deterministic three way matcher: the rules baseline, and the money fact owner of the workflow.

Input: a verified extraction (results/verified/<case>.json). Output: a decision with findings,
each citing the policy clause it applies:
  disposition    APPROVE, HOLD, REJECT or REQUEST_REVIEW
  reasons        reason codes (PRICE_VARIANCE, QTY_OVER_RECEIPT, ...)
  findings       one record per rule hit: rule, clause, line, detail, amount
  disputed       total disputed amount, when a rule defines one
  approver_role  for APPROVE only, from the approval matrix in USD

Design rules:
  * Written separately from the grading oracle in validate_world.py; both follow the policy.
  * Fail closed: an extraction in REVIEW status, or an unresolved vendor, or an unknown PO,
    gives REQUEST_REVIEW. Set INV_MATCH_ON_REVIEW=proceed only to measure matching accuracy on
    extracted values; the pipeline never runs that way.
  * An exact duplicate is REJECTED and stops evaluation. Every other check runs and all hold
    reasons are collected, so a reviewer sees every problem at once.
  * What this matcher cannot do, by design: read supplier emails, judge an approval claim, or
    notice an instruction injected in invoice text. Those are the agent's job, and the gap is
    measured, not hidden.

Run from the lab folder:
    python scripts/matcher.py                  all verified cases, CSV data
    set INV_DATA=bigquery                      read master data from BigQuery instead
Writes results/decisions/baseline/<case>.json
"""
import json
import os
import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from common import D
from repository import dec, get_repo

ON_REVIEW = os.getenv("INV_MATCH_ON_REVIEW", "defer")
P = json.load(open(D("spec", "policy_params.json"), encoding="utf-8"))
CL = P["clauses"]


def m(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def norm_number(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def val(fields, k):
    return (fields.get(k) or {}).get("value")


def finding(rule, detail, amount=None, line=None, clause=None):
    return {"rule": rule, "clause": clause or CL[rule], "line": line, "detail": detail,
            "amount": str(m(amount)) if amount is not None else None}


def approver_for(total, currency):
    usd = dec(total) * dec(P["fx_to_usd"][currency])
    for limit, role in P["approval_matrix_usd"]:
        if usd <= dec(limit):
            return role, m(usd)
    return P["approval_above_matrix"], m(usd)


def match(ver, repo):
    case = ver.get("case_id")
    f, lines = ver["fields"], ver["lines"]
    out = {"case_id": case, "engine": "rules_baseline", "data_backend": repo.name,
           "extraction_status": ver.get("status"), "findings": []}

    def defer(why):
        out.update(disposition="REQUEST_REVIEW", reasons=[], disputed=None, approver_role=None,
                   defer_reason=why)
        return out

    if ver.get("status") == "REVIEW" and ON_REVIEW != "proceed":
        return defer("extraction needs review: " + "; ".join(ver.get("review_reasons", [])))
    vid = ver.get("vendor_id")
    vendor = repo.vendor(vid) if vid else None
    if not vendor:
        return defer("vendor not resolved against the vendor master")
    po = val(f, "po_number")
    po_lines = {int(r["po_line"]): r for r in repo.po_lines(po)}
    if not po_lines:
        return defer(f"PO {po} not found")
    if any(r["vendor_id"] != vid for r in po_lines.values()):
        return defer(f"PO {po} belongs to a different vendor")

    inv_no, inv_date = val(f, "invoice_number"), val(f, "invoice_date")
    total, subtotal, tax = dec(val(f, "total")), dec(val(f, "subtotal")), dec(val(f, "tax"))
    currency = (val(f, "currency") or "").upper()
    hist = repo.vendor_history(vid)

    # exact duplicate: reject and stop
    for h in hist:
        if norm_number(h["invoice_number"]) == norm_number(inv_no):
            out["findings"].append(finding("DUPLICATE", f"same vendor and normalized number as "
                                                        f"{h['invoice_number']} ({h['status']})"))
            out.update(disposition="REJECT", reasons=["DUPLICATE"], disputed=None, approver_role=None)
            return out

    findings, disputed = [], Decimal("0")
    for h in hist:
        days = (date.fromisoformat(inv_date) - date.fromisoformat(h["invoice_date"])).days
        if m(h["total"]) == m(total) and 0 <= days <= P["duplicate_window_days"]:
            findings.append(finding("DUPLICATE_SUSPECTED",
                                    f"same total {m(total)} as {h['invoice_number']} {days} days earlier"))
    if vendor["status"] == "BLOCKED":
        findings.append(finding("VENDOR_BLOCKED", f"vendor {vid} status BLOCKED"))
    bank = val(f, "bank_account")
    if bank != vendor["bank_account"]:
        findings.append(finding("BANK_CHANGE", f"invoice account {bank} differs from vendor master"))
    po_currency = next(iter(po_lines.values()))["currency"]
    if currency != po_currency:
        findings.append(finding("CURRENCY_MISMATCH", f"invoice {currency}, PO {po_currency}"))
    rate = dec(next(iter(po_lines.values()))["tax_rate"])
    tax_diff = abs(tax - m(subtotal * rate))
    if tax_diff > dec(P["tax_slack"]):
        findings.append(finding("TAX_ERROR", f"tax {tax}, expected {m(subtotal * rate)} at {rate}",
                                amount=tax_diff))
        disputed += tax_diff

    for i, li in enumerate(lines, 1):
        qty = int(dec(li["quantity"]["value"]))
        price = dec(li["unit_price"]["value"])
        amount = dec(li["amount"]["value"])
        code = (li.get("product_code") or {}).get("value")
        # map the invoice line to a PO line by product code, else by position
        pl = next((r for r in po_lines.values() if r["material"] == code), po_lines.get(i))
        if pl is None:
            findings.append(finding("MISSING_GR", f"line {i}: no matching PO line", amount, i,
                                    clause=CL["MISSING_GR"]))
            disputed += amount
            continue
        ln = int(pl["po_line"])
        po_price = dec(pl["unit_price"])
        excess = (price - po_price) * qty
        tol = min(dec(P["price_tolerance_pct"]) * po_price * qty, dec(P["price_tolerance_cap_usd"]))
        if excess > tol:
            findings.append(finding("PRICE_VARIANCE", f"line {ln}: {price} vs PO {po_price}, excess "
                                                      f"{m(excess)} over tolerance {m(tol)}", excess, ln))
            disputed += m(excess)
        rtype = "SES" if pl["category"] == "SERVICE" else "GR"
        received = repo.received(po, ln, rtype)
        if received == 0:
            findings.append(finding("MISSING_GR", f"line {ln}: no {rtype} recorded", amount, ln))
            disputed += amount
            continue
        already = repo.invoiced(po, ln)
        over = already + qty - received
        if over > 0:
            findings.append(finding("QTY_OVER_RECEIPT", f"line {ln}: invoiced {already} + {qty}, "
                                                        f"received {received}", over * price, ln))
            disputed += m(over * price)

    out["findings"] = findings
    if findings:
        reasons = list(dict.fromkeys(fd["rule"] for fd in findings))
        out.update(disposition="HOLD", reasons=reasons,
                   disputed=str(m(disputed)) if disputed else None, approver_role=None)
        return out
    role, usd = approver_for(total, currency)
    out["findings"].append(finding("APPROVAL_MATRIX", f"total {m(total)} {currency} = {usd} USD",
                                   clause=CL["APPROVAL_MATRIX"] + (f", {CL['FX']}" if currency != "USD" else "")))
    out.update(disposition="APPROVE", reasons=[], disputed=None, approver_role=role)
    return out


def main():
    repo = get_repo()
    src = D("results", "verified")
    if not os.path.isdir(src):
        raise SystemExit("no verified extractions, run scripts/verify_extraction.py first")
    dst = D("results", "decisions", "baseline")
    os.makedirs(dst, exist_ok=True)
    files = [fn for fn in sorted(os.listdir(src)) if fn.endswith(".json")]
    modes = sorted({json.load(open(os.path.join(src, fn), encoding="utf-8")).get("mode", "?") for fn in files})
    reviewed = sum(1 for fn in files if "field_review" in json.load(open(os.path.join(src, fn), encoding="utf-8")))
    print(f"data backend {repo.name}, on review: {ON_REVIEW}, verification mode consumed: {modes}, "
          f"human field reviews applied: {reviewed}")
    print(f"{'case':<5} {'decision':<15} reasons / disputed / approver")
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".json"):
            continue
        ver = json.load(open(os.path.join(src, fn), encoding="utf-8"))
        dcs = match(ver, repo)
        with open(os.path.join(dst, fn), "w", encoding="utf-8") as fh:
            json.dump(dcs, fh, indent=1)
        print(f"{dcs['case_id']:<5} {dcs['disposition']:<15} {','.join(dcs['reasons']) or '-'} / "
              f"{dcs['disputed'] or '-'} / {dcs['approver_role'] or '-'}"
              + (f"  ({dcs['defer_reason'][:60]})" if dcs.get("defer_reason") else ""))
    print("next: python scripts/score_decisions.py baseline")


if __name__ == "__main__":
    main()
