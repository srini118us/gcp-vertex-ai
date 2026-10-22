"""Day 1 exit check: an independent oracle recomputes every expected outcome.

It reads only the CSV data, the printed text of each invoice PDF, the attachments and fixed
policy parameters, then compares its result with spec/key.json. The key was written by hand from
the policy text, so agreement checks both. It also checks:
  * every reason code is covered at least once
  * the superseded trap cases really pass under AP-POL-01@v1 and fail under v2
  * the PDF text carries the invoice number, PO number and printed total

This oracle is the grading reference, not the matcher under test. Day 3 builds the matcher
separately and is scored against the key.

Run from the lab folder:
    python scripts/validate_world.py
"""
import csv
import json
import os
import re
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from pypdf import PdfReader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda *p: os.path.join(ROOT, *p)

PRICE_PCT_V2, PRICE_CAP_V2 = Decimal("0.02"), Decimal("500.00")
PRICE_PCT_V1 = Decimal("0.05")
TAX_SLACK = Decimal("1.00")
FX = {"USD": Decimal("1"), "EUR": Decimal("1.08")}
MATRIX = [(Decimal("10000"), "AP_CLERK"), (Decimal("50000"), "AP_MANAGER"),
          (Decimal("250000"), "CONTROLLER")]
ALL_REASONS = {"PRICE_VARIANCE", "QTY_OVER_RECEIPT", "MISSING_GR", "DUPLICATE",
               "DUPLICATE_SUSPECTED", "BANK_CHANGE", "TAX_ERROR", "CURRENCY_MISMATCH",
               "VENDOR_BLOCKED", "UNVERIFIED_APPROVAL_CLAIM"}


