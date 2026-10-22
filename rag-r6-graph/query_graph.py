"""R6 Graph RAG, step 2: answer questions by walking the graph.

For each of the 22 R0 questions:
  1. entity linking, Gemini picks which graph entities the question mentions, choosing
     only from the real entity names in the graph
  2. traversal, a breadth first walk from those entities over the in memory networkx graph,
     up to RAG_HOPS hops, collecting the edges seen. Hub nodes (very high degree) are not
     expanded so a node like the company itself cannot flood the context.
  3. synthesis, Gemini answers only from the collected triples

Metrics: retrieval_hit (a gold document supplied at least one collected triple, same
meaning as R1 to R4), n_triples, hops used, and whether the answer was a refusal.

Run from the repo root, after extract_graph.py:
    python rag-r6-graph\\query_graph.py

Env knobs: RAG_HOPS (default 2), RAG_THROTTLE (default 6), RAG_LIMIT, RAG_PROJECT,
RAG_LOCATION, RAG_GEMINI. Reruns resume from results_graph.jsonl.

Output: rag-r6-graph\\results_graph.jsonl
"""
import json
import os
import subprocess
import time
import urllib.request
import urllib.error

import networkx as nx

PROJECT = os.getenv("RAG_PROJECT", "enterprise-agent-labs-1012")
LOCATION = os.getenv("RAG_LOCATION", "global")
GEMINI = os.getenv("RAG_GEMINI", "gemini-3.8-flash")
THROTTLE = float(os.getenv("RAG_THROTTLE", "6"))
LIMIT = int(os.getenv("RAG_LIMIT", "0"))
HOPS = int(os.getenv("RAG_HOPS", "2"))
HUB_DEGREE = 14
MAX_TRIPLES = 60

_host = "aiplatform.googleapis.com" if LOCATION == "global" else f"{LOCATION}-aiplatform.googleapis.com"
GEMINI_URL = (f"https://{_host}/v1/projects/{PROJECT}/locations/{LOCATION}"
              f"/publishers/google/models/{GEMINI}:generateContent")

QUESTIONS = os.path.join("rag-lab", "r0-foundation", "questions.jsonl")
TRIPLES = os.path.join("rag-r6-graph", "data", "triples.json")
OUT = os.path.join("rag-r6-graph", "results_graph.jsonl")


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


# --- the graph ----------------------------------------------------------------------

def build_graph(triples):
    g = nx.MultiDiGraph()
    for t in triples:
        g.add_edge(t["s"], t["o"], rel=t["r"], doc=t["doc"])
    return g


def traverse(g, starts, hops=HOPS):
    """Breadth first walk from the start entities over the undirected view, keeping edge
    direction in the output. Returns (edges, depth) where edges is a list of
    (subject, relation, object, doc, distance), nearest first."""
    seen_nodes = set(starts)
    seen_edges = {}
    frontier = list(starts)
    for depth in range(1, hops + 1):
        nxt = []
        for node in frontier:
            # a hub is only expanded when it was asked about directly
            if node not in starts and g.degree(node) > HUB_DEGREE:
                continue
            for u, v, data in list(g.out_edges(node, data=True)) + list(g.in_edges(node, data=True)):
                key = (u, data["rel"], v, data["doc"])
                if key not in seen_edges:
                    seen_edges[key] = depth
                other = v if u == node else u
                if other not in seen_nodes:
                    seen_nodes.add(other)
                    nxt.append(other)
        frontier = nxt
    edges = sorted(((u, r, v, d, dist) for (u, r, v, d), dist in seen_edges.items()),
                   key=lambda e: (e[4], e[0], e[2]))
    return edges[:MAX_TRIPLES]


# --- entity linking and synthesis ---------------------------------------------------

LINK_SYS = (
    "You link a question to entities of a knowledge graph. You are given the list of "
    "entity names in the graph. Return the entities the question mentions or clearly "
    "refers to, copied exactly from the list. If the question refers to something by a "
    "descriptive phrase, for example a product by its type, pick the entity it means. "
    'Return JSON only: {"entities":["..."]}. Return an empty list if none apply.'
)


def lexical_links(question, entities):
    """Entities whose name appears verbatim in the question, case insensitive. Short names
    are skipped so a fragment cannot match by accident."""
    q = question.lower()
    return [e for e in entities if len(e) >= 4 and e.lower() in q]


def link_entities(question, entities, tok):
    """Returns (linked, info). The LLM link is the primary signal, the lexical match is a
    flagged fallback. info records the raw reply and any error so a zero link result can
    be diagnosed instead of guessed at."""
    prompt = f"Entities:\n{json.dumps(sorted(entities))}\n\nQuestion: {question}"
    raw, err, llm = "", None, []
    try:
        raw = gemini(prompt, tok, system=LINK_SYS, as_json=True, max_tokens=2048)
        picked = json.loads(raw).get("entities", [])
        valid = set(entities)
        llm = [e for e in picked if e in valid]
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    lex = [e for e in lexical_links(question, entities) if e not in llm]
    if llm and lex:
        source = "both"
    elif llm:
        source = "llm"
    elif lex:
        source = "lexical"
    else:
        source = "none"
    return llm + lex, {"link_source": source, "llm_linked": llm, "lexical_added": lex,
                       "link_raw": raw[:300], "link_error": err}


