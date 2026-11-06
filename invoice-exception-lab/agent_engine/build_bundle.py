"""Build a self-contained Agent Engine bundle that mirrors the lab layout (no source changes)."""
import os, shutil
LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(LAB, "agent_engine", "build", "ap_investigator")
skip = shutil.ignore_patterns("__pycache__", "*.pyc", ".env")
shutil.rmtree(OUT, ignore_errors=True)
shutil.copytree(os.path.join(LAB, "agent", "invoice_agent"), os.path.join(OUT, "agent_src", "invoice_agent"), ignore=skip)
os.makedirs(os.path.join(OUT, "scripts"))
for f in ("common.py", "policy_store.py", "repository.py"):
    shutil.copy2(os.path.join(LAB, "scripts", f), os.path.join(OUT, "scripts", f))
for d in ("spec", "results/verified", "results/decisions/baseline", "results/extraction", "attachments", "policies", "data"):
    shutil.copytree(os.path.join(LAB, d), os.path.join(OUT, d), ignore=skip)
w = lambda name, text: open(os.path.join(OUT, name), "w", newline="\n").write(text)
w("__init__.py", "from . import agent\n")
w("agent.py", "import os, sys\nos.environ['GOOGLE_CLOUD_LOCATION'] = os.getenv('INV_MODEL_LOCATION', 'global')  # model endpoint; engine stays regional\nsys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent_src'))\nfrom invoice_agent.agent import root_agent  # noqa: E402,F401\n")
w("requirements.txt", "google-adk==2.4.0\n")
w(".env", "GOOGLE_GENAI_USE_VERTEXAI=TRUE\nGOOGLE_CLOUD_PROJECT=geap-ai-usecases-494501\nGOOGLE_CLOUD_LOCATION=global\nINV_DATA=csv\nINV_POLICY_SEARCH=local\n")
n = sum(len(fs) for _, _, fs in os.walk(OUT))
kb = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs) / 1024
print(f"bundle {OUT}: {n} files, {kb:.0f} KB")
