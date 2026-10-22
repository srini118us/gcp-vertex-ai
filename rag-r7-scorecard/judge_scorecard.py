"""R7 scorecard: one uniform LLM judge scores the final answers of R1 to R6.

The judge is blind to the pattern. For each (pattern, question) it sees the question,
the gold answer, whether the question is answerable, and the candidate answer, and
returns JSON: correct, contradicts_gold, refused, note.

Scoring rules (computed in code, not by the judge):
  answerable question:   good = correct and not contradicts_gold
                         false refusal = refused
  unanswerable question: good = refused (correct refusal)
                         hallucination = not refused

Not scored: grounding. R1 to R5 did not store the retrieved text, so grounding cannot be
judged uniformly. contradicts_gold against the gold answer is the hallucination proxy.

Latency and cost are ESTIMATES from the pattern design (calls per question), because the
runs did not log them uniformly. They are labelled as estimates in the output.

Run from the repo root:
    python rag-r7-scorecard\\judge_scorecard.py

Env knobs: RAG_THROTTLE (default 3), RAG_PROJECT, RAG_LOCATION, RAG_GEMINI.
Reruns resume from results_judgments.jsonl. Output: results_judgments.jsonl, scorecard.md
"""
import json
import os
import random
import subprocess
import time
import urllib.request
import urllib.error

PROJECT = os.getenv("RAG_PROJECT", "enterprise-agent-labs-1012")
LOCATION = os.getenv("RAG_LOCATION", "global")
GEMINI = os.getenv("RAG_GEMINI", "gemini-3.8-flash")
THROTTLE = float(os.getenv("RAG_THROTTLE", "3"))

_host = "aiplatform.googleapis.com" if LOCATION == "global" else f"{LOCATION}-aiplatform.googleapis.com"
GEMINI_URL = (f"https://{_host}/v1/projects/{PROJECT}/locations/{LOCATION}"
              f"/publishers/google/models/{GEMINI}:generateContent")

DIR = "rag-r7-scorecard"
OUT = os.path.join(DIR, "results_judgments.jsonl")
CARD = os.path.join(DIR, "scorecard.md")

SOURCES = {
    "R1 naive": os.path.join("rag-r1-naive", "results_naive.jsonl"),
    "R2 agentic": os.path.join("rag-r2-agentic", "results_agentic.jsonl"),
    "R3 corrective": os.path.join("rag-r3-corrective", "results_corrective.jsonl"),
    "R4 baseline": os.path.join("rag-r4-fusion-hyde", "results_fusion_hyde.jsonl"),
    "R4 fusion": os.path.join("rag-r4-fusion-hyde", "results_fusion_hyde.jsonl"),
    "R4 hyde": os.path.join("rag-r4-fusion-hyde", "results_fusion_hyde.jsonl"),
    "R5 vision": os.path.join("rag-r5-multimodal", "results_multimodal.jsonl"),
    "R6 graph": os.path.join("rag-r6-graph", "results_graph.jsonl"),
}

# Estimated work per question: (search calls, Gemini calls). Design based, not measured.
# R1 uses the managed summary, so its one search call includes the generation.
EST = {
    "R1 naive": (1, 0), "R2 agentic": (2, 3), "R3 corrective": (1.4, 3.4),
    "R4 baseline": (1, 1), "R4 fusion": (4, 2), "R4 hyde": (1, 2), "R5 vision": (1, 1), "R6 graph": (0, 2),
}


def token():
    return subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True,
        shell=(os.name == "nt"),
    ).strip()


def _post(url, body, tok, retries=6):
    data = json.dumps(body).encode()
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": PROJECT,
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = 30 * (attempt + 1)
                print(f"    429 quota, backing off {wait}s ...")
                time.sleep(wait)
                continue
            raise
        except OSError:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise


JUDGE_SYS = (
    "You are a strict, consistent grader of question answering. You get a question, the "
    "gold answer, whether the question is answerable from the company documents, and a "
    "candidate answer. Return JSON only: "
    '{"correct":true|false,"contradicts_gold":true|false,"refused":true|false,"note":"<=12 words"}\n'
    "Rules:\n"
    "- refused is true if the candidate declines or says the information is not available, "
    "or is empty.\n"
    "- For an answerable question, correct is true only if the candidate states the facts "
    "in the gold answer (wording may differ, all key numbers and names must match). A "
    "partial answer missing a key fact is false.\n"
    "- For an unanswerable question, correct is true only if the candidate refuses and "
    "does not invent an answer.\n"
    "- contradicts_gold is true if the candidate states a fact that conflicts with the gold "
    "answer or invents a specific fact (number, name, date) not in the gold answer."
)


def judge(q, answer, tok):
    prompt = (f"Question: {q['question']}\nGold answer: {q['gold_answer']}\n"
              f"Answerable: {'yes' if q['answerable'] else 'no'}\n"
              f"Candidate answer: {answer.strip() or '(empty)'}")
    err = None
    for budget in (2048, 4096):
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": JUDGE_SYS}]},
            "generationConfig": {"temperature": 0, "maxOutputTokens": budget,
                                 "responseMimeType": "application/json"},
        }
        try:
            resp = _post(GEMINI_URL, body, tok)
            parts = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            raw = "".join(p.get("text", "") for p in parts).strip()
            j = json.loads(raw)
            return {"correct": bool(j["correct"]), "contradicts_gold": bool(j["contradicts_gold"]),
                    "refused": bool(j["refused"]), "note": str(j.get("note", ""))[:120],
                    "judge_error": None}
        except urllib.error.HTTPError as e:
            if e.code != 403:
                raise
            # safety filter rejection, benign content so likely spurious: wait and retry
            err = "HTTP 403 policy rejection"
            time.sleep(20)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
    return {"correct": None, "contradicts_gold": None, "refused": None, "note": "",
            "judge_error": err}


