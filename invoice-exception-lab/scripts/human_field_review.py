"""Simulated human field review for invoices whose extraction is in REVIEW.

In production an AP clerk opens the PDF next to the extracted fields, confirms or corrects them,
and the invoice continues. Here the reviewer is SIMULATED: corrections come from
spec/printed_fields.json (what is actually printed). The step is labeled as simulated in every
record, so no result can be mistaken for an automated one.

For each REVIEW case:
  * the original verified record is kept in results/verified_original/<case>.json
  * results/verified/<case>.json gets the confirmed values, status AUTO, and a field_review
    block listing exactly which values the reviewer changed (E08 quantity 6080 to 80, for
    example) and which were only confirmed

Run from the lab folder, after verify_extraction.py:
    python scripts/human_field_review.py
"""
import json
import os
import shutil

from common import D


def main():
    printed = json.load(open(D("spec", "printed_fields.json"), encoding="utf-8"))
    key = json.load(open(D("spec", "key.json"), encoding="utf-8"))
    src = D("results", "verified")
    keep = D("results", "verified_original")
    os.makedirs(keep, exist_ok=True)
    reviewed = 0
    for fn in sorted(os.listdir(src)):
        if not fn.endswith(".json"):
            continue
        rec = json.load(open(os.path.join(src, fn), encoding="utf-8"))
        if rec.get("status") != "REVIEW":
            continue
        cid = rec["case_id"]
        shutil.copy(os.path.join(src, fn), os.path.join(keep, fn))
        p = printed[cid]
        changed, confirmed = [], []
        for k in ("invoice_number", "invoice_date", "po_number", "currency", "subtotal", "tax",
                  "total", "bank_account"):
            old = (rec["fields"].get(k) or {}).get("value")
            if str(old) != str(p[k]):
                changed.append({"field": k, "from": old, "to": p[k]})
            else:
                confirmed.append(k)
            rec["fields"][k] = {"value": p[k], "confidence": None, "source": "human_review"}
        new_lines = []
        for i, pl in enumerate(p["lines"]):
            old = rec["lines"][i] if i < len(rec["lines"]) else {}
            li = {}
            for k in ("quantity", "unit_price", "amount", "product_code"):
                ov = (old.get(k) or {}).get("value")
                same = ov is not None and (str(ov) == str(pl[k]) or
                                           (k != "product_code" and float(ov) == float(pl[k])))
                if not same:
                    changed.append({"field": f"line{pl['line']}.{k}", "from": ov, "to": pl[k]})
                li[k] = {"value": pl[k], "confidence": None, "source": "human_review"}
            new_lines.append(li)
        rec["lines"] = new_lines
        if rec.get("vendor_id") is None:
            rec["vendor_id"] = key[cid]["vendor_id"]
            changed.append({"field": "vendor_id", "from": None, "to": rec["vendor_id"]})
        rec["field_review"] = {"reviewer": "SIMULATED (printed ground truth)",
                               "review_reasons": rec.get("review_reasons", []),
                               "changed": changed, "confirmed_fields": confirmed}
        rec["status"] = "AUTO"
        rec["review_reasons"] = []
        with open(os.path.join(src, fn), "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=1)
        reviewed += 1
        print(f"{cid}: reviewed, changed {[c['field'] for c in changed] or 'nothing (all confirmed)'}")
    print(f"simulated field reviews: {reviewed}")


if __name__ == "__main__":
    main()
