"""Phase 1 delay_root_cause, loaded from git as a regression oracle (no copy of the legacy code is kept)."""
import ast
import subprocess
import types
from pathlib import Path

LEGACY_COMMIT = "72027e364"
ROOT = Path(__file__).resolve().parents[1]
_PATH = "logistics_agent/agent.py"

def load_legacy() -> types.ModuleType:
    """Imports, constants and functions of the legacy module; skips the ADK agent and A2A app."""
    src = subprocess.check_output(["git", "show", f"{LEGACY_COMMIT}:./{_PATH}"], cwd=ROOT, text=True, encoding="utf-8")
    tree = ast.parse(src)
    tree.body = [n for n in tree.body if not (isinstance(n, ast.Assign) and
                 any(isinstance(t, ast.Name) and t.id in ("root_agent", "a2a_app") for t in n.targets))]
    mod = types.ModuleType("legacy_logistics_agent")
    mod.__file__ = str(ROOT / _PATH)  # so its load_dotenv finds logistics_agent/.env, as before
    exec(compile(tree, f"{LEGACY_COMMIT}:{_PATH}", "exec"), mod.__dict__)
    return mod
