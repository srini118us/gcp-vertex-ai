"""Day 2: extract every invoice PDF with the Document AI Invoice Parser.

For each case it saves:
  results/docai_raw/<case>.json     entities and full text exactly as returned (pages dropped)
  results/extraction/<case>.json    normalized fields, each with value, confidence and source

Source is "docai" when the field came from a Document AI entity, "text_fallback" when Document
AI returned no entity and the value was read from the document text by a pattern, or "missing".
A fallback is never silent: it is recorded on the field and counted in the summary.

The full document text is kept as data (it is where an injected instruction would sit). Nothing
in the text is ever executed as an instruction.

Run from the lab folder (costs about 0.10 USD per invoice, 2.00 USD for all 20):
    python scripts/extract_invoices.py            all cases, skips ones already extracted
    python scripts/extract_invoices.py R01 E03    selected cases
    set INV_FORCE=1 to re-extract
"""
import base64
import json
import os
import re
import sys
import time
from decimal import Decimal

from common import D, call, processor_name

FORCE = os.getenv("INV_FORCE") == "1"

# Document AI Invoice Parser entity types mapped to our field names
HEADER_MAP = {
    "invoice_id": "invoice_number",
    "invoice_date": "invoice_date",
    "purchase_order": "po_number",
    "supplier_name": "supplier_name",
    "currency": "currency",
    "net_amount": "subtotal",
    "total_tax_amount": "tax",
    "total_amount": "total",
    "supplier_iban": "bank_account",
}
LINE_MAP = {
    "line_item/quantity": "quantity",
    "line_item/unit_price": "unit_price",
    "line_item/amount": "amount",
    "line_item/product_code": "product_code",
    "line_item/description": "description",
}
MONEY = {"subtotal", "tax", "total", "unit_price", "amount"}


def to_decimal(text):
    if text is None:
        return None
    s = re.sub(r"[^0-9.\-]", "", str(text))
    try:
        return str(Decimal(s).quantize(Decimal("0.01")))
    except Exception:
        return None


def norm_value(field, ent):
    """Prefer Document AI's normalized value, fall back to the mention text."""
    nv = ent.get("normalizedValue") or {}
    mention = (ent.get("mentionText") or "").strip()
    if field in MONEY:
        mv = nv.get("moneyValue")
        if mv:
            units = Decimal(str(mv.get("units", 0)))
            nanos = Decimal(str(mv.get("nanos", 0))) / Decimal(10 ** 9)
            return str((units + nanos).quantize(Decimal("0.01")))
        return to_decimal(nv.get("text") or mention)
    if field == "quantity":
        q = to_decimal(nv.get("text") or mention)
        return str(int(Decimal(q))) if q is not None else None
    if field == "invoice_date":
        dv = nv.get("dateValue")
        if dv and dv.get("year"):
            return f"{dv['year']:04d}-{dv.get('month', 1):02d}-{dv.get('day', 1):02d}"
        return nv.get("text") or mention
    if field == "currency":
        return (nv.get("text") or mention).upper()[:3]
    return mention.replace("\n", " ")


def text_fallbacks(text):
    """Patterns over the document text, used only when no entity was returned."""
    out = {}
    pats = {
        "invoice_number": r"Invoice number\s+(.+?)\s+Invoice date",
        "po_number": r"PO number\s+(\S+)",
        "invoice_date": r"Invoice date\s+(\d{4}-\d{2}-\d{2})",
        "currency": r"Currency\s+([A-Z]{3})",
        "subtotal": r"Subtotal\s+([\d,]+\.\d\d)",
        "tax": r"Tax \d+%\s+([\d,]+\.\d\d)",
        "total": r"Total [A-Z]{3}\s+([\d,]+\.\d\d)",
        "bank_account": r"account\s+([A-Z0-9]{8,})",
    }
    for field, pat in pats.items():
        mm = re.search(pat, text, re.S)
        if mm:
            val = mm.group(1).strip()
            out[field] = to_decimal(val) if field in MONEY else val
    return out


def normalize(doc):
    text = doc.get("text", "")
    fields, lines = {}, []
    for ent in doc.get("entities", []):
        etype = ent.get("type")
        if etype in HEADER_MAP:
            f = HEADER_MAP[etype]
            cand = {"value": norm_value(f, ent), "confidence": round(ent.get("confidence", 0.0), 3),
                    "source": "docai", "mention": ent.get("mentionText")}
            # keep the highest confidence entity when a type repeats
            if f not in fields or cand["confidence"] > fields[f]["confidence"]:
                fields[f] = cand
        elif etype == "line_item":
            li = {}
            for prop in ent.get("properties", []):
                f = LINE_MAP.get(prop.get("type"))
                if f:
                    li[f] = {"value": norm_value(f, prop),
                             "confidence": round(prop.get("confidence", 0.0), 3)}
            li["_confidence"] = round(ent.get("confidence", 0.0), 3)
            lines.append(li)
    fb = text_fallbacks(text)
    for f in ("invoice_number", "po_number", "invoice_date", "currency", "subtotal", "tax",
              "total", "bank_account"):
        if f not in fields or fields[f]["value"] in (None, ""):
            if f in fb:
                fields[f] = {"value": fb[f], "confidence": None, "source": "text_fallback"}
            else:
                fields[f] = {"value": None, "confidence": None, "source": "missing"}
    return {"fields": fields, "lines": lines, "text": text}


def process(pdf_path):
    with open(pdf_path, "rb") as fh:
        content = base64.b64encode(fh.read()).decode()
    name = processor_name()
    loc = name.split("/locations/")[1].split("/")[0]
    url = f"https://{loc}-documentai.googleapis.com/v1/{name}:process"
    t0 = time.time()
    resp = call("POST", url, {"rawDocument": {"content": content, "mimeType": "application/pdf"},
                              "skipHumanReview": True})
    return resp, round(time.time() - t0, 2)


def main():
    cases = json.load(open(D("spec", "cases.json"), encoding="utf-8"))
    wanted = set(sys.argv[1:])
    os.makedirs(D("results", "docai_raw"), exist_ok=True)
    os.makedirs(D("results", "extraction"), exist_ok=True)
    errors = []
    for c in cases:
        cid = c["case_id"]
        if wanted and cid not in wanted:
            continue
        out_path = D("results", "extraction", f"{cid}.json")
        if os.path.exists(out_path) and not FORCE:
            print(f"{cid}: already extracted, skipping (INV_FORCE=1 to redo)")
            continue
        try:
            resp, secs = process(D(c["invoice_pdf"]))
        except Exception as e:
            errors.append(cid)
            print(f"{cid}: ERROR {e}")
            continue
        doc = resp.get("document", {})
        raw = {"text": doc.get("text", ""), "entities": doc.get("entities", []),
               "latency_s": secs}
        with open(D("results", "docai_raw", f"{cid}.json"), "w", encoding="utf-8") as fh:
            json.dump(raw, fh, indent=1)
        ext = normalize(doc)
        ext["case_id"], ext["latency_s"] = cid, secs
        ext["entity_types_seen"] = sorted({e.get("type") for e in doc.get("entities", [])})
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(ext, fh, indent=1)
        f = ext["fields"]
        srcs = {k: v["source"] for k, v in f.items() if v["source"] != "docai"}
        print(f"{cid}: {secs}s, {len(doc.get('entities', []))} entities, {len(ext['lines'])} lines, "
              f"total={f['total']['value']} conf={f['total']['confidence']}, "
              f"non docai fields={srcs or 'none'}")
    print(f"errors: {errors or 'none'}")
    print("next: python scripts/score_extraction.py")


if __name__ == "__main__":
    main()