SYNTH_SYS = (
    "Answer only from the provided graph facts. Each fact is (subject) relation (object) "
    "with its source document in brackets. Combine facts across hops when needed. If the "
    "facts do not contain the answer, say the information is not available in the sources. "
    "Be concise."
)


def synthesize(question, edges, tok):
    if not edges:
        return "the information is not available in the sources"
    facts = "\n".join(f"({u}) {r} ({v}) [{d}]" for u, r, v, d, _ in edges)
    return gemini(f"Question: {question}\n\nFacts:\n{facts}\n\nAnswer:", tok,
                  system=SYNTH_SYS, max_tokens=512)


def refused(answer):
    a = answer.lower()
    return any(k in a for k in ("not available", "do not contain", "does not contain",
                                "not contain", "no information", "not stated"))


def run_question(q, g, entities, tok):
    linked, link_info = link_entities(q["question"], entities, tok)
    edges = traverse(g, linked) if linked else []
    answer = synthesize(q["question"], edges, tok)
    docs = sorted({e[3] for e in edges})
    gold = {os.path.splitext(s)[0] for s in q.get("gold_sources", [])}
    hit = bool(gold & set(docs)) if q["answerable"] else None
    return {
        **link_info,
        "linked": linked, "n_triples": len(edges), "max_distance": max((e[4] for e in edges), default=0),
        "retrieved": docs, "retrieval_hit": hit, "refused": refused(answer), "answer": answer,
        "triples": [{"s": u, "r": r, "o": v, "doc": d, "dist": dist} for u, r, v, d, dist in edges],
    }


def main():
    if not os.path.exists(TRIPLES):
        raise SystemExit(f"{TRIPLES} not found, run extract_graph.py first")
    with open(TRIPLES, encoding="utf-8") as fh:
        triples = json.load(fh)
    g = build_graph(triples)
    entities = list(g.nodes)
    print(f"graph loaded: {g.number_of_nodes()} entities, {g.number_of_edges()} edges, hops {HOPS}")

    tok = token()
    rows = []
    with open(QUESTIONS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if LIMIT:
        rows = rows[:LIMIT]

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

    print(f"{'id':>4} | {'pattern':<11} | link | trip | dist | hit | answer")
    print("-" * 100)
    for i, q in enumerate(todo):
        if i:
            time.sleep(THROTTLE)
        tok = token()  # fresh token per question, a long run outlives one access token
        try:
            out = run_question(q, g, entities, tok)
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:140] if hasattr(e, "read") else ""
            print(f"{q['id']:>4} | ERROR {e.code} {detail}")
            continue
        except Exception as e:
            print(f"{q['id']:>4} | ERROR {type(e).__name__}: {e}")
            continue
        rec = {"id": q["id"], "pattern": q["pattern"], "difficulty": q["difficulty"],
               "answerable": q["answerable"], "question": q["question"],
               "gold_answer": q["gold_answer"], "gold_sources": q.get("gold_sources", []), **out}
        results.append(rec)
        hit_s = "n/a" if out["retrieval_hit"] is None else ("yes" if out["retrieval_hit"] else "NO")
        print(f"{q['id']:>4} | {q['pattern']:<11} | {len(out['linked']):>4} | {out['n_triples']:>4} | "
              f"{out['max_distance']:>4} | {hit_s:>3} | {out['answer'].replace(chr(10), ' ')[:40]}")

    results.sort(key=lambda r: r["id"])
    with open(OUT, "w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")

    ans_qs = [r for r in results if r["answerable"]]
    unans = [r for r in results if not r["answerable"]]
    graph_qs = [r for r in ans_qs if r["pattern"] == "graph"]
    print("-" * 100)
    print(f"retrieval hit on answerable (all):        {sum(1 for r in ans_qs if r['retrieval_hit'])}/{len(ans_qs)}")
    print(f"retrieval hit on graph questions q14 to q17: {sum(1 for r in graph_qs if r['retrieval_hit'])}/{len(graph_qs)}")
    print(f"refused unanswerable:                     {sum(1 for r in unans if r['refused'])}/{len(unans)}")
    print(f"no entity linked (graph returned nothing): {sum(1 for r in results if not r['linked'])}/{len(results)}")
    srcs = {}
    for r in results:
        srcs[r.get("link_source", "?")] = srcs.get(r.get("link_source", "?"), 0) + 1
    print(f"link source counts: {srcs}")
    errs = [r["id"] for r in results if r.get("link_error")]
    print(f"questions where the LLM link call errored: {errs if errs else 'none'}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
