"""
Lab 03: ADK Agent with SAP Basis Tools
GCP Vertex AI Learning Path

This demonstrates:
1. Creating an agent with function calling
2. Defining custom tools
3. Running the agent locally
"""

import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Configure API
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL = "gemini-2.5-flash"

# ============================================
# Define Tools (Functions the agent can call)
# ============================================

def get_tcode_info(tcode: str) -> dict:
    """Get information about an SAP transaction code."""
    tcodes = {
        "SM37": {
            "name": "Background Job Monitor",
            "purpose": "View, manage, and analyze background jobs",
            "related": ["SM36", "SM39", "SMX"]
        },
        "SM58": {
            "name": "tRFC Monitor", 
            "purpose": "Monitor and manage transactional RFC calls",
            "related": ["SM59", "SMQS", "SMQR"]
        },
        "ST22": {
            "name": "ABAP Dump Analysis",
            "purpose": "Analyze ABAP runtime errors and short dumps",
            "related": ["ST12", "SM21"]
        },
        "SM59": {
            "name": "RFC Destinations",
            "purpose": "Configure and test RFC connections",
            "related": ["SM58", "SMGW"]
        },
        "SM50": {
            "name": "Work Process Overview",
            "purpose": "Monitor work processes on current server",
            "related": ["SM66", "SM51"]
        },
        "SU53": {
            "name": "Authorization Check",
            "purpose": "Display last authorization failure for current user",
            "related": ["SU01", "PFCG"]
        },
        "SM12": {
            "name": "Lock Entries",
            "purpose": "Display and delete lock entries",
            "related": ["SM21", "SM50"]
        },
        "SM21": {
            "name": "System Log",
            "purpose": "View system log messages and events",
            "related": ["SM37", "ST22"]
        }
    }
    
    tcode_upper = tcode.upper().strip()
    if tcode_upper in tcodes:
        return {"status": "found", "tcode": tcode_upper, **tcodes[tcode_upper]}
    else:
        return {"status": "not_found", "tcode": tcode_upper, "message": f"Transaction {tcode_upper} not in knowledge base"}


def get_failed_jobs(system_id: str = "PRD", hours: int = 24) -> dict:
    """Get list of failed background jobs from an SAP system (mock data)."""
    mock_jobs = [
        {
            "job_name": "FINS_PRED_FIN_REDUCTION",
            "job_id": "12345601",
            "status": "Canceled",
            "start_time": "2026-04-05 08:00:00",
            "error": "RFC communication failure to destination HANA_DB"
        },
        {
            "job_name": "RSBDCSUB",
            "job_id": "12345602", 
            "status": "Canceled",
            "start_time": "2026-04-05 09:30:00",
            "error": "Authorization check failed for user BATCH_USER"
        },
        {
            "job_name": "RSBTCDEL",
            "job_id": "12345603",
            "status": "Canceled",
            "start_time": "2026-04-05 10:15:00",
            "error": "TIME_OUT - Maximum runtime exceeded"
        }
    ]
    
    return {
        "system": system_id,
        "hours_checked": hours,
        "total_failed": len(mock_jobs),
        "jobs": mock_jobs
    }


def check_system_health(system_id: str = "PRD") -> dict:
    """Check overall health of an SAP system (mock data)."""
    return {
        "system": system_id,
        "status": "WARNING",
        "checks": {
            "work_processes": {"status": "OK", "btc_free": 5, "btc_total": 10},
            "memory": {"status": "WARNING", "usage_percent": 85},
            "database": {"status": "OK", "connection": "active"},
            "rfc_queues": {"status": "WARNING", "stuck_entries": 12}
        },
        "recommendation": "Check RFC queue in SM58 and memory in ST02"
    }


# ============================================
# Define Tool Declarations
# ============================================

get_tcode_info_declaration = {
    "name": "get_tcode_info",
    "description": "Get information about an SAP transaction code including its purpose and related transactions",
    "parameters": {
        "type": "object",
        "properties": {
            "tcode": {
                "type": "string",
                "description": "SAP transaction code (e.g., SM37, SM58, ST22)"
            }
        },
        "required": ["tcode"]
    }
}

