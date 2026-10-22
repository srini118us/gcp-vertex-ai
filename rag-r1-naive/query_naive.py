"""R1 Naive baseline runner (v2, throttled).

Fires each of the 22 R0 questions at the Vertex AI Search engine with a summary
spec, logging the answer, retrieved documents, a retrieval hit flag, and, when the
summary is empty, the skip reason. Throttles between queries and backs off on 429,
since the LLM summary has a low per minute quota on a new project.

Run from the repo root, after the engine exists:
    python rag-r1-naive\\query_naive.py

Env knobs: RAG_THROTTLE (seconds between queries, default 5),
RAG_PROJECT, RAG_ENGINE.

Outputs rag-r1-naive\\results_naive.jsonl and prints a table.
"""
import json
import os
import subprocess
import time
import urllib.request
import urllib.error

PROJECT = os.getenv("RAG_PROJECT", "enterprise-agent-labs-1012")
ENGINE = os.getenv("RAG_ENGINE", "meridian-search")
THROTTLE = float(os.getenv("RAG_THROTTLE", "5"))
COL = (f"https://discoveryengine.googleapis.com/v1/projects/{PROJECT}"
       f"/locations/global/collections/default_collection")
SEARCH_URL = f"{COL}/engines/{ENGINE}/servingConfigs/default_search:search"

QUESTIONS = os.path.join("rag-lab", "r0-foundation", "questions.jsonl")
OUT = os.path.join("rag-r1-naive", "results_naive.jsonl")


def token():
    return subprocess.check_output(
        ["gcloud", "auth", "print-access-token"], text=True,
        shell=(os.name == "nt"),
    ).strip()


def search(query, tok, retries=4):
    body = {
        "query": query,
        "pageSize": 5,
        "contentSearchSpec": {
            "snippetSpec": {"returnSnippet": True},
            "summarySpec": {
                "summaryResultCount": 5,
                "includeCitations": True,
                "ignoreAdversarialQuery": True,
                "ignoreNonSummarySeekingQuery": False,
            },
        },
    }
    data = json.dumps(body).encode()
    for attempt in range(retries):
        req = urllib.request.Request(SEARCH_URL, data=data, headers={
            "Authorization": f"Bearer {tok}",
            "Content-Type": "application/json",
            "X-Goog-User-Project": PROJECT,
        })
        try:
            with urllib.request.urlopen(req) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = 30 * (attempt + 1)
                print(f"    429 quota, backing off {wait}s ...")
                time.sleep(wait)
                continue
            raise


def base(name):
    return os.path.splitext(os.path.basename(name))[0]


def retrieved_docs(resp):
    docs = []
    for res in resp.get("results", []):
        d = res.get("document", {})
        link = d.get("derivedStructData", {}).get("link", "") or d.get("id", "")
        docs.append(base(link) if link else d.get("id", ""))
    return docs


def main():
    tok = token()
    rows = []
    with open(QUESTIONS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    results = []
    print(f"{'id':>4} | {'pattern':<11} | ans | hit | answer or skip reason")
    print("-" * 95)
    for i, q in enumerate(rows):
        if i:
            time.sleep(THROTTLE)
        try:
            resp = search(q["question"], tok)
        except urllib.error.HTTPError as e:
            print(f"{q['id']:>4} | ERROR {e.code}")
            continue
        summ = resp.get("summary", {})
        answer = summ.get("summaryText", "").strip()
        skipped = summ.get("summarySkippedReasons", [])
        retrieved = retrieved_docs(resp)
        gold = {base(s) for s in q.get("gold_sources", [])}
        hit = bool(gold & set(retrieved)) if q["answerable"] else None
        results.append({
            "id": q["id"], "pattern": q["pattern"], "difficulty": q["difficulty"],
            "answerable": q["answerable"], "question": q["question"],
            "gold_answer": q["gold_answer"], "gold_sources": q.get("gold_sources", []),
            "answer": answer, "summary_skipped": skipped,
            "retrieved": retrieved, "retrieval_hit": hit,
        })
        hit_s = "n/a" if hit is None else ("yes" if hit else "NO")
        ans_s = "Y" if q["answerable"] else "N"
        shown = answer[:52] if answer else ("(skipped: " + ",".join(skipped) + ")" if skipped else "(empty)")
        print(f"{q['id']:>4} | {q['pattern']:<11} | {ans_s:>3} | {hit_s:>3} | {shown}")

    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in results:
            fh.write(json.dumps(rec) + "\n")

    answerable = [r for r in results if r["answerable"]]
    hits = sum(1 for r in answerable if r["retrieval_hit"])
    with_answer = sum(1 for r in results if r["answer"])
    print("-" * 95)
    print(f"retrieval hit on answerable questions: {hits}/{len(answerable)}")
    print(f"questions with a generated answer: {with_answer}/{len(results)}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
