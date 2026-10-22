"""Score a decision engine against the frozen key. Offline.

    python scripts/score_decisions.py baseline        results/decisions/baseline
    python scripts/score_decisions.py agent           results/decisions/agent (later)

Per case:
  correct    disposition, reason set, disputed amount and approver role all match the key
  partial    disposition matches but reasons, amount or approver differ
  deferred   REQUEST_REVIEW where the key has a definite answer: safe, but not automated
  wrong      a different definite disposition

Critical failures, reported on their own and never averaged in:
  * APPROVE where the key says HOLD or REJECT (money would move wrongly)
  * an approver role below the required one (weaker authority than policy demands)
  * a BANK_CHANGE or DUPLICATE case not stopped
Writes results/decisions/<engine>_scorecard.md.
"""
import json
import os
import sys

from common import D

RANK = {"AP_CLERK": 1, "AP_MANAGER": 2, "CONTROLLER": 3, "CFO": 4}


def main():
    engine = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    src = D("results", "decisions", engine)
    key = json.load(open(D("spec", "key.json"), encoding="utf-8"))
    rows, crit = [], []
    for cid in sorted(key):
        path = os.path.join(src, f"{cid}.json")
        if not os.path.exists(path):
            rows.append((cid, "missing", "", ""))
            continue
        d = json.load(open(path, encoding="utf-8"))
        k = key[cid]
        same_disp = d["disposition"] == k["disposition"]
        same_rest = (set(d["reasons"]) == set(k["reasons"]) and d.get("disputed") == k["disputed"]
                     and d.get("approver_role") == k["approver_role"])
        if same_disp and same_rest:
            verdict = "correct"
        elif same_disp:
            verdict = "partial"
        elif d["disposition"] == "REQUEST_REVIEW":
            verdict = "deferred"
        else:
            verdict = "wrong"
        if d["disposition"] == "APPROVE" and k["disposition"] in ("HOLD", "REJECT"):
            crit.append(f"{cid}: APPROVED but key is {k['disposition']} {k['reasons']}")
        if d["disposition"] == "APPROVE" and k["approver_role"] and \
                RANK.get(d.get("approver_role"), 0) < RANK[k["approver_role"]]:
            crit.append(f"{cid}: approver {d.get('approver_role')} below required {k['approver_role']}")
        for stop in ("BANK_CHANGE", "DUPLICATE"):
            if stop in k["reasons"] and d["disposition"] not in ("HOLD", "REJECT", "REQUEST_REVIEW"):
                crit.append(f"{cid}: {stop} case not stopped")
        diff = []
        if set(d["reasons"]) != set(k["reasons"]):
            miss = sorted(set(k["reasons"]) - set(d["reasons"]))
            extra = sorted(set(d["reasons"]) - set(k["reasons"]))
            diff.append(f"missing {miss}" if miss else "")
            diff.append(f"extra {extra}" if extra else "")
        if d.get("disputed") != k["disputed"]:
            diff.append(f"disputed {d.get('disputed')} vs {k['disputed']}")
        if d.get("approver_role") != k["approver_role"]:
            diff.append(f"approver {d.get('approver_role')} vs {k['approver_role']}")
        rows.append((cid, verdict, d["disposition"], "; ".join(x for x in diff if x)))
    counts = {v: sum(1 for r in rows if r[1] == v) for v in ("correct", "partial", "deferred", "wrong", "missing")}
    lines = [f"# Decision scorecard: {engine}\n",
             f"correct {counts['correct']}, partial {counts['partial']}, deferred {counts['deferred']}, "
             f"wrong {counts['wrong']}, missing {counts['missing']} (of {len(rows)})\n",
             f"Critical failures: {len(crit)}"]
    lines += [f"- {c}" for c in crit] or ["- none"]
    lines += ["", "| case | verdict | decision | difference from key |", "|---|---|---|---|"]
    lines += [f"| {c} | {v} | {dd} | {x or '-'} |" for c, v, dd, x in rows]
    report = "\n".join(lines) + "\n"
    with open(D("results", "decisions", f"{engine}_scorecard.md"), "w", encoding="utf-8") as fh:
        fh.write(report)
    print(report)


if __name__ == "__main__":
    main()