get_failed_jobs_declaration = {
    "name": "get_failed_jobs",
    "description": "Get list of failed background jobs from an SAP system",
    "parameters": {
        "type": "object",
        "properties": {
            "system_id": {
                "type": "string",
                "description": "SAP System ID (e.g., PRD, QAS, DEV)"
            },
            "hours": {
                "type": "integer",
                "description": "Number of hours to look back (default: 24)"
            }
        },
        "required": ["system_id"]
    }
}

check_system_health_declaration = {
    "name": "check_system_health",
    "description": "Check overall health status of an SAP system",
    "parameters": {
        "type": "object",
        "properties": {
            "system_id": {
                "type": "string",
                "description": "SAP System ID (e.g., PRD, QAS, DEV)"
            }
        },
        "required": ["system_id"]
    }
}

# Map function names to actual functions
function_map = {
    "get_tcode_info": get_tcode_info,
    "get_failed_jobs": get_failed_jobs,
    "check_system_health": check_system_health
}


# ============================================
# Agent Runner
# ============================================

def run_agent(user_query: str):
    """Run the SAP Basis Agent with a user query."""
    
    print(f"\n{'='*60}")
    print(f"User Query: {user_query}")
    print('='*60)
    
    # System instruction
    system_instruction = """You are an expert SAP Basis administrator assistant. 
    You help users troubleshoot SAP system issues, explain transaction codes, 
    and monitor system health. Use the available tools to get real data.
    Be concise and technical. Always reference relevant transaction codes."""
    
    # Define tools
    tools = [
        types.Tool(function_declarations=[
            get_tcode_info_declaration,
            get_failed_jobs_declaration,
            check_system_health_declaration
        ])
    ]
    
    # Generate response with tools
    response = client.models.generate_content(
        model=MODEL,
        contents=user_query,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            temperature=0.1
        )
    )
    
    # Check if model wants to call a function
    candidate = response.candidates[0]
    part = candidate.content.parts[0]
    
    if hasattr(part, 'function_call') and part.function_call:
        function_call = part.function_call
        function_name = function_call.name
        function_args = dict(function_call.args) if function_call.args else {}
        
        print(f"\n🔧 Agent calling tool: {function_name}")
        print(f"   Arguments: {function_args}")
        
        # Execute the function
        if function_name in function_map:
            # Handle default arguments
            if function_name == "get_failed_jobs":
                if "hours" not in function_args:
                    function_args["hours"] = 24
            
            result = function_map[function_name](**function_args)
            print(f"   Result: {json.dumps(result, indent=2)}")
            
            # Build conversation with function result
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_query)]
                ),
                types.Content(
                    role="model",
                    parts=[types.Part.from_function_call(
                        name=function_name,
                        args=function_args
                    )]
                ),
                types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=function_name,
                        response=result
                    )]
                )
            ]
            
            # Get final response
            final_response = client.models.generate_content(
                model=MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=tools,
                    temperature=0.1
                )
            )
            
            print(f"\n📋 Agent Response:")
            print(final_response.text)
        else:
            print(f"Unknown function: {function_name}")
    else:
        # No function call, direct response
        print(f"\n📋 Agent Response:")
        print(response.text)


# ============================================
# Main - Interactive Mode
# ============================================

if __name__ == "__main__":
    print("="*60)
    print("🤖 SAP Basis Agent (ADK)")
    print("   Type 'quit' to exit")
    print("="*60)
    
    # Example queries
    example_queries = [
        "What is SM58 used for?",
        "Check the health of PRD system",
        "Show me failed jobs in PRD from the last 24 hours",
        "I have tRFC errors, which transactions should I check?"
    ]
    
    print("\n📝 Example queries:")
    for i, q in enumerate(example_queries, 1):
        print(f"   {i}. {q}")
    
    print("\n")
    
    while True:
        user_input = input("You: ").strip()
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        if not user_input:
            continue
            
        run_agent(user_input)