"""Read a remote session's proposal, apply guardrails locally, compare with the laptop decision."""
import json, os, sys
import vertexai
LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(LAB, "agent"), os.path.join(LAB, "scripts")]
import guardrails
from invoice_agent.tools import REPO, case_scope

NAME = "projects/445694672328/locations/us-central1/reasoningEngines/6683498252546867200"
case, sid = sys.argv[1], sys.argv[2]
remote = vertexai.Client(project="geap-ai-usecases-494501", location="us-central1").agent_engines.get(name=NAME)
sess = remote.get_session(user_id="lab-user", session_id=sid)
st = sess["state"] if isinstance(sess, dict) else sess.state
print("state keys", sorted(st))
rules = json.load(open(os.path.join(LAB, "results", "decisions", "baseline", f"{case}.json"), encoding="utf-8"))
final = guardrails.apply(rules, st["assessment"], REPO.approvals(case_scope(case)["po_number"]), st.get("violations", []))
laptop = json.load(open(os.path.join(LAB, "results", "decisions", "agent", f"{case}.json"), encoding="utf-8"))
for label, d in (("remote", final), ("laptop", laptop)):
    print(f"{label:7} disposition={d.get('disposition')} reasons={d.get('reasons')}")
print("guardrails", json.dumps(final.get("guardrails"), indent=1)[:1200])
