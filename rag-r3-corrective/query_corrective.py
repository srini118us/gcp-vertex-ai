"""R3 Corrective RAG (CRAG) runner.

Adds a relevance grader between retrieve and generate over the same meridian-search
engine. For each of the 22 R0 questions it:
  1. retrieves the top chunks from the engine,
  2. grades each chunk for relevance to the question (Gemini),
  3. if nothing is relevant, runs one corrective re retrieve with a reformed query,
  4. synthesizes only from the relevant chunks, or refuses if none are relevant.

The point of CRAG is to make refusal deliberate. Naive RAG refuses the unanswerable
questions only because the engine happened to return nothing. The grader refuses even
when the engine returns chunks that do not actually answer, which is the real world
case, retrieved but irrelevant.

Metrics logged:
  retrieval_hit  gold doc among everything retrieved (recall, same as R1)
  relevant_hit   gold doc among the chunks the grader KEPT (grounding quality)
  refused        the grader found nothing relevant and declined
  corrected      a corrective re retrieve was triggered

Run from the repo root, after the R1 engine exists:
    python rag-r3-corrective\\query_corrective.py

Env knobs: RAG_THROTTLE (default 4), RAG_LIMIT, RAG_PROJECT, RAG_ENGINE,
RAG_LOCATION (default global), RAG_GEMINI (default gemini-3.8-flash).

Outputs rag-r3-corrective\\results_corrective.jsonl and prints a table.
"""
import json
import os
import subprocess
import time
import urllib.request
import urllib.error

PROJECT = os.getenv("RAG_PROJECT", "enterprise-agent-labs-1012")
ENGINE = os.getenv("RAG_ENGINE", "meridian-search")
LOCATION = os.getenv("RAG_LOCATION", "global")
GEMINI = os.getenv("RAG_GEMINI", "gemini-3.8-flash")
THROTTLE = float(os.getenv("RAG_THROTTLE", "4"))
LIMIT = int(os.getenv("RAG_LIMIT", "0"))

COL = (f"https://discoveryengine.googleapis.com/v1/projects/{PROJECT}"
       f"/locations/global/collections/default_collection")
SEARCH_URL = f"{COL}/engines/{ENGINE}/servingConfigs/default_search:search"

_host = "aiplatform.googleapis.com" if LOCATION == "global" else f"{LOCATION}-aiplatform.googleapis.com"
GEMINI_URL = (f"https://{_host}/v1/projects/{PROJECT}/locations/{LOCATION}"
              f"/publishers/google/models/{GEMINI}:generateContent")

QUESTIONS = os.path.join("rag-lab", "r0-foundation", "questions.jsonl")
OUT = os.path.join("rag-r3-corrective", "results_corrective.jsonl")


def token():
    return subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True,
        shell=(os.name == "nt"),
    ).strip()


def _post(url, body, tok, retries=5):
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
                time.sleep(20 * (attempt + 1))
                continue
            raise
        except OSError:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise


def base(name):
    return os.path.splitext(os.path.basename(name))[0]


def retrieve(query, tok):
    body = {
        "query": query,
        "pageSize": 5,
        "contentSearchSpec": {
            "snippetSpec": {"returnSnippet": True},
            "extractiveContentSpec": {
                "maxExtractiveAnswerCount": 2,
                "maxExtractiveSegmentCount": 1,
            },
        },
    }
    resp = _post(SEARCH_URL, body, tok)
    items = []
    for res in resp.get("results", []):
        d = res.get("document", {})
        dsd = d.get("derivedStructData", {})
        link = dsd.get("link", "") or d.get("id", "")
        doc = base(link) if link else d.get("id", "")
        texts = []
        for s in dsd.get("snippets", []):
            if s.get("snippet") and s.get("snippet_status") != "NO_SNIPPET_AVAILABLE":
                texts.append(s["snippet"])
        for a in dsd.get("extractive_answers", []):
            if a.get("content"):
                texts.append(a["content"])
        for seg in dsd.get("extractive_segments", []):
            if seg.get("content"):
                texts.append(seg["content"])
        items.append({"doc": doc, "text": " ".join(texts).strip()})
    return {"docs": [it["doc"] for it in items], "items": items}


