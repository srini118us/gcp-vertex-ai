"""R4 Fusion and HyDE runner.

Both techniques rewrite the query in front of the same meridian-search engine. The
index does not change. For each of the 22 R0 questions the runner executes three
retrievals and logs where the gold document ranks in each:

  baseline  the original question, one search (same as R1)
  fusion    the LLM writes N query variants, all variants plus the original retrieve
            in parallel, and the ranked lists merge by Reciprocal Rank Fusion
            (score = sum of 1 / (k + rank) across lists, k = 60)
  hyde      the LLM writes a hypothetical answer passage and that passage is used
            as the search query

Metrics per method: hit@5 (gold doc in the top 5), gold rank (1 is best, None if
missing), and mean reciprocal rank (MRR) across answerable questions. An answer is
also synthesized from each method's top chunks so refusal behavior can be compared.

Run from the repo root, after the R1 engine exists:
    python rag-r4-fusion-hyde\\query_fusion_hyde.py

Env knobs: RAG_THROTTLE (default 4), RAG_LIMIT, RAG_VARIANTS (default 3),
RAG_PROJECT, RAG_ENGINE, RAG_LOCATION (default global),
RAG_GEMINI (default gemini-3.8-flash).

Outputs rag-r4-fusion-hyde\\results_fusion_hyde.jsonl and prints a table. Reruns
resume from the jsonl, so only missing questions run again.
"""
import json
import os
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
N_VARIANTS = int(os.getenv("RAG_VARIANTS", "3"))
RRF_K = 60
TOP_K = 5

COL = (f"https://discoveryengine.googleapis.com/v1/projects/{PROJECT}"
       f"/locations/global/collections/default_collection")
SEARCH_URL = f"{COL}/engines/{ENGINE}/servingConfigs/default_search:search"

_host = "aiplatform.googleapis.com" if LOCATION == "global" else f"{LOCATION}-aiplatform.googleapis.com"
GEMINI_URL = (f"https://{_host}/v1/projects/{PROJECT}/locations/{LOCATION}"
              f"/publishers/google/models/{GEMINI}:generateContent")

