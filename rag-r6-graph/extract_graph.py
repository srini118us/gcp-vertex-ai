"""R6 Graph RAG, step 1: build the knowledge graph.

Gemini reads each of the 8 Meridian documents and extracts (subject, relation, object)
triples as JSON. The triples are saved with their source document so every edge can be
traced back to the text it came from. Step 2 (query_graph.py) loads them into an in
memory networkx graph and walks it.

Run from the repo root:
    pip install networkx
    python rag-r6-graph\\extract_graph.py

Env knobs: RAG_PROJECT, RAG_LOCATION (default global), RAG_GEMINI (default
gemini-3.8-flash), RAG_THROTTLE (seconds between documents, default 6).

Output: rag-r6-graph\\data\\triples.json
"""
import glob
import json
import os
import subprocess
import time
import urllib.request
import urllib.error

PROJECT = os.getenv("RAG_PROJECT", "enterprise-agent-labs-1012")
LOCATION = os.getenv("RAG_LOCATION", "global")
GEMINI = os.getenv("RAG_GEMINI", "gemini-3.8-flash")
THROTTLE = float(os.getenv("RAG_THROTTLE", "6"))

_host = "aiplatform.googleapis.com" if LOCATION == "global" else f"{LOCATION}-aiplatform.googleapis.com"
GEMINI_URL = (f"https://{_host}/v1/projects/{PROJECT}/locations/{LOCATION}"
              f"/publishers/google/models/{GEMINI}:generateContent")

CORPUS_GLOB = os.path.join("rag-lab", "r0-foundation", "corpus", "*.md")
DATA = os.path.join("rag-r6-graph", "data")
OUT = os.path.join(DATA, "triples.json")


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


EXTRACT_SYS = (
    "You extract a knowledge graph from one document of an appliance company. Return JSON "
    'only: {"triples":[{"s":"...","r":"...","o":"..."}]}\n'
    "Rules:\n"
    "- One fact per triple. Only facts stated in the document, never invented.\n"
    "- Entity names are short and canonical. Use the product code for products (DX500, "
    "WX200, FR900, AC300), the full name for people and companies, and '<Name> division' "
    "for divisions (for example 'Laundry division'). Never use pronouns.\n"
    "- Relations are lowercase snake_case verb phrases such as led_by, belongs_to_division, "
    "supplies, used_in, affected_by, caused_by, exempt_from, has_capacity, has_list_price.\n"
    "- Prefer direct entity to entity facts over intermediate nodes, so a reader can follow "
    "a chain of facts by walking from one entity to the next.\n"
    "- For specification tables, one triple per row for each product."
)


def extract(doc_name, text, tok):
    body = {
        "contents": [{"role": "user", "parts": [{"text": f"Document: {doc_name}\n\n{text}"}]}],
        "systemInstruction": {"parts": [{"text": EXTRACT_SYS}]},
        "generationConfig": {"temperature": 0, "maxOutputTokens": 4096,
                             "responseMimeType": "application/json"},
    }
    resp = _post(GEMINI_URL, body, tok)
    parts = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    raw = "".join(p.get("text", "") for p in parts).strip()
    triples = json.loads(raw).get("triples", [])
    out = []
    for t in triples:
        s, r, o = (str(t.get(k, "")).strip() for k in ("s", "r", "o"))
        if s and r and o:
            out.append({"s": s, "r": r, "o": o, "doc": doc_name})
    return out


# entities the graph questions need, a coarse check that extraction found them
EXPECTED = ["CoolCore", "Volt Components", "Priya Nair", "WX200", "AC300", "DX500", "FR900"]


def main():
    os.makedirs(DATA, exist_ok=True)
    tok = token()
    files = sorted(glob.glob(CORPUS_GLOB))
    print(f"found {len(files)} documents")
    all_triples = []
    for i, path in enumerate(files):
        if i:
            time.sleep(THROTTLE)
        name = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        try:
            triples = extract(name, text, tok)
        except Exception as e:
            print(f"  {name}: ERROR {type(e).__name__}: {e}")
            continue
        all_triples += triples
        print(f"  {name}: {len(triples)} triples")

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(all_triples, fh, indent=1)

    entities = {t["s"] for t in all_triples} | {t["o"] for t in all_triples}
    print(f"total {len(all_triples)} triples, {len(entities)} distinct entities")
    for name in EXPECTED:
        found = any(name.lower() in e.lower() for e in entities)
        print(f"  entity {name}: {'present' if found else 'MISSING'}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
