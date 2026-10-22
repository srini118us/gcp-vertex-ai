"""Run the ADK investigation agent on cases, apply guardrails, and report agent metrics.

Harness rules carried from the Argon and RAG labs:
  * hard deadline per case (asyncio.wait_for), a hung call is recorded as a timeout, not waited on
  * budget ledger: estimated cost is summed after each case, the run stops at INV_AGENT_BUDGET_USD
  * completion is reported separately from correctness
  * the full tool trajectory, token usage and latency are saved per case
  * resume: completed cases are skipped unless INV_FORCE=1; errors and timeouts are retried

Prerequisites, from the lab folder: verify_extraction.py, human_field_review.py, matcher.py.
Environment:
    GOOGLE_GENAI_USE_VERTEXAI=TRUE
    GOOGLE_CLOUD_PROJECT=geap-ai-usecases-494501
    GOOGLE_CLOUD_LOCATION=global
    INV_POLICY_SEARCH=vertex      (or local)
Run:
    python scripts/run_agent.py E01            one case
    python scripts/run_agent.py                all cases with a baseline decision
Writes results/agent/runs/<case>.json and results/decisions/agent/<case>.json.
Cost uses Gemini API list prices for gemini-3.8-flash (0.75 USD in, 3.75 USD out per 1M,
thinking billed as output, checked 2026-10-13); Vertex billing may differ, so it is an estimate.
"""
import asyncio
import json
import os
import sys
import time

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(LAB, "scripts"))
sys.path.insert(0, os.path.join(LAB, "agent"))

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

import guardrails  # noqa: E402
from common import D  # noqa: E402
from invoice_agent.agent import MODEL, root_agent  # noqa: E402
from invoice_agent.tools import REPO, case_scope  # noqa: E402

PRICE_IN, PRICE_OUT = 0.75, 3.75
DEADLINE = float(os.getenv("INV_AGENT_DEADLINE_S", "180"))
BUDGET = float(os.getenv("INV_AGENT_BUDGET_USD", "2.00"))
FORCE = os.getenv("INV_FORCE") == "1"


async def run_case(runner, cid):
    scope = case_scope(cid)
    session = await runner.session_service.create_session(
        app_name=runner.app_name, user_id="ap_lab",
        state={"scope": scope, "trajectory": [], "violations": []})
    usage = {"prompt": 0, "output": 0, "thoughts": 0, "cached": 0}
    final_text = []

    async def turn(text):
        msg = types.Content(role="user", parts=[types.Part(text=text)])
        async for ev in runner.run_async(user_id="ap_lab", session_id=session.id, new_message=msg):
            um = ev.usage_metadata
            if um:
                usage["prompt"] += um.prompt_token_count or 0
                usage["output"] += um.candidates_token_count or 0
                usage["thoughts"] += um.thoughts_token_count or 0
                usage["cached"] += um.cached_content_token_count or 0
            if ev.is_final_response() and ev.content and ev.content.parts:
                final_text.extend(p.text for p in ev.content.parts if getattr(p, "text", None))

    await turn(f"Investigate case {cid}.")
    st = (await runner.session_service.get_session(app_name=runner.app_name, user_id="ap_lab",
                                                   session_id=session.id)).state
    retried = False
    if "assessment" not in st:
        retried = True
        await turn("You have not called submit_assessment. Call it now with your assessment.")
        st = (await runner.session_service.get_session(app_name=runner.app_name, user_id="ap_lab",
                                                       session_id=session.id)).state
    return {"assessment": st.get("assessment"), "trajectory": st.get("trajectory", []),
            "violations": st.get("violations", []), "usage": usage, "retried": retried,
            "final_text": " ".join(final_text)[:1000]}


def cost(u):
    return ((u["prompt"] - u["cached"]) * PRICE_IN + u["cached"] * PRICE_IN * 0.1
            + (u["output"] + u["thoughts"]) * PRICE_OUT) / 1_000_000


async def main():
    for k in ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
        if not os.getenv(k):
            raise SystemExit(f"set {k} first (see the module docstring)")
    wanted = sys.argv[1:]
    base_dir = D("results", "decisions", "baseline")
    cases = wanted or sorted(f[:-5] for f in os.listdir(base_dir) if f.endswith(".json"))
    os.makedirs(D("results", "agent", "runs"), exist_ok=True)
    os.makedirs(D("results", "decisions", "agent"), exist_ok=True)
    runner = InMemoryRunner(agent=root_agent, app_name="invoice_lab")
    spent = 0.0
    print(f"model {MODEL}, policy search {os.getenv('INV_POLICY_SEARCH', 'local')}, "
          f"data {REPO.name}, deadline {DEADLINE}s, budget {BUDGET} USD")
    for cid in cases:
        run_path = D("results", "agent", "runs", f"{cid}.json")
        if os.path.exists(run_path) and not FORCE:
            prev = json.load(open(run_path, encoding="utf-8")).get("status")
            if prev == "completed":
                print(f"{cid}: already completed, skipping (INV_FORCE=1 to redo)")
                continue
            print(f"{cid}: previous run ended with status {prev}, retrying")
        if spent >= BUDGET:
            print(f"budget {BUDGET} USD reached, stopping before {cid}")
            break
        t0 = time.time()
        status = "completed"
        try:
            res = await asyncio.wait_for(run_case(runner, cid), timeout=DEADLINE)
        except asyncio.TimeoutError:
            res, status = {"assessment": None, "trajectory": [], "violations": [], "usage":
                           {"prompt": 0, "output": 0, "thoughts": 0, "cached": 0}}, "timeout"
        except Exception as e:  # recorded, never silent
            res, status = {"assessment": None, "trajectory": [], "violations": [], "usage":
                           {"prompt": 0, "output": 0, "thoughts": 0, "cached": 0},
                           "error": f"{type(e).__name__}: {e}"[:500]}, "error"
        if status == "completed" and not res["assessment"]:
            status = "no_assessment"
        res.update(case_id=cid, status=status, latency_s=round(time.time() - t0, 1),
                   est_cost_usd=round(cost(res["usage"]), 5), model=MODEL)
        spent += res["est_cost_usd"]
        with open(run_path, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1)
        rules = json.load(open(os.path.join(base_dir, f"{cid}.json"), encoding="utf-8"))
        approvals = REPO.approvals(rules_po(cid))
        final = guardrails.apply(rules, res["assessment"], approvals, res["violations"])
        with open(D("results", "decisions", "agent", f"{cid}.json"), "w", encoding="utf-8") as fh:
            json.dump(final, fh, indent=1)
        a = res["assessment"] or {}
        g = final["guardrails"]
        print(f"{cid}: {status}, {res['latency_s']}s, tools {len(res['trajectory'])}, "
              f"rules {rules['disposition']}, proposed {a.get('proposed_disposition', '-')}, "
              f"added {a.get('added_reasons', [])}, injection {a.get('injection_detected', '-')}, "
              f"cites {len((final.get('agent') or {}).get('citations', []))}, "
              f"violations {len(g['violations'])}, ~${res['est_cost_usd']:.4f}"
              + (f", ERROR {res.get('error')}" if res.get("error") else ""))
    print(f"estimated spend this run: ${spent:.4f}")
    print("next: python scripts/score_agent.py")


def rules_po(cid):
    return case_scope(cid)["po_number"]


if __name__ == "__main__":
    asyncio.run(main())