QUESTIONS = os.path.join("rag-lab", "r0-foundation", "questions.jsonl")
OUT = os.path.join("rag-r4-fusion-hyde", "results_fusion_hyde.jsonl")


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
    """Ranked list of {doc, text}, best first, one entry per document."""
    body = {
        "query": query[:1500],
        "pageSize": TOP_K,
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
    return items


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


# --- query rewrites ---------------------------------------------------------------

VARIANT_SYS = (
    "Rewrite the user question into different search queries for a knowledge base about "
    "an appliance company (products, warranty, returns, pricing, recalls, support). "
    "Keep the meaning, change the wording and vocabulary, use synonyms and the terms a "
    "document would use. Return JSON only: "
    '{"queries":["...","..."]}'
)


def make_variants(question, tok):
    """Returns (variants, error). A reasoning model spends part of the output budget on
    thinking, so a small limit truncates the JSON. Use a large budget, retry once with a
    larger one, and record the error instead of silently returning nothing."""
    prompt = f"Write {N_VARIANTS} alternative search queries for: {question}"
    err = None
    for budget in (2048, 4096):
        try:
            raw = gemini(prompt, tok, system=VARIANT_SYS, as_json=True, max_tokens=budget)
            qs = [q for q in json.loads(raw).get("queries", []) if isinstance(q, str) and q.strip()]
            if qs:
                return qs[:N_VARIANTS], None
            err = "empty variant list"
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
    return [], err


HYDE_SYS = (
    "Write a short passage, two or three sentences, in the style of an appliance company "
    "policy or product document that would answer the question. State it plainly as fact. "
    "It is only used to guide a search, so do not hedge and do not mention the question."
)


def make_hyde(question, tok):
    passage = gemini(question, tok, system=HYDE_SYS, max_tokens=1024)
    return passage or question


# --- fusion -----------------------------------------------------------------------

def rrf(ranked_lists):
    """Reciprocal Rank Fusion over lists of items. Returns fused list, best first,
    carrying the longest text seen for each doc."""
    score, text = {}, {}
    for lst in ranked_lists:
        for rank, it in enumerate(lst, start=1):
            score[it["doc"]] = score.get(it["doc"], 0.0) + 1.0 / (RRF_K + rank)
            if len(it["text"]) > len(text.get(it["doc"], "")):
                text[it["doc"]] = it["text"]
    order = sorted(score, key=lambda d: (-score[d], d))
    return [{"doc": d, "text": text[d], "score": round(score[d], 5)} for d in order]


# --- answer and scoring -----------------------------------------------------------

SYNTH_SYS = (
    "Answer only from the provided snippets. If they do not contain the answer, say "
    "the information is not available in the sources. Be concise. Cite doc ids in "
    "square brackets."
)


def synthesize(question, items, tok):
    ctx = "\n".join(f"[{it['doc']}] {it['text']}" for it in items if it["text"])
    if not ctx:
        return "the information is not available in the sources"
    prompt = f"Question: {question}\n\nSnippets:\n{ctx}\n\nAnswer:"
    return gemini(prompt, tok, system=SYNTH_SYS, max_tokens=512)


def gold_rank(items, gold):
    for i, it in enumerate(items, start=1):
        if it["doc"] in gold:
            return i
    return None


def refused(answer):
    a = answer.lower()
    return ("not available" in a or "do not contain" in a or "does not contain" in a
            or "no information" in a or "not contain" in a)


def run_question(q, tok):
    question = q["question"]
    gold = {base(s) for s in q.get("gold_sources", [])}

    # baseline, the original question
    base_items = retrieve(question, tok)[:TOP_K]

    # fusion, original plus variants, in parallel, then RRF
    variants, variant_error = make_variants(question, tok)
    queries = [question] + variants
    with ThreadPoolExecutor(max_workers=min(4, len(queries))) as ex:
        lists = list(ex.map(lambda x: retrieve(x, tok), queries))
    fused = rrf(lists)[:TOP_K]

    # hyde, hypothetical passage as the query
    passage = make_hyde(question, tok)
    hyde_items = retrieve(passage, tok)[:TOP_K]

    out = {
        "variants": variants,
        "variant_error": variant_error,
        "hyde_passage": passage,
        "baseline": {"docs": [i["doc"] for i in base_items]},
        "fusion": {"docs": [i["doc"] for i in fused], "n_queries": len(queries)},
        "hyde": {"docs": [i["doc"] for i in hyde_items]},
    }
    for name, items in (("baseline", base_items), ("fusion", fused), ("hyde", hyde_items)):
        out[name]["gold_rank"] = gold_rank(items, gold) if q["answerable"] else None
        out[name]["hit"] = (out[name]["gold_rank"] is not None) if q["answerable"] else None
        out[name]["answer"] = synthesize(question, items, tok)
        out[name]["refused"] = refused(out[name]["answer"])
    return out


def fmt_rank(r):
    return "-" if r is None else str(r)


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
    print(f"{'id':>4} | {'pattern':<11} | gold rank: base fus hyde | hit: base fus hyde | fusion answer")
    print("-" * 112)
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

        def h(m):
            v = out[m]["hit"]
            return "n/a" if v is None else ("yes" if v else "NO")
        ans = out["fusion"]["answer"].replace("\n", " ")[:30]
        print(f"{q['id']:>4} | {q['pattern']:<11} | "
              f"{fmt_rank(out['baseline']['gold_rank']):>13} {fmt_rank(out['fusion']['gold_rank']):>3} "
              f"{fmt_rank(out['hyde']['gold_rank']):>4} | "
              f"{h('baseline'):>9} {h('fusion'):>3} {h('hyde'):>4} | v={len(out['variants'])} | {ans}")

    results.sort(key=lambda r: r["id"])
    with open(OUT, "w", encoding="utf-8") as fh:
        for rec in results:
            fh.write(json.dumps(rec) + "\n")

    answerable = [r for r in results if r["answerable"]]
    unans = [r for r in results if not r["answerable"]]
    print("-" * 112)
    print(f"{'method':<10} | hit@5 on answerable | MRR   | refused unanswerable | refused answerable (false refusals)")
    for m in ("baseline", "fusion", "hyde"):
        hits = sum(1 for r in answerable if r[m]["hit"])
        mrr = (sum(1.0 / r[m]["gold_rank"] for r in answerable if r[m]["gold_rank"])
               / len(answerable)) if answerable else 0.0
        ref_ok = sum(1 for r in unans if r[m]["refused"])
        false_ref = sum(1 for r in answerable if r[m]["refused"])
        print(f"{m:<10} | {hits:>2}/{len(answerable):<17} | {mrr:.3f} | "
              f"{ref_ok:>2}/{len(unans):<18} | {false_ref}")
    no_var = [r["id"] for r in results if not r["variants"]]
    print(f"questions with zero variants (fusion equals baseline there): {no_var if no_var else 'none'}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
