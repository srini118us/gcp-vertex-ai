"""Day 2b: verification controls between extraction and matching. Offline, no API calls.

Extraction alone is not trusted. Each invoice passes three deterministic controls before the
matcher may use it:

  1. Vendor resolution against the vendor master. The vendor id must appear in the document
     text AND the Document AI supplier name must match the same vendor in the master. Reading
     "the value after the label" is not used: Document AI text reorders table cells (on E07 the
     text runs "Supplier ID, Evergreen Logistics Services, EVL-2026-1015, PO-4517, V500").
  2. Arithmetic invariants: quantity x unit price = amount on every line, lines sum to the
     subtotal, subtotal + tax = total. This catches misreads regardless of confidence (E08 read
     quantity 6080 for 80; 6080 x 60.00 is not 4,800.00).
  3. Confidence gate on Document AI critical fields (default 0.80).

Bank account: read from text, no confidence. It is NOT sent to review here, because the matcher
compares it with the vendor master and any difference produces a BANK_CHANGE hold. A misread can
therefore only cause a false hold, never a payment to a wrong account. That asymmetry is the
reason this value may stay unverified at this step.

An invoice with any review reason gets status REVIEW and does not reach the matcher automatically.

Writes results/verified/<case>.json and, when spec/printed_fields.json exists, an evaluation of
which extraction errors the controls caught and which would have passed silently.

Run from the lab folder:
    python scripts/verify_extraction.py
"""
import csv
import json
import os
import re
from decimal import Decimal

from common import D

GATE = float(os.getenv("INV_CONF_MIN", "0.80"))
# strict (default) or corroborated. Both decisions are always computed and saved (shadow mode).
MODE = os.getenv("INV_VERIFY_MODE", "strict")
# risk tier: corroboration only applies to invoices at or below this total (invoice currency)
CORRO_LIMIT = Decimal(os.getenv("INV_CORRO_LIMIT", "50000"))
CRITICAL_HEADER = ["invoice_number", "po_number", "currency", "subtotal", "tax", "total"]
CRITICAL_LINE = ["quantity", "unit_price", "amount"]
CENT = Decimal("0.01")


def dec(v):
    try:
        return Decimal(str(v))
    except Exception:
        return None


