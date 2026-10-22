"""Day 2: score extraction against what is actually printed on each PDF.

Offline, no API calls. Reads results/extraction/*.json and spec/printed_fields.json.

Vendor identity is not scored here: scripts/verify_extraction.py resolves it against the
vendor master (the label adjacent text pattern used at first was wrong on 3 of 20).

Reports:
  * field accuracy per field, and how each field was sourced (docai, text_fallback, missing)
  * line item accuracy (quantity, unit price, amount, product code)
  * the confidence gate: for each threshold, how many wrong values would pass silently
    (wrong but confident, the critical failure) and how many fields go to human review
Writes results/extraction_scorecard.md.

Run from the lab folder:
    python scripts/score_extraction.py
    set INV_CONF_MIN=0.8 to change the gate used for the headline (default 0.80)
"""
import json
import os
import re
from collections import Counter, defaultdict

from common import D

GATE = float(os.getenv("INV_CONF_MIN", "0.80"))
HEADER = ["invoice_number", "invoice_date", "po_number", "currency", "subtotal", "tax",
          "total", "bank_account"]
LINE_FIELDS = ["quantity", "unit_price", "amount", "product_code"]
CRITICAL = {"invoice_number", "po_number", "currency", "subtotal", "tax", "total",
            "bank_account", "quantity", "unit_price", "amount"}


def same(field, got, want):
    if got is None:
        return False
    g, w = str(got).strip(), str(want).strip()
    if field in ("invoice_number", "po_number", "product_code", "bank_account", "supplier_id"):
        return re.sub(r"\s", "", g).upper() == re.sub(r"\s", "", w).upper()
    if field in ("subtotal", "tax", "total", "unit_price", "amount"):
        try:
            return abs(float(g) - float(w)) < 0.005
        except ValueError:
            return False
    if field == "quantity":
        try:
            return int(float(g)) == int(float(w))
        except ValueError:
            return False
    return g.upper() == w.upper()


def collect():
    truth = json.load(open(D("spec", "printed_fields.json"), encoding="utf-8"))
    key = json.load(open(D("spec", "key.json"), encoding="utf-8"))
    obs = []   # (case, field, correct, confidence, source)
    line_issues = []
    for cid, t in truth.items():
        path = D("results", "extraction", f"{cid}.json")
        if not os.path.exists(path):
            continue
        ext = json.load(open(path, encoding="utf-8"))
        want = t
        for f in HEADER:
            got = ext["fields"].get(f, {"value": None, "confidence": None, "source": "missing"})
            obs.append((cid, f, same(f, got["value"], want[f]), got["confidence"], got["source"]))
        # line items, matched in printed order
        lines = ext["lines"]
        if len(lines) != len(t["lines"]):
            line_issues.append(f"{cid}: {len(lines)} lines extracted, {len(t['lines'])} printed")
        for i, tl in enumerate(t["lines"]):
            li = lines[i] if i < len(lines) else {}
            for f in LINE_FIELDS:
                got = li.get(f, {"value": None, "confidence": None})
                obs.append((cid, f"line{tl['line']}.{f}", same(f, got.get("value"), tl[f]),
                            got.get("confidence"), "docai" if got.get("value") is not None else "missing"))
    return obs, line_issues


def base(field):
    return field.split(".")[-1]


def main():
    obs, line_issues = collect()
    if not obs:
        raise SystemExit("no extraction results found, run scripts/extract_invoices.py first")
    cases = sorted({o[0] for o in obs})
    out = [f"# Extraction scorecard\n", f"Cases scored: {len(cases)}. Gate: confidence {GATE}.\n"]

    acc, src = defaultdict(lambda: [0, 0]), defaultdict(Counter)
    for cid, f, ok, conf, s in obs:
        b = base(f)
        acc[b][0] += ok
        acc[b][1] += 1
        src[b][s] += 1
    out.append("## Field accuracy\n")
    out.append("| field | correct | sources |")
    out.append("|---|---|---|")
    for b in HEADER + LINE_FIELDS:
        if b in acc:
            c, n = acc[b]
            out.append(f"| {b} | {c}/{n} | {', '.join(f'{k} {v}' for k, v in src[b].items())} |")

    out.append("\n## Confidence gate (Document AI sourced values only)\n")
    out.append("A silent error is a wrong value at or above the gate. It is the failure that matters:")
    out.append("nothing would stop it. Review load is values below the gate.\n")
    out.append("| gate | silent errors (critical fields) | silent errors (all) | sent to review | caught errors |")
    out.append("|---|---|---|---|---|")
    scored = [o for o in obs if o[4] == "docai" and o[3] is not None]
    for gate in (0.5, 0.7, 0.8, 0.9, 0.95):
        silent = [o for o in scored if not o[2] and o[3] >= gate]
        silent_c = [o for o in silent if base(o[1]) in CRITICAL]
        review = [o for o in scored if o[3] < gate]
        caught = [o for o in review if not o[2]]
        out.append(f"| {gate} | {len(silent_c)} | {len(silent)} | {len(review)} | {len(caught)} |")

    fallback = [o for o in obs if o[4] == "text_fallback"]
    missing = [o for o in obs if o[4] == "missing"]
    wrong_fb = [o for o in fallback if not o[2]]
    out.append("\n## Fallbacks and gaps\n")
    out.append(f"- Values read by text pattern because Document AI returned no entity: {len(fallback)} "
               f"({len(wrong_fb)} wrong). These carry no confidence, so the workflow must treat them "
               f"as needing deterministic verification.")
    out.append(f"- Values missing entirely: {len(missing)}")
    for li in line_issues:
        out.append(f"- {li}")

    wrong = [o for o in obs if not o[2]]
    out.append("\n## Every wrong value\n")
    if wrong:
        out.append("| case | field | source | confidence |")
        out.append("|---|---|---|---|")
        for cid, f, ok, conf, s in wrong:
            out.append(f"| {cid} | {f} | {s} | {conf} |")
    else:
        out.append("None.")
    report = "\n".join(out) + "\n"
    with open(D("results", "extraction_scorecard.md"), "w", encoding="utf-8") as fh:
        fh.write(report)
    print(report)


if __name__ == "__main__":
    main()
