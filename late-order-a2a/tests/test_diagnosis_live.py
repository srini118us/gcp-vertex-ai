"""Live regression against BigQuery. Run with RUN_CLOUD_TESTS=1 after tests/capture_goldens.py."""
import json
import os
from datetime import date
from pathlib import Path
import pytest
from logistics_core import diagnosis as d

pytestmark = pytest.mark.cloud
GOLDEN = Path(__file__).parent / "golden" / "delay_root_cause_live.json"

def golden():
    if not GOLDEN.exists():
        pytest.fail("run tests/capture_goldens.py first")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))

@pytest.fixture(scope="module")
def logistics_env():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parents[1] / "logistics_agent" / ".env")
    assert os.getenv("LOGISTICS_SA"), "LOGISTICS_SA must be set to impersonate the logistics identity"

def test_shared_module_reproduces_goldens(logistics_env):
    g = golden()
    as_of = date.fromisoformat(g["as_of_date"])
    for case in g["cases"]:
        assert d.delay_root_cause(case["order_id"], as_of=as_of) == case["result"], case["label"]

def test_cx_identity_is_denied_with_sanitized_error(logistics_env, monkeypatch):
    from dotenv import dotenv_values
    cx_sa = dotenv_values(Path(__file__).parents[1] / "cx_agent" / ".env").get("CX_SA")
    assert cx_sa, "CX_SA must be set in cx_agent/.env"
    monkeypatch.setenv("LOGISTICS_SA", cx_sa)
    with pytest.raises(d.LogisticsDataAccessDenied) as e:
        d.delay_root_cause(109778, as_of=date.fromisoformat(golden()["as_of_date"]))
    assert str(e.value) == "ACCESS_DENIED: logistics data access denied"
