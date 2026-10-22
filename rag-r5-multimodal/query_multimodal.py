"""R5 Multimodal runner, four arms on the table questions.

Question set, the questions whose answer lives in the product catalog tables:
q04 (FR900 price), q05 (WX200 capacity), q06 (AC300 power), q07 (DX500 dimensions),
plus q11 (DX500 noise level, unanswerable, the catalog says noise is not published)
to check refusal does not regress.

Arms:
  A baseline  the R1 engine (meridian-search) over the flattened text catalog
  B control   data store r5-control, one text document per product written by plain
              code from the markdown table, no vision
  C vision    data store r5-vision, one text document per product written by Gemini
              reading the catalog as an image
  D query     no retrieval, the catalog PNG plus the question go straight to Gemini

Scoring per arm: hit (the right product document was retrieved, arms A to C) and
correct (every number in the gold answer appears in the answer, or a refusal for q11).

Run from the repo root, after prepare_r5.py and the data stores are indexed:
    python rag-r5-multimodal\\query_multimodal.py

Env knobs: RAG_THROTTLE (default 3), RAG_PROJECT, RAG_ENGINE, RAG_LOCATION,
RAG_GEMINI. Outputs rag-r5-multimodal\\results_multimodal.jsonl.
"""
import base64
import json
import os
import re
import subprocess
import time
import urllib.request
import urllib.error

PROJECT = os.getenv("RAG_PROJECT", "enterprise-agent-labs-1012")
ENGINE = os.getenv("RAG_ENGINE", "meridian-search")
LOCATION = os.getenv("RAG_LOCATION", "global")
GEMINI = os.getenv("RAG_GEMINI", "gemini-3.8-flash")
THROTTLE = float(os.getenv("RAG_THROTTLE", "10"))
ARM_PAUSE = float(os.getenv("RAG_ARM_PAUSE", "4"))
IDS =["q04", "q05", "q06", "q07", "q11"]
CODES = ["DX500", "WX200", "FR900", "AC300"]

COL = (f"https://discoveryengine.googleapis.com/v1/projects/{PROJECT}"
       f"/locations/global/collections/default_collection")
ENGINE_URL = f"{COL}/engines/{ENGINE}/servingConfigs/default_search:search"


def store_url(store_id):
    return f"{COL}/dataStores/{store_id}/servingConfigs/default_search:search"


_host = "aiplatform.googleapis.com" if LOCATION == "global" else f"{LOCATION}-aiplatform.googleapis.com"
GEMINI_URL = (f"https://{_host}/v1/projects/{PROJECT}/locations/{LOCATION}"
              f"/publishers/google/models/{GEMINI}:generateContent")

QUESTIONS = os.path.join("rag-lab", "r0-foundation", "questions.jsonl")
DATA = os.path.join("rag-r5-multimodal", "data")
PNG = os.path.join(DATA, "catalog.png")
OUT = os.path.join("rag-r5-multimodal", "results_multimodal.jsonl")


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


def base(name):
    return os.path.splitext(os.path.basename(name))[0]


def gemini(parts, tok, system=None, max_tokens=512):
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": max_tokens},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    resp = _post(GEMINI_URL, body, tok)
    out = resp.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in out).strip()


SYNTH_SYS = (
    "Answer only from the provided material. If it does not contain the answer, say the "
    "information is not available in the sources. Be concise."
)


def synthesize(question, context, tok):
    if not context.strip():
        return "the information is not available in the sources"
    return gemini([{"text": f"Question: {question}\n\nMaterial:\n{context}\n\nAnswer:"}],
                  tok, system=SYNTH_SYS)


# --- arm A, the R1 engine over the flattened text ----------------------------------

def arm_baseline(question, tok):
    body = {
        "query": question, "pageSize": 5,
        "contentSearchSpec": {
            "snippetSpec": {"returnSnippet": True},
            "extractiveContentSpec": {"maxExtractiveAnswerCount": 2, "maxExtractiveSegmentCount": 1},
        },
    }
    resp = _post(ENGINE_URL, body, tok)
    docs, ctx = [], []
    for res in resp.get("results", []):
        d = res.get("document", {})
        dsd = d.get("derivedStructData", {})
        link = dsd.get("link", "") or d.get("id", "")
        docs.append(base(link))
        for s in dsd.get("snippets", []):
            if s.get("snippet") and s.get("snippet_status") != "NO_SNIPPET_AVAILABLE":
                ctx.append(s["snippet"])
        for a in dsd.get("extractive_answers", []):
            if a.get("content"):
                ctx.append(a["content"])
        for seg in dsd.get("extractive_segments", []):
            if seg.get("content"):
                ctx.append(seg["content"])
    return docs, "\n".join(ctx)


# --- arms B and C, a data store of one small text document per product --------------

