"""
Stock Agent - ADK Agent Definition
Lab 04: Vertex AI Agent Engine

This agent provides real-time stock market data and analysis.
Uses yfinance for free market data (no API key required).
"""

from google.adk.agents import Agent

# Import our custom tools
from .tools import (
    get_stock_price,
    get_stock_history,
    compare_stocks,
    get_company_info,
    analyze_trend,
)

# System instruction for the agent
SYSTEM_INSTRUCTION = """You are a helpful stock market analyst assistant.

Your capabilities:
- Get real-time stock prices and daily changes
- Retrieve historical price data for various periods
- Compare multiple stocks side by side
- Provide detailed company information
- Analyze stock trends using technical indicators

Guidelines:
- Always use the available tools to fetch current data
- Format numbers clearly: use $ for prices, % for percentages
- When comparing stocks, present data in a clear, organized way
- Always mention that this is not financial advice
- Be concise but informative in your responses

Remember: You have access to real market data through yfinance.
Use the tools to provide accurate, up-to-date information."""


# Define the ADK Agent
# This is what Agent Engine will wrap and deploy
root_agent = Agent(
    name="stock_agent",
    model="gemini-2.0-flash",  # Using Gemini 2.0 Flash for speed
    instruction=SYSTEM_INSTRUCTION,
    tools=[
        get_stock_price,
        get_stock_history,
        compare_stocks,
        get_company_info,
        analyze_trend,
    ],
)


# For local testing with ADK CLI: adk run stock_agent
# For deployment: adk deploy agent_engine --project=... stock_agent/
