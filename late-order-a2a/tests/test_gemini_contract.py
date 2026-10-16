"""The Gemini Logistics agent must look exactly as before to Gemini and to A2A clients, and use the shared module."""
import asyncio
import json
from pathlib import Path
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.tools import FunctionTool
from logistics_agent import agent

GOLDEN = json.loads((Path(__file__).parent / "golden" / "gemini_contract.json").read_text(encoding="utf-8"))

def test_tool_declaration_unchanged():
    decl = FunctionTool(agent.delay_root_cause)._get_declaration().model_dump(exclude_none=True, mode="json")
    assert decl == GOLDEN["tool_declaration"]

def test_agent_definition_unchanged():
    a = agent.root_agent
    assert (a.name, a.model, a.description, a.instruction) == ("logistics_agent", GOLDEN["model"], GOLDEN["description"], GOLDEN["instruction"])
    assert [t.__name__ for t in a.tools] == ["delay_root_cause"]

def test_agent_card_unchanged():
    card = asyncio.run(AgentCardBuilder(agent=agent.root_agent, rpc_url="http://localhost:8001").build())
    assert card.model_dump(exclude_none=True, mode="json") == GOLDEN["agent_card"]

def test_tool_delegates_to_shared_diagnosis(monkeypatch):
    seen = []
    monkeypatch.setattr(agent.diagnosis, "delay_root_cause", lambda oid: seen.append(oid) or {"order_id": oid})
    assert agent.delay_root_cause(109778) == {"order_id": 109778} and seen == [109778]

def test_no_sql_or_rules_left_in_agent():
    src = Path(agent.__file__).read_text(encoding="utf-8")
    assert "SELECT" not in src and "1.5" not in src and "bigquery" not in src
