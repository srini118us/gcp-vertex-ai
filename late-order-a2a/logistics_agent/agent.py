import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from google.adk.agents import LlmAgent
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from logistics_core import diagnosis

# ADK derives the Gemini function declaration from this name, signature and docstring: keep them stable.
def delay_root_cause(order_id: int) -> dict:
    """Governed logistics diagnosis for one order: per item warehouse lag and transit time,
    compared with the shipping distribution center's 90 day baseline. Rules decide the cause."""
    return diagnosis.delay_root_cause(order_id)

root_agent = LlmAgent(
    name="logistics_agent", model="gemini-3.8-flash",
    description="Supply Chain team agent. Diagnoses why a specific order is delayed: warehouse lag versus transit time, against the distribution center baseline.",
    instruction="""You diagnose delivery delays for one order at a time. Always call delay_root_cause.
Report each item's cause exactly as returned, with the hours compared to the baseline.
Always include each item's cause code exactly, e.g. WAREHOUSE_DELAY.
Never speculate beyond the tool output. You do not handle refunds or customer communication.""",
    tools=[delay_root_cause])

a2a_app = to_a2a(root_agent, port=8001)