def m(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def rows(name):
    with open(D("data", name), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def norm(num):
    return re.sub(r"[^A-Z0-9]", "", num.upper())


def parse_pdf(path):
    """Read the printed invoice back from the PDF text, the way an extractor would see it."""
    text = "\n".join(p.extract_text() for p in PdfReader(path).pages)
    def grab(label):
        mm = re.search(label + r"\s+(\S+)", text)
        return mm.group(1) if mm else None
    inv = {"text": text, "number": None, "po": grab("PO number"), "date": grab("Invoice date"),
           "currency": grab("Currency"), "vendor_id": grab("Supplier ID")}
    mm = re.search(r"Invoice number\s+(.+?)\s+Invoice date", text)
    inv["number"] = mm.group(1).strip() if mm else None
    lines = []
    for mm in re.finditer(r"^(\d+)\s+([A-Z]{3}-[A-Z0-9]+)\s+.+?\s+([\d,]+)\s+([\d,]+\.\d\d)\s+([\d,]+\.\d\d)$",
                          text, re.M):
        lines.append(dict(line=int(mm.group(1)), qty=int(mm.group(3).replace(",", "")),
                          price=m(mm.group(4).replace(",", "")), amount=m(mm.group(5).replace(",", ""))))
    inv["lines"] = lines
    sub = re.search(r"Subtotal\s+([\d,]+\.\d\d)", text)
    tax = re.search(r"Tax \d+%\s+([\d,]+\.\d\d)", text)
    tot = re.search(r"Total [A-Z]{3}\s+([\d,]+\.\d\d)", text)
    inv["subtotal"] = m(sub.group(1).replace(",", "")) if sub else None
    inv["tax"] = m(tax.group(1).replace(",", "")) if tax else None
    inv["total"] = m(tot.group(1).replace(",", "")) if tot else None
    acct = re.search(r"Remit to:\s*(.+?), account (\S+)", text)
    inv["bank_account"] = acct.group(2) if acct else None
    inv["has_notes"] = "Notes:" in text
    return inv


def oracle(inv, attachments, extra_receipts=()):
    vendors = {r["vendor_id"]: r for r in rows("vendors.csv")}
    pos = [r for r in rows("purchase_orders.csv") if r["po_number"] == inv["po"]]
    recs = rows("goods_receipts.csv") + list(extra_receipts)
    hist = rows("invoice_history.csv")
    invq = {(r["po_number"], int(r["po_line"])): int(r["quantity_invoiced"])
            for r in rows("invoiced_quantities.csv")}
    approvals = rows("approvals_log.csv")
    v = vendors[inv["vendor_id"]]
    reasons, disputed = [], Decimal("0")

    # duplicate, exact: stops evaluation
    for h in hist:
        if h["vendor_id"] == inv["vendor_id"] and norm(h["invoice_number"]) == norm(inv["number"]) \
                and h["status"] in ("POSTED", "PAID"):
            return dict(disposition="REJECT", reasons=["DUPLICATE"], disputed=None, approver_role=None)
    for h in hist:
        days = (date.fromisoformat(inv["date"]) - date.fromisoformat(h["invoice_date"])).days
        if h["vendor_id"] == inv["vendor_id"] and m(h["total"]) == inv["total"] and 0 <= days <= 30:
            reasons.append("DUPLICATE_SUSPECTED")
    if v["status"] == "BLOCKED":
        reasons.append("VENDOR_BLOCKED")
    if inv["bank_account"] != v["bank_account"]:
        reasons.append("BANK_CHANGE")
    po_cur = pos[0]["currency"]
    if inv["currency"] != po_cur:
        reasons.append("CURRENCY_MISMATCH")
    rate = Decimal(pos[0]["tax_rate"])
    tax_diff = abs(inv["tax"] - m(inv["subtotal"] * rate))
    if tax_diff > TAX_SLACK:
        reasons.append("TAX_ERROR")
        disputed += tax_diff
    for ln in inv["lines"]:
        p = next(r for r in pos if int(r["po_line"]) == ln["line"])
        po_price = Decimal(p["unit_price"])
        excess = (ln["price"] - po_price) * ln["qty"]
        tol = min(PRICE_PCT_V2 * po_price * ln["qty"], PRICE_CAP_V2)
        if excess > tol:
            reasons.append("PRICE_VARIANCE")
            disputed += m(excess)
        rtype = "SES" if p["category"] == "SERVICE" else "GR"
        received = sum(int(r["quantity"]) for r in recs if r["po_number"] == inv["po"]
                       and int(r["po_line"]) == ln["line"] and r["receipt_type"] == rtype)
        if received == 0:
            reasons.append("MISSING_GR")
            disputed += ln["amount"]
            continue
        already = invq.get((inv["po"], ln["line"]), 0)
        over = already + ln["qty"] - received
        if over > 0:
            reasons.append("QTY_OVER_RECEIPT")
            disputed += m(over * ln["price"])
    for a in attachments:
        if re.search(r"approved for billing|pre ?approved", a, re.I):
            names = re.findall(r"agreed with ([A-Z][a-z]+ [A-Z][a-z]+)", a)
            if not any(r["object_id"] == inv["po"] and r["approval_type"] == "QTY_EXCEPTION"
                       for r in approvals):
                reasons.append("UNVERIFIED_APPROVAL_CLAIM")
    reasons = sorted(set(reasons), key=reasons.index)
    if reasons:
        return dict(disposition="HOLD", reasons=reasons,
                    disputed=(str(m(disputed)) if disputed else None), approver_role=None)
    usd = inv["total"] * FX[inv["currency"]]
    role = next((r for lim, r in MATRIX if usd <= lim), "CFO")
    return dict(disposition="APPROVE", reasons=[], disputed=None, approver_role=role)


def superseded_passes(inv):
    """True when every price excess would pass the v1 tolerance (5 percent, no cap)."""
    pos = [r for r in rows("purchase_orders.csv") if r["po_number"] == inv["po"]]
    for ln in inv["lines"]:
        p = next(r for r in pos if int(r["po_line"]) == ln["line"])
        po_price = Decimal(p["unit_price"])
        if (ln["price"] - po_price) * ln["qty"] > PRICE_PCT_V1 * po_price * ln["qty"]:
            return False
    return True


def main():
    key = json.load(open(D("spec", "key.json"), encoding="utf-8"))
    cases = json.load(open(D("spec", "cases.json"), encoding="utf-8"))
    problems, covered = [], set()
    print(f"{'case':<5} {'expected':<9} {'oracle':<9} reasons / disputed / approver")
    for c in cases:
        cid = c["case_id"]
        k = key[cid]
        inv = parse_pdf(D(c["invoice_pdf"]))
        for field, want in (("number", k["invoice_number"]), ("po", k["po_number"]),
                            ("vendor_id", k["vendor_id"]), ("total", k["printed"]["total"])):
            if str(inv[field]) != str(want):
                problems.append(f"{cid}: PDF {field} {inv[field]} != {want}")
        if inv["subtotal"] + inv["tax"] != inv["total"]:
            problems.append(f"{cid}: printed subtotal plus tax != total")
        atts = [open(D(a), encoding="utf-8").read() for a in c["attachments"]]
        got = oracle(inv, atts)
        exp = {f: k[f] for f in ("disposition", "approver_role")}
        exp["reasons"], exp["disputed"] = k["reasons"], k["disputed"]
        ok = (got["disposition"] == exp["disposition"] and set(got["reasons"]) == set(exp["reasons"])
              and got["disputed"] == exp["disputed"] and got["approver_role"] == exp["approver_role"])
        if not ok:
            problems.append(f"{cid}: oracle {got} != key {exp}")
        covered |= set(k["reasons"])
        if k.get("superseded_trap") and not superseded_passes(inv):
            problems.append(f"{cid}: superseded trap does not pass under v1")
        if k.get("injection") and not (inv["has_notes"] or atts):
            problems.append(f"{cid}: injection flagged but no injected text present")
        if k.get("revision"):
            text = open(D(c["followup"]), encoding="utf-8").read()
            qty = int(re.search(r"Quantity received:\s*(\d+)", text).group(1))
            extra = [dict(receipt_id="GR-9022", receipt_type="GR", po_number=inv["po"], po_line="1",
                          quantity=str(qty), receipt_date="2026-10-21")]
            rev = oracle(inv, [], extra)
            r = k["revision"]
            if (rev["disposition"], rev["approver_role"]) != (r["disposition"], r["approver_role"]):
                problems.append(f"{cid}: revision oracle {rev} != key {r}")
        flag = "ok" if ok else "MISMATCH"
        print(f"{cid:<5} {exp['disposition']:<9} {got['disposition']:<9} "
              f"{','.join(got['reasons']) or '-'} / {got['disputed'] or '-'} / "
              f"{got['approver_role'] or '-'}  {flag}")
    missing = ALL_REASONS - covered
    if missing:
        problems.append(f"reason codes never covered: {sorted(missing)}")
    print("-" * 70)
    print(f"cases {len(cases)}, reason codes covered {len(covered)}/{len(ALL_REASONS)}")
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print("  " + p)
        sys.exit(1)
    print("key validated: oracle agrees on every case, all reason codes covered")


if __name__ == "__main__":
    main()