def gemini(prompt, tok, system=None, as_json=False, max_tokens=512):
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if as_json:
        body["generationConfig"]["responseMimeType"] = "application/json"
    resp = _post(GEMINI_URL, body, tok)
    parts = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


# --- the corrective pieces --------------------------------------------------------

GRADE_SYS = (
    "You grade whether each retrieved snippet is relevant to answering the question. "
    "A snippet is relevant only if it contains information that directly helps answer "
    "the specific question asked. Be strict: loosely related, same topic but different "
    "fact, is NOT relevant. Return JSON only: "
    '{"grades":[{"i":0,"relevant":true}]}'
)


def grade(question, items, tok):
    """Returns (relevant_index_set, info). Reasoning model, thinking tokens eat the output
    budget, so try 2048 then 4096. If both fail, fall back to all chunks (behave like
    naive) and flag it in info so the fallback can be audited."""
    if not items:
        return set(), {"grade_error": None, "grade_fell_back": False}
    listing = "\n".join(f"[{i}] ({it['doc']}) {it['text'][:400]}"
                        for i, it in enumerate(items))
    prompt = f"Question: {question}\n\nSnippets:\n{listing}\n\nGrade each snippet by index."
    err = None
    for budget in (2048, 4096):
        try:
            raw = gemini(prompt, tok, system=GRADE_SYS, as_json=True, max_tokens=budget)
            grades = json.loads(raw).get("grades", [])
            if not isinstance(grades, list) or not grades:
                raise ValueError("grader returned no grades")
            rel = {g["i"] for g in grades if g.get("relevant") and isinstance(g.get("i"), int)}
            return rel, {"grade_error": None, "grade_fell_back": False}
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
    return set(range(len(items))), {"grade_error": err, "grade_fell_back": True}


def reformulate(question, tok):
    """Returns (query, error). error is set when the rewrite failed and the original
    question was reused."""
    prompt = (f"A search for this question returned nothing relevant: {question}\n"
              "Rewrite it as a different search query using alternative terms. "
              "Return only the query text.")
    q = gemini(prompt, tok, max_tokens=1024)
    first = q.splitlines()[0] if q else ""
    newq = first.strip().strip('"\'')
    if not newq:
        return question, "empty reformulation, reused the original question"
    return newq, None


SYNTH_SYS = (
    "Answer only from the provided snippets. If they do not contain the answer, say "
    "the information is not available in the sources. Be concise. Cite doc ids in "
    "square brackets."
)


def synthesize(question, gathered, tok):
    ctx = "\n".join(f"[{d}] {t}" for d, t in gathered if t)
    prompt = f"Question: {question}\n\nSnippets:\n{ctx}\n\nAnswer:"
    return gemini(prompt, tok, system=SYNTH_SYS, max_tokens=512)


def run_question(q, tok):
    r = retrieve(q["question"], tok)
    items = r["items"]
    rel_idx, ginfo = grade(q["question"], items, tok)
    all_docs = list(r["docs"])
    corrected = False
    reform_error = None

    # corrective action: if nothing graded relevant, reform the query and retry once
    if not rel_idx:
        corrected = True
        newq, reform_error = reformulate(q["question"], tok)
        r2 = retrieve(newq, tok)
        items = r2["items"]
        rel_idx, ginfo2 = grade(q["question"], items, tok)
        all_docs += r2["docs"]
        if ginfo2["grade_fell_back"]:
            ginfo = ginfo2
        elif ginfo["grade_fell_back"] is False:
            ginfo = ginfo2

    relevant = [items[i] for i in sorted(rel_idx) if i < len(items)]
    refused = len(relevant) == 0
    answer = ("the information is not available in the sources" if refused
              else synthesize(q["question"], [(it["doc"], it["text"]) for it in relevant], tok))

    relevant_docs = sorted({it["doc"] for it in relevant})
    gold = {base(s) for s in q.get("gold_sources", [])}
    union = set(all_docs)
    return {
        **ginfo, "reform_error": reform_error,
        "n_retrieved": len(union), "n_relevant": len(relevant), "corrected": corrected,
        "refused": refused, "retrieved": sorted(union), "relevant_docs": relevant_docs,
        "retrieval_hit": (bool(gold & union) if q["answerable"] else None),
        "relevant_hit": (bool(gold & set(relevant_docs)) if q["answerable"] else None),
        "answer": answer,
    }


