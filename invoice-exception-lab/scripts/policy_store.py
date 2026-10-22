"""Policy access for the agent: search to find, the versioned files to read.

Architecture choice: Vertex AI Search is the retrieval index, the policies/ folder is the source
of truth. Search returns which documents match; the clause text the agent cites is always read
from the version controlled file, so a stale or partial index can never change policy wording.
Every clause carries its status (CURRENT or SUPERSEDED), taken from the document header.

Backends, chosen with INV_POLICY_SEARCH:
  local   keyword scoring over the files (default, offline, used by tests)
  vertex  Vertex AI Search data store "invoice-policies" (scripts/setup_policy_search.py)
"""
import os
import re

from common import D, PROJECT, call

DATA_STORE = os.getenv("INV_POLICY_STORE", "invoice-policies")
BACKEND = os.getenv("INV_POLICY_SEARCH", "local")


def load_policies():
    """{doc_id: {"status", "header", "clauses": {clause_id: text}}} from policies/*.md"""
    out = {}
    for fn in sorted(os.listdir(D("policies"))):
        if not fn.endswith(".md"):
            continue
        doc_id = fn[:-3]
        text = open(D("policies", fn), encoding="utf-8").read()
        status = "SUPERSEDED" if "Status: SUPERSEDED" in text else "CURRENT"
        clauses = {}
        for m in re.finditer(r"^## (AP-POL-\d+@v\d+:\d+\.\d+) (.+?)\n(.*?)(?=^## |\Z)", text, re.S | re.M):
            clauses[m.group(1)] = f"{m.group(2)}. {m.group(3).strip()}"
        out[doc_id] = {"status": status, "header": text.split("\n\n")[1] if "\n\n" in text else "",
                       "clauses": clauses}
    return out


POLICIES = load_policies()
CLAUSES = {cid: (doc, d["status"]) for doc, d in POLICIES.items() for cid in d["clauses"]}


def clause(clause_id):
    if clause_id not in CLAUSES:
        return {"clause_id": clause_id, "found": False}
    doc, status = CLAUSES[clause_id]
    return {"clause_id": clause_id, "found": True, "status": status, "document": doc,
            "text": POLICIES[doc]["clauses"][clause_id]}


def _local_search(query, k):
    words = set(re.findall(r"[a-z]{3,}", query.lower()))
    scored = []
    for doc, d in POLICIES.items():
        body = " ".join(d["clauses"].values()).lower()
        score = sum(body.count(w) for w in words)
        if score:
            scored.append((score, doc))
    return [doc for _, doc in sorted(scored, reverse=True)[:k]]


def _vertex_search(query, k):
    url = (f"https://discoveryengine.googleapis.com/v1/projects/{PROJECT}/locations/global/"
           f"collections/default_collection/dataStores/{DATA_STORE}/servingConfigs/default_search:search")
    resp = call("POST", url, {"query": query, "pageSize": k})
    docs = []
    for r in resp.get("results", []):
        link = (r.get("document", {}).get("derivedStructData", {}) or {}).get("link", "")
        m = re.search(r"(AP-POL-\d+@v\d+)", link)
        if m and m.group(1) not in docs:
            docs.append(m.group(1))
    return docs


def search(query, k=4):
    docs = _vertex_search(query, k) if BACKEND == "vertex" else _local_search(query, k)
    return {"backend": BACKEND, "query": query, "results": [
        {"document": doc, "status": POLICIES[doc]["status"],
         "clauses": [{"clause_id": c, "title_and_text": t[:400]}
                     for c, t in POLICIES[doc]["clauses"].items()]}
        for doc in docs if doc in POLICIES]}
