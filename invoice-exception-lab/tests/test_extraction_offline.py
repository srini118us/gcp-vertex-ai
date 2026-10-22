"""Offline test of the Day 2 pipeline: normalize and score, no API calls.

Builds Document AI shaped responses from spec/printed_fields.json, plants two errors, and checks
that the scorer reports them:
  * R04 total extracted as 8,560.00 instead of 8,902.40 with confidence 0.97 (silent error)
  * E06 line quantity read as 15 instead of 75 with confidence 0.41 (caught by the gate)
Bank account has no Document AI entity in the mock, so it must come from the text fallback.

Run from the lab folder:
    python tests/test_extraction_offline.py
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import extract_invoices as ex  # noqa: E402


def money_ent(t, val, conf=0.98):
    units, cents = str(val).split(".")
    return {"type": t, "mentionText": f"{float(val):,.2f}", "confidence": conf,
            "normalizedValue": {"moneyValue": {"units": units, "nanos": int(cents) * 10 ** 7}}}


def fake_doc(p, vid, total=None, total_conf=0.98, qty_override=None):
    text = (f"INVOICE\nInvoice number {p['invoice_number']} Invoice date {p['invoice_date']}\n"
            f"PO number {p['po_number']} Payment terms NET30\nSupplier ID {vid} Currency {p['currency']}\n"
            f"Subtotal {p['subtotal']}\nTax 7% {p['tax']}\nTotal {p['currency']} {p['total']}\n"
            f"Remit to: Bank, account {p['bank_account']}\n")
    ents = [
        {"type": "invoice_id", "mentionText": p["invoice_number"], "confidence": 0.99},
        {"type": "purchase_order", "mentionText": p["po_number"], "confidence": 0.95},
        {"type": "invoice_date", "mentionText": p["invoice_date"], "confidence": 0.97,
         "normalizedValue": {"dateValue": dict(zip(("year", "month", "day"),
                                                   map(int, p["invoice_date"].split("-"))))}},
        {"type": "currency", "mentionText": p["currency"], "confidence": 0.9},
        money_ent("net_amount", p["subtotal"]),
        money_ent("total_tax_amount", p["tax"]),
        money_ent("total_amount", total or p["total"], total_conf),
    ]
    for ln in p["lines"]:
        q, qc = (qty_override if qty_override else (ln["quantity"], 0.95))
        ents.append({"type": "line_item", "confidence": 0.9, "properties": [
            {"type": "line_item/quantity", "mentionText": str(q), "confidence": qc},
            money_ent("line_item/unit_price", ln["unit_price"]),
            money_ent("line_item/amount", ln["amount"]),
            {"type": "line_item/product_code", "mentionText": ln["product_code"], "confidence": 0.93},
        ]})
    return {"text": text, "entities": ents}


def main():
    lab = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = tempfile.mkdtemp()
    try:
        for sub in ("spec", "scripts"):
            shutil.copytree(os.path.join(lab, sub), os.path.join(tmp, sub))
        os.makedirs(os.path.join(tmp, "results", "extraction"))
        printed = json.load(open(os.path.join(lab, "spec", "printed_fields.json")))
        key = json.load(open(os.path.join(lab, "spec", "key.json")))
        for cid, p in printed.items():
            if cid == "R04":
                doc = fake_doc(p, key[cid]["vendor_id"], total="8560.00", total_conf=0.97)
            elif cid == "E06":
                doc = fake_doc(p, key[cid]["vendor_id"], qty_override=(15, 0.41))
            else:
                doc = fake_doc(p, key[cid]["vendor_id"])
            ext = ex.normalize(doc)
            with open(os.path.join(tmp, "results", "extraction", f"{cid}.json"), "w") as fh:
                json.dump(ext, fh)
        sys.path.insert(0, os.path.join(tmp, "scripts"))
        import importlib
        import common
        common.ROOT = tmp
        import score_extraction as sc
        importlib.reload(sc)
        sc.D = lambda *q: os.path.join(tmp, *q)
        obs, issues = sc.collect()
        wrong = [(c, f) for c, f, ok, conf, s in obs if not ok]
        assert ("R04", "total") in wrong, wrong
        assert ("E06", "line1.quantity") in wrong, wrong
        assert len(wrong) == 2, f"unexpected wrong values: {wrong}"
        bank = [o for o in obs if o[1] == "bank_account"]
        assert all(o[4] == "text_fallback" and o[2] for o in bank), bank
        silent = [o for o in obs if not o[2] and o[4] == "docai" and o[3] is not None and o[3] >= 0.8]
        assert [(o[0], o[1]) for o in silent] == [("R04", "total")], silent
        print(f"offline extraction test passed: {len(obs)} values scored, 2 planted errors found, "
              f"1 silent at gate 0.8, bank account read by fallback on all 20")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
