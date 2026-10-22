"""Offline test of the rules matcher on perfect extractions (CSV data, no API calls).

Perfect extraction = the printed fields of every PDF, vendor resolved, status AUTO. This isolates
matching logic from extraction quality.

Prediction recorded before the first run: 19 of 20 fully correct; E01 has the right disposition,
amount and QTY_OVER_RECEIPT, but misses UNVERIFIED_APPROVAL_CLAIM, because a rules engine does
not read supplier emails. Also checked: fail closed on REVIEW status, on an unknown vendor and on
a PO that belongs to another vendor; E01 revision (follow up receipt) flips to APPROVE CONTROLLER.

Run from the lab folder:
    python tests/test_matcher_offline.py
"""
import copy
import json
import os
import sys

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "scripts"))
import matcher  # noqa: E402
from repository import CsvRepo  # noqa: E402


def fld(v):
    return {"value": v, "confidence": 0.99, "source": "docai"}


def perfect(cid, p, k):
    return {"case_id": cid, "status": "AUTO", "vendor_id": k["vendor_id"],
            "fields": {"invoice_number": fld(p["invoice_number"]), "invoice_date": fld(p["invoice_date"]),
                       "po_number": fld(p["po_number"]), "currency": fld(p["currency"]),
                       "subtotal": fld(p["subtotal"]), "tax": fld(p["tax"]), "total": fld(p["total"]),
                       "bank_account": {"value": p["bank_account"], "confidence": None,
                                        "source": "text_fallback"}},
            "lines": [{"quantity": fld(l["quantity"]), "unit_price": fld(l["unit_price"]),
                       "amount": fld(l["amount"]), "product_code": fld(l["product_code"])}
                      for l in p["lines"]]}


class RepoWithExtraReceipt(CsvRepo):
    """CSV data plus the E01 follow up receipt GR-9022 (150 units)."""
    def received(self, po, ln, t):
        extra = 150 if (po, int(ln), t) == ("PO-4501", 1, "GR") else 0
        return super().received(po, ln, t) + extra


def main():
    printed = json.load(open(os.path.join(LAB, "spec", "printed_fields.json")))
    key = json.load(open(os.path.join(LAB, "spec", "key.json")))
    repo = CsvRepo()
    correct, partial = [], []
    for cid in sorted(key):
        k = key[cid]
        d = matcher.match(perfect(cid, printed[cid], k), repo)
        ok_disp = d["disposition"] == k["disposition"]
        ok_all = ok_disp and set(d["reasons"]) == set(k["reasons"]) and \
            d["disputed"] == k["disputed"] and d["approver_role"] == k["approver_role"]
        assert ok_disp, f"{cid}: {d['disposition']} vs key {k['disposition']} {d}"
        (correct if ok_all else partial).append(cid)
        for fd in d["findings"]:
            assert fd["clause"].startswith("AP-POL-"), fd
    assert partial == ["E01"], f"partial: {partial}"
    e01 = matcher.match(perfect("E01", printed["E01"], key["E01"]), repo)
    assert e01["reasons"] == ["QTY_OVER_RECEIPT"] and e01["disputed"] == "18750.00", e01

    # fail closed
    v = perfect("R01", printed["R01"], key["R01"])
    v_review = dict(v, status="REVIEW", review_reasons=["low confidence: line 2 quantity"])
    assert matcher.match(v_review, repo)["disposition"] == "REQUEST_REVIEW"
    assert matcher.match(dict(v, vendor_id=None), repo)["disposition"] == "REQUEST_REVIEW"
    wrong_po = copy.deepcopy(v)
    wrong_po["fields"]["po_number"] = fld("PO-4501")      # belongs to V100, invoice is V600
    assert matcher.match(wrong_po, repo)["disposition"] == "REQUEST_REVIEW"
    # hostile invoice number is only data
    hostile = copy.deepcopy(v)
    hostile["fields"]["invoice_number"] = fld("FW-1'; DROP TABLE vendors; --")
    assert matcher.match(hostile, repo)["disposition"] == "APPROVE"

    # stateful revision: the follow up receipt clears E01
    rev = matcher.match(perfect("E01", printed["E01"], key["E01"]), RepoWithExtraReceipt())
    r = key["E01"]["revision"]
    assert (rev["disposition"], rev["approver_role"]) == (r["disposition"], r["approver_role"]), rev

    print(f"offline matcher test passed: {len(correct)} correct, partial {partial} "
          f"(missing UNVERIFIED_APPROVAL_CLAIM, as predicted), fail closed on review status, "
          f"unknown vendor and foreign PO, hostile invoice number treated as data, "
          f"E01 revision gives APPROVE CONTROLLER")


if __name__ == "__main__":
    main()
