"""R2 Agentic RAG runner (v2).

Wraps a reasoning loop around the same meridian-search engine from R1. For each of
the 22 R0 questions it:
  1. plans, Gemini decomposes the question into sub queries, each flagged independent
     or dependent (depends_on),
  2. executes, independent sub queries run in parallel, dependent ones chain and are
     reformed from the earlier result,
  3. synthesizes, Gemini composes the final answer from the gathered snippets,
and logs which sub queries ran in parallel versus in sequence, the union of retrieved
docs, a retrieval hit flag against gold, and the answer.

Retrieval backend is unchanged from R1, so table misses (q05 to q07) are expected to
stay missed. Agentic helps where one query was not enough, the compound and multi hop
questions, which the planner must actually split.

Run from the repo root, after the R1 engine exists:
    python rag-r2-agentic\\query_agentic.py

Env knobs:
    RAG_THROTTLE   seconds between questions, default 4
    RAG_LIMIT      run only the first N questions, for a cheap smoke test
    RAG_PROJECT    default enterprise-agent-labs-1012
    RAG_ENGINE     default meridian-search
    RAG_LOCATION   Gemini location, default global
    RAG_GEMINI     Gemini model, default gemini-3.8-flash

Outputs rag-r2-agentic\\results_agentic.jsonl and prints a table.
"""
import json
import os
import re
import subprocess
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

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
OUT = os.path.join("rag-r2-agentic", "results_agentic.jsonl")


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
            # URLError, connection reset, or a read TimeoutError, all transient.
            # back off and retry.
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise


def base(name):
    return os.path.splitext(os.path.basename(name))[0]


# --- retrieval, the same meridian-search engine as R1 -----------------------------

def retrieve(query, tok):
    """Return per doc text aligned to its doc id, so the synthesizer gets real
    context. Pulls snippets, extractive answers, and extractive segments."""
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


# --- Gemini, the orchestrator -----------------------------------------------------

def gemini(prompt, tok, system=None, as_json=False, max_tokens=1024):
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


PLAN_SYS = (
    "You plan retrieval for a question answering system over a small appliance company "
    "knowledge base (Meridian: product catalog, warranty, returns, pricing, recalls, "
    "support, company overview).\n"
    "Split the question into the minimum set of search queries. Two rules:\n"
    "- If the question asks about two or more separate facts, make one query per fact "
    "(they are independent, depends_on null, and will run in parallel).\n"
    "- If a query needs the ANSWER of an earlier query before it can be written (a "
    "chain), set depends_on to that query's id.\n"
    "A simple single fact question is one query. Return JSON only.\n\n"
    "Example, simple:\n"
    "Q: What is the warranty on the DX500 dishwasher?\n"
    '{"subqueries":[{"id":"s1","query":"DX500 dishwasher warranty","depends_on":null}]}\n\n'
    "Example, compound (two independent facts):\n"
    "Q: Can I return the FR900 and is it affected by the recall?\n"
    '{"subqueries":[{"id":"s1","query":"FR900 return policy","depends_on":null},'
    '{"id":"s2","query":"FR900 recall status","depends_on":null}]}\n\n'
    "Example, multi hop (second query needs the first answer):\n"
    "Q: Which other products use the part that was recalled in the AC300?\n"
    '{"subqueries":[{"id":"s1","query":"AC300 recall affected part","depends_on":null},'
    '{"id":"s2","query":"products that use the recalled part","depends_on":"s1"}]}'
)


def _as_list(v):
    if v is None or v == "":
        return []
    return v if isinstance(v, list) else [v]


def plan(question, tok):
    """Returns (subs, info). The planner is a reasoning model, thinking tokens eat the
    output budget, so try 2048 then 4096. If both fail the question falls back to the
    verbatim single query, and info records that so the fallback can be audited."""
    err = None
    for budget in (2048, 4096):
        try:
            raw = gemini(question, tok, system=PLAN_SYS, as_json=True, max_tokens=budget)
            subs = json.loads(raw).get("subqueries", [])
            subs = [s for s in subs if s.get("query")][:5]
            if not subs:
                raise ValueError("planner returned no sub queries")
            for s in subs:
                s["depends_on"] = _as_list(s.get("depends_on"))
            if len(subs) == 1:
                # no decomposition happened, so use the baseline query verbatim.
                # this isolates the variable under test, R2 differs from R1 only
                # where the planner actually splits the question.
                subs[0]["query"] = question
                subs[0]["depends_on"] = []
            return subs, {"plan_error": None, "fell_back": False, "plan_budget": budget}
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:200]
    return ([{"id": "s1", "query": question, "depends_on": []}],
            {"plan_error": err, "fell_back": True, "plan_budget": None})