def load(path):
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                r = json.loads(line)
                rows[r["id"]] = r
    return rows


def candidate(pattern, rec):
    """Pull the pattern's final answer out of its record."""
    if pattern == "R4 baseline":
        return (rec.get("baseline") or {}).get("answer")
    if pattern == "R4 fusion":
        return (rec.get("fusion") or {}).get("answer")
    if pattern == "R4 hyde":
        return (rec.get("hyde") or {}).get("answer")
    if pattern == "R5 vision":
        arm = rec.get("C_vision") or (rec.get("arms") or {}).get("C_vision")
        return (arm or {}).get("answer")
    return rec.get("answer")


def main():
    os.makedirs(DIR, exist_ok=True)
    qs = load(os.path.join("rag-lab", "r0-foundation", "questions.jsonl"))
    if not qs:
        # questions file is jsonl with an id per line, load() handles that
        raise SystemExit("questions.jsonl not found at rag-lab\\r0-foundation")

    done = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    done[(r["pattern"], r["id"])] = r
    if done:
        print(f"resuming, {len(done)} judgments already recorded")

    todo = []
    for pattern, path in SOURCES.items():
        recs = load(path)
        if not recs:
            print(f"  WARNING no records for {pattern} at {path}")
        for qid, rec in recs.items():
            if (pattern, qid) in done or qid not in qs:
                continue
            ans = candidate(pattern, rec)
            if ans is None:
                continue
            todo.append((pattern, qs[qid], ans))
    print(f"{len(todo)} answers to judge")

    results = list(done.values())
    for i, (pattern, q, ans) in enumerate(todo):
        if i:
            time.sleep(THROTTLE)
        tok = token()
        try:
            j = judge(q, ans, tok)
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:400] if hasattr(e, "read") else ""
            print(f"{pattern:<14} {q['id']} ERROR {e.code} {detail}")
            if e.code == 401:
                print(f"project={PROJECT} location={LOCATION} model={GEMINI}")
                print("auth or permission problem, stopping so the cause is visible")
                break
            continue
        except Exception as e:
            print(f"{pattern:<14} {q['id']} ERROR {type(e).__name__}: {e}")
            continue
        results.append({"pattern": pattern, "id": q["id"], "answerable": q["answerable"],
                        "qpattern": q["pattern"], "answer": ans[:400], **j})
        flag = "ERR" if j["judge_error"] else ("ok" if j["correct"] else "NO")
        print(f"{pattern:<14} {q['id']} {flag:<3} refused={j['refused']} {j['note']}")
        with open(OUT, "w", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps(r) + "\n")

    with open(OUT, "w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")

    # ---- scorecard ----------------------------------------------------------------
    lines = ["| pattern | n | good on answerable | false refusals | contradicts gold | "
             "correct refusals | invented answers | est search calls | est Gemini calls |",
             "|---|---|---|---|---|---|---|---|---|"]
    for pattern in SOURCES:
        rs = [r for r in results if r["pattern"] == pattern and not r["judge_error"]]
        if not rs:
            continue
        a = [r for r in rs if r["answerable"]]
        u = [r for r in rs if not r["answerable"]]
        good = sum(1 for r in a if r["correct"] and not r["contradicts_gold"])
        fref = sum(1 for r in a if r["refused"])
        contra = sum(1 for r in a if r["contradicts_gold"])
        cref = sum(1 for r in u if r["refused"])
        inv = sum(1 for r in u if not r["refused"])
        s, g = EST[pattern]
        lines.append(f"| {pattern} | {len(rs)} | {good}/{len(a)} | {fref} | {contra} | "
                     f"{cref}/{len(u)} | {inv} | {s} | {g} |")
    errs = [(r["pattern"], r["id"]) for r in results if r["judge_error"]]
    lines.append("")
    lines.append(f"judge errors: {errs if errs else 'none'}")
    lines.append("Call counts are design based estimates, not measured.")
    lines.append("R5 vision covers only the 5 multimodal and unanswerable questions it ran.")
    card = "\n".join(lines)
    with open(CARD, "w", encoding="utf-8") as fh:
        fh.write(card + "\n")
    print("\n" + card)

    # ---- by question pattern: where does each approach win -----------------------
    print("\ngood answers by question type (answerable only):")
    types = sorted({r["qpattern"] for r in results if r["answerable"]})
    print(f"{'pattern':<14} " + " ".join(f"{t[:10]:>10}" for t in types))
    for pattern in SOURCES:
        row = []
        for t in types:
            rs = [r for r in results if r["pattern"] == pattern and r["answerable"]
                  and r["qpattern"] == t and not r["judge_error"]]
            g = sum(1 for r in rs if r["correct"] and not r["contradicts_gold"])
            row.append(f"{g}/{len(rs)}" if rs else "-")
        print(f"{pattern:<14} " + " ".join(f"{x:>10}" for x in row))

    # ---- sample for the hand check -----------------------------------------------
    random.seed(7)
    sample = random.sample([r for r in results if not r["judge_error"]], min(6, len(results)))
    print("\nhand check these 6, judge verdict vs the answer text:")
    for r in sample:
        print(f"- {r['pattern']} {r['id']} judged correct={r['correct']} "
              f"contradicts={r['contradicts_gold']} refused={r['refused']}")
        print(f"    answer: {r['answer'][:160].replace(chr(10), ' ')}")
    print(f"\nsaved {OUT} and {CARD}")


if __name__ == "__main__":
    main()
