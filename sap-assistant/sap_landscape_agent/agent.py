from google.adk.agents import Agent
from .tools import search_sap_docs
from . import config

SYSTEM_INSTRUCTION = """You are the SAP Landscape Documentation Assistant.
ALWAYS use search_sap_docs tool first before answering.
Base answers ONLY on search results.
Always cite the document source."""

root_agent = Agent(
    name=config.AGENT_NAME,
    model=config.MODEL_NAME,
    description=config.AGENT_DESCRIPTION,
    instruction=SYSTEM_INSTRUCTION,
    tools=[search_sap_docs],
)