def reform(question, dep_texts, tok):
    prompt = (f"Question: {question}\n\nContext from earlier searches:\n"
              + "\n".join(dep_texts[:4])
              + "\n\nWrite the single best next search query to answer the remaining "
                "part. Return only the query text.")
    q = gemini(prompt, tok, max_tokens=1024)
    first = q.splitlines()[0] if q else question
    return re.sub(r'^["\']|["\']$', "", first).strip() or question


SYNTH_SYS = (
    "Answer only from the provided snippets. If they do not contain the answer, say "
    "the information is not available in the sources. Be concise. Cite the doc ids in "
    "square brackets."
)


def synthesize(question, gathered, tok):
    ctx = "\n".join(f"[{d}] {t}" for d, t in gathered if t)
    prompt = f"Question: {question}\n\nSnippets:\n{ctx}\n\nAnswer:"
    return gemini(prompt, tok, system=SYNTH_SYS, max_tokens=512)


def run_question(q, tok):
    subs, plan_info = plan(q["question"], tok)
    independent = [s for s in subs if not s["depends_on"]]
    dependent = [s for s in subs if s["depends_on"]]

    results = {}
    log = []

    # independent sub queries, in parallel
    t0 = time.time()
    if independent:
        with ThreadPoolExecutor(max_workers=min(4, len(independent))) as ex:
            futs = {ex.submit(retrieve, s["query"], tok): s for s in independent}
            for fut, s in futs.items():
                results[s["id"]] = fut.result()
    par_elapsed = round(time.time() - t0, 2)
    for s in independent:
        log.append({"id": s["id"], "query": s["query"], "mode": "parallel"})

    # dependent sub queries, chained, reformed from the dependency's text
    for s in dependent:
        dep_texts = []
        for dep_id in s["depends_on"]:
            for it in results.get(dep_id, {}).get("items", []):
                if it["text"]:
                    dep_texts.append(it["text"])
        q_text = reform(q["question"], dep_texts, tok)
        t1 = time.time()
        results[s["id"]] = retrieve(q_text, tok)
        log.append({"id": s["id"], "query": q_text, "mode": "sequential",
                    "depends_on": s["depends_on"], "latency_s": round(time.time() - t1, 2)})

    # gather and synthesize
    gathered, union_docs = [], []
    for r in results.values():
        union_docs += r["docs"]
        for it in r["items"]:
            if it["text"]:
                gathered.append((it["doc"], it["text"]))
    answer = synthesize(q["question"], gathered, tok) if gathered else \
        "the information is not available in the sources"

    gold = {base(s) for s in q.get("gold_sources", [])}
    hit = bool(gold & set(union_docs)) if q["answerable"] else None
    return {
        **plan_info,
        "subqueries": log, "parallel_count": len(independent),
        "sequential_count": len(dependent), "parallel_elapsed_s": par_elapsed,
        "retrieved": sorted(set(union_docs)), "retrieval_hit": hit, "answer": answer,
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

    # resume: keep questions already recorded, only run the ones still missing
    done = {}
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    done[r["id"]] = r
    if done:
        print(f"resuming, {len(done)} questions already recorded, running the rest")

    results = list(done.values())
    todo = [q for q in rows if q["id"] not in done]
    print(f"{'id':>4} | {'pattern':<11} | sub | par/seq | hit | answer")
    print("-" * 100)
    for i, q in enumerate(todo):
        if i:
            time.sleep(THROTTLE)
        tok = token()  # fresh token per question, a long run outlives one access token
        try:
            out = run_question(q, tok)
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:160] if hasattr(e, "read") else ""
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
        nsub = len(out["subqueries"])
        ps = f"{out['parallel_count']}/{out['sequential_count']}"
        ans = (out["answer"] or "").replace("\n", " ")[:46]
        print(f"{q['id']:>4} | {q['pattern']:<11} | {nsub:>3} | {ps:>7} | {hit_s:>3} | {ans}")

    results.sort(key=lambda r: r["id"])
    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in results:
            fh.write(json.dumps(rec) + "\n")

    answerable = [r for r in results if r["answerable"]]
    hits = sum(1 for r in answerable if r["retrieval_hit"])
    multi = sum(1 for r in results if r["sequential_count"])
    decomposed = sum(1 for r in results if len(r["subqueries"]) > 1)
    print("-" * 100)
    print(f"retrieval hit on answerable questions: {hits}/{len(answerable)}")
    print(f"questions decomposed into more than one sub query: {decomposed}/{len(results)}")
    print(f"questions that used a sequential chain: {multi}/{len(results)}")
    fb = [r["id"] for r in results if r.get("fell_back")]
    print(f"planner fell back to the single verbatim query: {fb if fb else 'none'}")
    for r in results:
        if r.get("plan_error"):
            print(f"  {r['id']}: {r['plan_error']}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