def simple(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def load_vendors():
    with open(D("data", "vendors.csv"), encoding="utf-8") as fh:
        return {r["vendor_id"]: r for r in csv.DictReader(fh)}


def resolve_vendor(ext, vendors):
    text = ext.get("text", "")
    ids = sorted({t for t in re.findall(r"\bV\d{3}\b", text) if t in vendors})
    name = (ext["fields"].get("supplier_name") or {}).get("value")
    by_name = [vid for vid, v in vendors.items()
               if name and (simple(v["name"]) == simple(name)
                            or simple(v["name"]).startswith(simple(name))
                            or simple(name).startswith(simple(v["name"])))]
    info = {"ids_in_text": ids, "supplier_name": name, "name_matches": by_name}
    if len(ids) == 1 and by_name == ids:
        return ids[0], "id_and_name_agree", info, None
    if len(ids) == 1 and not by_name:
        return None, "id_only", info, "vendor name not matched to master, id alone is not enough"
    if not ids and len(by_name) == 1:
        return None, "name_only", info, "no vendor id in document, name alone is not enough"
    return None, "conflict", info, f"vendor ids in text {ids} vs name matches {by_name}"


def arithmetic(ext):
    problems = []
    f = ext["fields"]
    sub, tax, tot = (dec(f.get(k, {}).get("value")) for k in ("subtotal", "tax", "total"))
    line_sum = Decimal("0")
    for i, li in enumerate(ext["lines"], 1):
        q, p, a = (dec((li.get(k) or {}).get("value")) for k in ("quantity", "unit_price", "amount"))
        if None in (q, p, a):
            problems.append(f"line {i}: missing quantity, unit price or amount")
            continue
        if abs(q * p - a) > CENT:
            problems.append(f"line {i}: {q} x {p} = {q * p} but amount is {a}")
        line_sum += a
    if sub is not None and ext["lines"] and abs(line_sum - sub) > CENT:
        problems.append(f"lines sum to {line_sum} but subtotal is {sub}")
    if None not in (sub, tax, tot) and abs(sub + tax - tot) > CENT:
        problems.append(f"subtotal {sub} + tax {tax} != total {tot}")
    return problems


def gate(ext):
    """Low confidence critical values as (where, field, text). where is 'header' or a line number."""
    low = []
    for k in CRITICAL_HEADER:
        fld = ext["fields"].get(k, {})
        if fld.get("source") == "docai" and fld.get("confidence") is not None and fld["confidence"] < GATE:
            low.append(("header", k, f"{k} confidence {fld['confidence']}"))
        if fld.get("source") == "missing":
            low.append(("header", k, f"{k} missing"))
    for i, li in enumerate(ext["lines"], 1):
        for k in CRITICAL_LINE:
            c = (li.get(k) or {}).get("confidence")
            if c is not None and c < GATE:
                low.append((i, k, f"line {i} {k} confidence {c}"))
    return low


def corroborated(item, arith_problems, ext):
    """A low confidence line value is corroborated when every arithmetic invariant holds (its own
    line, lines to subtotal, subtotal plus tax to total) and the subtotal and total themselves
    passed the gate. Header values are never corroborated by this rule."""
    where, field, _ = item
    if where == "header" or arith_problems:
        return False
    f = ext["fields"]
    for k in ("subtotal", "total"):
        c = f.get(k, {}).get("confidence")
        if f.get(k, {}).get("source") != "docai" or c is None or c < GATE:
            return False
    return True


def verify(ext, vendors):
    vid, method, info, vproblem = resolve_vendor(ext, vendors)
    base = []
    if vproblem:
        base.append(f"vendor: {vproblem}")
    arith = arithmetic(ext)
    base += [f"arithmetic: {p}" for p in arith]
    low = gate(ext)
    strict = base + [f"low confidence: {x[2]}" for x in low]
    relaxed = base + [f"low confidence: {x[2]}" for x in low if not corroborated(x, arith, ext)]
    corro = [x[2] for x in low if corroborated(x, arith, ext)]
    total = dec(ext["fields"].get("total", {}).get("value")) or Decimal("0")
    # risk tier: corroboration is not allowed above the limit, those keep the strict decision
    if total > CORRO_LIMIT:
        relaxed, corro = strict, []
    active = relaxed if MODE == "corroborated" else strict
    return {"case_id": ext.get("case_id"), "status": "REVIEW" if active else "AUTO",
            "review_reasons": active, "mode": MODE,
            "shadow": {"strict_status": "REVIEW" if strict else "AUTO",
                       "corroborated_status": "REVIEW" if relaxed else "AUTO",
                       "corroborated_values": corro},
            "vendor_id": vid, "vendor_method": method,
            "vendor_evidence": info, "fields": ext["fields"], "lines": ext["lines"]}


def evaluate(results):
    """Which extraction errors did the controls catch? Uses the printed ground truth."""
    path = D("spec", "printed_fields.json")
    if not os.path.exists(path):
        return None
    truth = json.load(open(path, encoding="utf-8"))
    key = json.load(open(D("spec", "key.json"), encoding="utf-8"))
    rows = []
    for r in results:
        cid, t = r["case_id"], truth[r["case_id"]]
        wrong = []
        if r["vendor_id"] not in (None, key[cid]["vendor_id"]):
            wrong.append("vendor_id")
        for k in CRITICAL_HEADER:
            v = r["fields"].get(k, {}).get("value")
            want = t[k]
            if k in ("subtotal", "tax", "total"):
                ok = v is not None and abs(float(v) - float(want)) < 0.005
            else:
                ok = v is not None and re.sub(r"\s", "", str(v)).upper() == re.sub(r"\s", "", str(want)).upper()
            if not ok:
                wrong.append(k)
        for i, tl in enumerate(t["lines"]):
            li = r["lines"][i] if i < len(r["lines"]) else {}
            for k in CRITICAL_LINE:
                v = (li.get(k) or {}).get("value")
                if v is None or abs(float(v) - float(tl[k])) >= 0.005:
                    wrong.append(f"line{tl['line']}.{k}")
        rows.append((cid, r["status"], wrong, r["vendor_id"] is None))
    return rows


def main():
    vendors = load_vendors()
    src = D("results", "extraction")
    files = sorted(f for f in os.listdir(src) if f.endswith(".json")) if os.path.isdir(src) else []
    if not files:
        raise SystemExit("no extraction results, run scripts/extract_invoices.py first")
    os.makedirs(D("results", "verified"), exist_ok=True)
    results = []
    print(f"mode {MODE}, gate {GATE}, corroboration limit {CORRO_LIMIT}")
    print(f"{'case':<5} {'status':<7} {'strict':<7} {'corro':<7} {'vendor':<7} review reasons")
    for f in files:
        ext = json.load(open(os.path.join(src, f), encoding="utf-8"))
        ext.setdefault("case_id", f[:-5])
        r = verify(ext, vendors)
        results.append(r)
        with open(D("results", "verified", f), "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=1)
        sh = r["shadow"]
        print(f"{r['case_id']:<5} {r['status']:<7} {sh['strict_status']:<7} {sh['corroborated_status']:<7} "
              f"{r['vendor_id'] or '-':<7} {'; '.join(r['review_reasons']) or '-'}")
    auto = sum(1 for r in results if r["status"] == "AUTO")
    print("-" * 80)
    print(f"AUTO {auto}, REVIEW {len(results) - auto}, gate {GATE}")
    ev = evaluate(results)
    if ev is not None:
        by_case = {r["case_id"]: r for r in results}
        for label, key in (("strict", "strict_status"), ("corroborated", "corroborated_status")):
            st = {c: by_case[c]["shadow"][key] for c, _, _, _ in ev}
            silent = [(c, w) for c, _, w, _ in ev if w and st[c] == "AUTO"]
            caught = [(c, w) for c, _, w, _ in ev if w and st[c] == "REVIEW"]
            false_review = [c for c, _, w, _ in ev if not w and st[c] == "REVIEW"]
            print(f"[{label}] errors caught: {caught or 'none'} | silent: {silent or 'none'} | "
                  f"false reviews: {len(false_review)} {false_review or ''}")
        flips = [r["case_id"] for r in results
                 if r["shadow"]["strict_status"] != r["shadow"]["corroborated_status"]]
        print(f"shadow disagreement (strict vs corroborated): {flips or 'none'}")


if __name__ == "__main__":
    main()
