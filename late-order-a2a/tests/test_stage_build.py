import os
import subprocess
import sys
from pathlib import Path
from conftest import ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import stage_build

def test_gemini_build_is_self_contained(tmp_path):
    out = tmp_path / "logistics-gemini"
    files = stage_build.stage("logistics-gemini", out)
    assert {"Procfile", "requirements.txt", ".python-version", "logistics_core/diagnosis.py",
            "logistics_core/bq.py", "logistics_agent/agent.py"} <= set(files)
    assert not [f for f in files if ".env" in Path(f).name or "__pycache__" in f]
    # the staged agent must import the staged shared module, not the repo copy
    code = ("import logistics_core, logistics_agent.agent as a; "
            "print(logistics_core.__file__); print(a.a2a_app is not None)")
    r = subprocess.run([sys.executable, "-c", code], cwd=out, capture_output=True, text=True,
                       env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
    assert r.returncode == 0, r.stderr[-2000:]
    first, second = r.stdout.strip().splitlines()[-2:]
    assert Path(first).resolve().is_relative_to(out.resolve()) and second == "True"

def test_procfile_entrypoint_unchanged(tmp_path):
    stage_build.stage("logistics-gemini", tmp_path / "b")
    assert (tmp_path / "b" / "Procfile").read_text().strip() == "web: uvicorn logistics_agent.agent:a2a_app --host 0.0.0.0 --port $PORT"