def arm_store(question, store_id, folder, tok):
    resp = _post(store_url(store_id), {"query": question, "pageSize": 4}, tok)
    docs, ctx = [], []
    for res in resp.get("results", []):
        d = res.get("document", {})
        link = d.get("derivedStructData", {}).get("link", "") or d.get("id", "")
        code = base(link)
        docs.append(code)
        path = os.path.join(DATA, folder, f"{code}.txt")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                ctx.append(fh.read().strip())
    return docs, "\n\n".join(ctx[:3])


# --- arm D, the image goes straight to Gemini --------------------------------------

def arm_query_time(question, tok):
    with open(PNG, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    parts = [{"inlineData": {"mimeType": "image/png", "data": b64}},
             {"text": f"Question: {question}\n\nAnswer only from the catalog image. If it "
                      "does not contain the answer, say the information is not available "
                      "in the sources. Be concise."}]
    return gemini(parts, tok)


# --- scoring -----------------------------------------------------------------------

def numbers(text):
    return re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))


def is_refusal(answer):
    a = answer.lower()
    return any(k in a for k in ("not available", "do not contain", "does not contain",
                                "not contain", "no information", "not published", "not stated"))


def correct(q, answer):
    if not q["answerable"]:
        return is_refusal(answer)
    want = numbers(q["gold_answer"])
    got = numbers(answer)
    return bool(want) and all(n in got for n in want)


def product_code(question):
    for c in CODES:
        if c in question:
            return c
    return None


def run_question(q, tok):
    code = product_code(q["question"])
    out = {}

    docs, ctx = arm_baseline(q["question"], tok)
    ans = synthesize(q["question"], ctx, tok)
    out["A_baseline"] = {"docs": docs, "hit": ("product_catalog" in docs) if q["answerable"] else None,
                         "answer": ans, "correct": correct(q, ans)}

    for key, store, folder in (("B_control", "r5-control", "control"),
                               ("C_vision", "r5-vision", "vision")):
        time.sleep(ARM_PAUSE)
        docs, ctx = arm_store(q["question"], store, folder, tok)
        ans = synthesize(q["question"], ctx, tok)
        out[key] = {"docs": docs, "hit": (code in docs) if (q["answerable"] and code) else None,
                    "answer": ans, "correct": correct(q, ans)}

    time.sleep(ARM_PAUSE)
    ans = arm_query_time(q["question"], tok)
    out["D_query_image"] = {"answer": ans, "correct": correct(q, ans)}
    return out


def flag(v):
    return "n/a" if v is None else ("yes" if v else "NO")


def main():
    tok = token()
    qs = []
    with open(QUESTIONS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                q = json.loads(line)
                if q["id"] in IDS:
                    qs.append(q)

    # resume: keep questions already recorded, run only the missing ones
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
    qs = [q for q in qs if q["id"] not in done]

    print(f"{'id':>4} | A hit/ok   | B hit/ok   | C hit/ok   | D ok  | vision answer")
    print("-" * 100)
    for i, q in enumerate(qs):
        if i:
            time.sleep(THROTTLE)
        try:
            out = run_question(q, tok)
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:200] if hasattr(e, "read") else ""
            print(f"{q['id']:>4} | ERROR {e.code} {detail}")
            continue
        except Exception as e:
            print(f"{q['id']:>4} | ERROR {type(e).__name__}: {e}")
            continue
        results.append({"id": q["id"], "question": q["question"], "answerable": q["answerable"],
                        "gold_answer": q["gold_answer"], **out})
        a, b, c, d = out["A_baseline"], out["B_control"], out["C_vision"], out["D_query_image"]
        print(f"{q['id']:>4} | {flag(a['hit']):>3} / {'ok' if a['correct'] else 'NO':<4} | "
              f"{flag(b['hit']):>3} / {'ok' if b['correct'] else 'NO':<4} | "
              f"{flag(c['hit']):>3} / {'ok' if c['correct'] else 'NO':<4} | "
              f"{'ok' if d['correct'] else 'NO':<5} | {c['answer'].replace(chr(10), ' ')[:34]}")

    results.sort(key=lambda r: r["id"])
    with open(OUT, "w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")

    ans_qs = [r for r in results if r["answerable"]]
    unans = [r for r in results if not r["answerable"]]
    print("-" * 100)
    print(f"{'arm':<14} | retrieval hit | correct on answerable | correct refusal")
    for key in ("A_baseline", "B_control", "C_vision", "D_query_image"):
        hits = sum(1 for r in ans_qs if r[key].get("hit")) if key != "D_query_image" else None
        corr = sum(1 for r in ans_qs if r[key]["correct"])
        ref = sum(1 for r in unans if r[key]["correct"])
        hit_s = "n/a" if hits is None else f"{hits}/{len(ans_qs)}"
        print(f"{key:<14} | {hit_s:>13} | {corr:>2}/{len(ans_qs):<19} | {ref}/{len(unans)}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
