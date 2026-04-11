"""
ORCHESTRATOR/INCIDENT_MANAGER_AGENT.PY
SAP Incident Manager - MCP Orchestrator Agent

Workflow:
1. User reports an issue
2. Agent searches SAP documentation for troubleshooting
3. Agent finds related past incidents
4. Agent creates ServiceNow incident
5. Agent posts notification to Teams
"""

from typing import Dict, Any, List
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mcp_servers.servicenow.servicenow_tools import (
    create_incident,
    search_incidents,
    get_related_incidents
)
from mcp_servers.teams.teams_tools import (
    post_incident_notification,
    post_simple_message
)
from mcp_servers.rag.sap_docs_tool import (
    search_sap_documentation,
    get_troubleshooting_steps
)


def handle_incident_report(
    user_report: str,
    priority: str = "3",
    reporter_name: str = "User",
    auto_create_ticket: bool = True,
    auto_notify_teams: bool = True
) -> Dict[str, Any]:
    """Main orchestration function for handling incident reports."""
    
    workflow_start = datetime.now()
    results = {"steps": []}
    
    print("\n" + "=" * 70)
    print("🚀 SAP INCIDENT MANAGER - MCP WORKFLOW")
    print("=" * 70)
    print(f"Report: {user_report}")
    print(f"Priority: P{priority}")
    print(f"Reporter: {reporter_name}")
    print("-" * 70)
    
    # STEP 1: Search SAP Documentation
    print("\n📚 STEP 1: Searching SAP documentation...")
    rag_result = get_troubleshooting_steps(user_report)
    troubleshooting = None
    
    if rag_result["status"] == "success":
        troubleshooting = rag_result.get("response", "")
        print(f"   ✅ Found documentation ({rag_result['mode']})")
        print(f"   Preview: {troubleshooting[:100]}...")
    else:
        print(f"   ⚠️ No documentation found")
    
    results["steps"].append({"step": 1, "action": "rag_search", "status": rag_result["status"]})
    
    # STEP 2: Find Related Incidents
    print("\n🔍 STEP 2: Finding related incidents...")
    related_result = get_related_incidents(user_report)
    related_numbers = []
    
    if related_result["status"] == "success" and related_result.get("count", 0) > 0:
        related_numbers = [inc.get("number") for inc in related_result.get("incidents", [])]
        print(f"   ✅ Found {len(related_numbers)} related ({related_result['mode']})")
        print(f"   Related: {', '.join(related_numbers)}")
    else:
        print(f"   ℹ️ No related incidents found")
    
    results["steps"].append({"step": 2, "action": "search_incidents", "status": related_result["status"]})
    
    # STEP 3: Create ServiceNow Incident
    incident_number = None
    servicenow_url = None
    
    if auto_create_ticket:
        print("\n🎫 STEP 3: Creating ServiceNow incident...")
        
        description = f"Reported by: {reporter_name}\n\nIssue:\n{user_report}\n"
        if troubleshooting:
            description += f"\nSuggested Troubleshooting:\n{troubleshooting}\n"
        if related_numbers:
            description += f"\nRelated Incidents: {', '.join(related_numbers)}\n"
        
        create_result = create_incident(
            short_description=user_report[:160],
            description=description,
            priority=priority
        )
        
        if create_result["status"] == "success":
            incident_data = create_result.get("incident", {})
            incident_number = incident_data.get("number")
            servicenow_url = incident_data.get("url")
            print(f"   ✅ Created: {incident_number} ({create_result['mode']})")
            print(f"   URL: {servicenow_url}")
        else:
            print(f"   ❌ Failed: {create_result.get('message')}")
        
        results["steps"].append({
            "step": 3, "action": "create_incident", 
            "status": create_result["status"], "incident_number": incident_number
        })
    
    # STEP 4: Post to Teams
    if auto_notify_teams:
        print("\n📣 STEP 4: Posting to Microsoft Teams...")
        
        teams_result = post_incident_notification(
            incident_number=incident_number or "PENDING",
            title=user_report[:160],
            priority=priority,
            description=user_report,
            troubleshooting=troubleshooting,
            related_incidents=related_numbers if related_numbers else None,
            servicenow_url=servicenow_url
        )
        
        print(f"   ✅ Posted to #{teams_result.get('channel')} ({teams_result['mode']})")
        results["steps"].append({"step": 4, "action": "teams_notification", "status": teams_result["status"]})
    
    # Summary
    duration = (datetime.now() - workflow_start).total_seconds()
    
    print("\n" + "=" * 70)
    print("✅ WORKFLOW COMPLETE")
    print("=" * 70)
    print(f"Duration: {duration:.2f} seconds")
    print(f"Incident: {incident_number or 'Not created'}")
    if servicenow_url:
        print(f"URL: {servicenow_url}")
    print(f"\n👉 Refresh ServiceNow to see the new incident!")
    print("=" * 70 + "\n")
    
    results["incident_number"] = incident_number
    results["duration"] = duration
    return results


def interactive_mode():
    """Run in interactive mode."""
    print("\n" + "=" * 60)
    print("🤖 SAP INCIDENT MANAGER - INTERACTIVE MODE")
    print("=" * 60)
    print("Commands: report <desc>, quit")
    print("=" * 60 + "\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break
            if user_input.lower().startswith("report "):
                description = user_input[7:].strip()
                priority = input("Priority (1-4) [3]: ").strip() or "3"
                handle_incident_report(user_report=description, priority=priority)
            else:
                handle_incident_report(user_report=user_input)
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="SAP Incident Manager")
    parser.add_argument("--interactive", "-i", action="store_true")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--report", "-r", type=str)
    parser.add_argument("--priority", "-p", type=str, default="3")
    
    args = parser.parse_args()
    
    if args.interactive:
        interactive_mode()
    elif args.demo:
        print("\n🎬 RUNNING DEMO SCENARIO\n")
        handle_incident_report(
            user_report="Joule is not responding in PROD environment. Multiple users affected since 10:30 AM.",
            priority="2",
            reporter_name="Srinivasa Dasari"
        )
    elif args.report:
        handle_incident_report(user_report=args.report, priority=args.priority)
    else:
        parser.print_help()
