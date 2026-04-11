"""
Microsoft Teams Integration Tools - MOCK MODE
Lab 09: MCP SAP Incident Manager
"""

from datetime import datetime
from typing import Dict, Any


def post_incident_notification(
    incident_number: str,
    short_description: str = None,
    priority: str = None,
    assigned_group: str = None,
    servicenow_url: str = None,
    rag_summary: str = None,
    related_incidents: list = None,
    title: str = None,
    description: str = None,
    **kwargs
) -> Dict[str, Any]:
    """Post incident notification to Microsoft Teams (MOCK)."""
    
    issue_text = title or short_description or description or "No description"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    priority_emoji = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🟢"}
    emoji = priority_emoji.get(priority, "⚪") if priority else "⚪"
    
    print("")
    print("=" * 60)
    print(f"📣 TEAMS NOTIFICATION (MOCK) - #{incident_number}")
    print("=" * 60)
    print(f"  {emoji} Priority: {priority or 'Not set'}")
    print(f"  📋 Issue: {issue_text}")
    print(f"  👥 Assigned: {assigned_group or 'Unassigned'}")
    print(f"  🔗 Link: {servicenow_url or 'N/A'}")
    print(f"  ⏰ Time: {timestamp}")
    print("=" * 60)
    print("  ✅ Posted to #sap-incidents channel")
    print("=" * 60)
    print("")
    
    return {
        "success": True,
        "mock": True,
        "mode": "MOCK",
        "status": "success",
        "channel": "#sap-incidents",
        "incident_number": incident_number,
        "timestamp": timestamp,
        "message": f"Notification posted for {incident_number}"
    }


def post_simple_message(message: str, channel: str = "#sap-incidents") -> Dict[str, Any]:
    """Post a simple text message to Teams (MOCK)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    print("")
    print("=" * 50)
    print(f"📣 TEAMS MESSAGE (MOCK) - {channel}")
    print("=" * 50)
    print(f"  {message}")
    print(f"  ⏰ {timestamp}")
    print("=" * 50)
    print("")
    
    return {
        "success": True,
        "mock": True,
        "mode": "MOCK",
        "status": "success",
        "channel": channel,
        "timestamp": timestamp
    }


def get_teams_status() -> Dict[str, Any]:
    """Check Teams integration status."""
    return {
        "connected": True,
        "mode": "MOCK",
        "status": "success",
        "channel": "#sap-incidents",
        "reason": "Personal Teams accounts don't support webhooks"
    }