def main():
    tok = token()
    rows = []
    with open(QUESTIONS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if LIMIT:
        rows = rows[:LIMIT]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    done = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    done[rec["id"]] = rec
    if done:
        print(f"resuming, {len(done)} questions already recorded, running the rest")

    results = list(done.values())
    todo = [q for q in rows if q["id"] not in done]
    print(f"{'id':>4} | {'pattern':<11} | ret | rel | corr | refused | hit | relhit | answer")
    print("-" * 108)
    for i, q in enumerate(todo):
        if i:
            time.sleep(THROTTLE)
        tok = token()  # fresh token per question, a long run outlives one access token
        try:
            out = run_question(q, tok)
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:140] if hasattr(e, "read") else ""
            print(f"{q['id']:>4} | ERROR {e.code} {detail}")
            continue
        except Exception as e:
            print(f"{q['id']:>4} | ERROR {type(e).__name__}: {e}")
            continue
        rec = {
            "id": q["id"], "pattern": q["pattern"], "difficulty": q["difficulty"],
            "answerable": q["answerable"], "question": q["question"],
            "gold_answer": q["gold_answer"], "gold_sources": q.get("gold_sources", []),
            **out,
        }
        results.append(rec)
        hit_s = "n/a" if out["retrieval_hit"] is None else ("yes" if out["retrieval_hit"] else "NO")
        rh_s = "n/a" if out["relevant_hit"] is None else ("yes" if out["relevant_hit"] else "NO")
        ans = (out["answer"] or "").replace("\n", " ")[:34]
        print(f"{q['id']:>4} | {q['pattern']:<11} | {out['n_retrieved']:>3} | "
              f"{out['n_relevant']:>3} | {'yes' if out['corrected'] else '  .':>4} | "
              f"{'yes' if out['refused'] else '  .':>7} | {hit_s:>3} | {rh_s:>6} | {ans}")

    results.sort(key=lambda r: r["id"])
    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in results:
            fh.write(json.dumps(rec) + "\n")

    answerable = [r for r in results if r["answerable"]]
    unans = [r for r in results if not r["answerable"]]
    rhit = sum(1 for r in answerable if r["retrieval_hit"])
    relhit = sum(1 for r in answerable if r["relevant_hit"])
    refused_ok = sum(1 for r in unans if r["refused"])
    halluc = sum(1 for r in unans if not r["refused"])
    corr = sum(1 for r in results if r["corrected"])
    print("-" * 108)
    print(f"retrieval hit on answerable (recall):        {rhit}/{len(answerable)}")
    print(f"grader kept the gold doc (relevant hit):     {relhit}/{len(answerable)}")
    print(f"correct refusal on unanswerable:             {refused_ok}/{len(unans)}")
    print(f"answered an unanswerable (should be 0):      {halluc}")
    print(f"corrective re retrieve triggered:            {corr}/{len(results)}")
    gfb = [r["id"] for r in results if r.get("grade_fell_back")]
    print(f"grader failed, fell back to all chunks:      {gfb if gfb else 'none'}")
    rfe = [r["id"] for r in results if r.get("reform_error")]
    print(f"reformulation failed, reused question:       {rfe if rfe else 'none'}")
    for r in results:
        if r.get("grade_error"):
            print(f"  {r['id']}: {r['grade_error']}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
