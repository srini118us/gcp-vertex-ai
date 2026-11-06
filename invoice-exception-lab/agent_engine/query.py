"""Create a scoped session on the deployed agent, send one case, print calls and the answer."""
import os, sys
import vertexai
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent"))
from invoice_agent.tools import case_scope  # trusted caller computes the scope locally

NAME = "projects/445694672328/locations/us-central1/reasoningEngines/6683498252546867200"
case = sys.argv[1] if len(sys.argv) > 1 else "E01"
client = vertexai.Client(project="geap-ai-usecases-494501", location="us-central1")
remote = client.agent_engines.get(name=NAME)
session = remote.create_session(user_id="lab-user", state={"scope": case_scope(case), "trajectory": [], "violations": []})
sid = session["id"] if isinstance(session, dict) else session.id
print("session", sid)
for ev in remote.stream_query(user_id="lab-user", session_id=sid, message=f"Investigate case {case}."):
    if "content" not in ev:
        print("EVENT", str(ev)[:400]); continue
    for part in ev["content"].get("parts", []):
        if "function_call" in part:
            print("CALL  ", part["function_call"]["name"], part["function_call"].get("args"))
        elif "function_response" in part:
            print("RESULT", part["function_response"]["name"], str(part["function_response"].get("response"))[:160])
        elif "text" in part:
            print("TEXT  ", part["text"][:1200])
