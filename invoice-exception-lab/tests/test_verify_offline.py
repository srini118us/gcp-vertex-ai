"""Offline test of the verification controls, using the failure shapes seen in the live run.

  E07 shape: text with table cells reordered, the vendor id far from its label; supplier name
             entity present. Must resolve V500 by id and name agreement, status AUTO.
  E08 shape: quantity read as 6080 (true 80) at confidence 0.529. Must go to REVIEW, and the
             arithmetic control must catch it even if the confidence had been high.
  Conflict:  vendor id in text says V100 but the name matches V300. Must go to REVIEW.
  R01 shape: clean, two lines. Must be AUTO.

Run from the lab folder:
    python tests/test_verify_offline.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import verify_extraction as vx  # noqa: E402


def f(v, c=0.97, s="docai"):
    return {"value": v, "confidence": c, "source": s}


def ext(text, name, lines, sub, tax, tot, cid):
    return {"case_id": cid, "text": text, "lines": lines, "fields": {
        "invoice_number": f("X-1"), "po_number": f("PO-1"), "currency": f("USD"),
        "subtotal": f(sub), "tax": f(tax), "total": f(tot), "supplier_name": f(name),
        "bank_account": f("123", None, "text_fallback")}}


def line(q, p, a, qc=0.95):
    return {"quantity": {"value": q, "confidence": qc}, "unit_price": {"value": p, "confidence": 0.97},
            "amount": {"value": a, "confidence": 0.97}}


def main():
    vendors = vx.load_vendors()
    e07 = ext("Supplier ID\nEvergreen Logistics Services\nEVL-2026-1015\nPO-4517\nV500\nInvoice date",
              "Evergreen Logistics Services", [line("1", "7800.00", "7800.00")],
              "7800.00", "0.00", "7800.00", "E07")
    r = vx.verify(e07, vendors)
    assert (r["status"], r["vendor_id"], r["vendor_method"]) == ("AUTO", "V500", "id_and_name_agree"), r

    e08 = ext("Supplier ID\nBill to: Calder Industries Inc.\nApex Components Inc.\nV100",
              "Apex Components Inc.", [line("6080", "60.00", "4800.00", qc=0.529)],
              "4800.00", "336.00", "5136.00", "E08")
    r = vx.verify(e08, vendors)
    assert r["status"] == "REVIEW" and r["vendor_id"] == "V100", r
    assert any(x.startswith("arithmetic: line 1") for x in r["review_reasons"]), r
    e08_high = ext(e08["text"], "Apex Components Inc.", [line("6080", "60.00", "4800.00", qc=0.99)],
                   "4800.00", "336.00", "5136.00", "E08h")
    r = vx.verify(e08_high, vendors)
    assert r["status"] == "REVIEW" and not any("confidence" in x for x in r["review_reasons"]), r

    conflict = ext("Supplier ID V100", "Coastal Steel Supply Co.", [line("10", "5.00", "50.00")],
                   "50.00", "3.50", "53.50", "C1")
    r = vx.verify(conflict, vendors)
    assert r["status"] == "REVIEW" and r["vendor_id"] is None and r["vendor_method"] == "conflict", r

    r01 = ext("Supplier ID\nV600\nFairway Office Supply", "Fairway Office Supply",
              [line("30", "42.00", "1260.00"), line("6", "18.50", "111.00")],
              "1371.00", "95.97", "1466.97", "R01")
    r = vx.verify(r01, vendors)
    assert (r["status"], r["vendor_id"]) == ("AUTO", "V600"), r
    # corroboration: R01 with a low confidence but correct quantity
    r01_low = ext(r01["text"], "Fairway Office Supply",
                  [line("30", "42.00", "1260.00"), line("6", "18.50", "111.00", qc=0.564)],
                  "1371.00", "95.97", "1466.97", "R01L")
    r = vx.verify(r01_low, vendors)
    assert r["shadow"] == {"strict_status": "REVIEW", "corroborated_status": "AUTO",
                           "corroborated_values": ["line 2 quantity confidence 0.564"]}, r["shadow"]
    # E08 shape is never corroborated, its arithmetic fails
    r = vx.verify(e08, vendors)
    assert r["shadow"]["corroborated_status"] == "REVIEW", r["shadow"]
    # risk tier: above the limit corroboration does not apply
    big = ext(r01["text"], "Fairway Office Supply", [line("600", "100.00", "60000.00", qc=0.6)],
              "60000.00", "4200.00", "64200.00", "BIG")
    r = vx.verify(big, vendors)
    assert r["shadow"]["corroborated_status"] == "REVIEW", r["shadow"]
    print("offline verification test passed: reordered text resolved, 6080 misread caught by "
          "arithmetic even at high confidence, vendor conflict sent to review, clean invoice AUTO, corroboration clears a correct low confidence\n"
          "quantity but never a failed arithmetic line or an invoice above the risk limit")


if __name__ == "__main__":
    main()
