"""
MCP_SERVERS/TEAMS/TEAMS_TOOLS.PY
Microsoft Teams MCP Tools for Notifications
"""

import requests
from typing import Dict, Any, List
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from config.settings import teams_config, mock_config


def post_incident_notification(
    incident_number: str,
    title: str,
    priority: str,
    description: str,
    troubleshooting: str = None,
    related_incidents: List[str] = None,
    servicenow_url: str = None,
    mention_team: bool = True
) -> Dict[str, Any]:
    """Post an incident notification to Microsoft Teams."""
    
    priority_emoji = {"1": "🔴", "2": "🟠", "3": "🔵", "4": "🟢"}.get(priority, "⚪")
    priority_name = {"1": "Critical", "2": "High", "3": "Moderate", "4": "Low"}.get(priority, priority)
    
    if mock_config.use_mock_teams:
        print("\n" + "=" * 60)
        print("📣 TEAMS NOTIFICATION (MOCK)")
        print("=" * 60)
        print(f"Channel: #{teams_config.channel_name}")
        print("-" * 60)
        print(f"{priority_emoji} **New SAP Incident: {incident_number}**")
        print(f"")
        print(f"**Title:** {title}")
        print(f"**Priority:** P{priority} - {priority_name}")
        print(f"**Description:** {description[:200]}...")
        
        if troubleshooting:
            print(f"")
            print(f"💡 **Suggested Troubleshooting:**")
            print(f"{troubleshooting[:300]}...")
        
        if related_incidents:
            print(f"")
            print(f"🔗 **Related:** {', '.join(related_incidents)}")
        
        if servicenow_url:
            print(f"")
            print(f"🔗 **ServiceNow:** {servicenow_url}")
        
        print("=" * 60)
        
        return {
            "status": "success",
            "mode": "MOCK",
            "channel": teams_config.channel_name
        }
    
    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "size": "Large", "weight": "Bolder", 
                     "text": f"{priority_emoji} New SAP Incident: {incident_number}"},
                    {"type": "TextBlock", "text": title, "wrap": True},
                    {"type": "TextBlock", "text": description[:500], "wrap": True}
                ]
            }
        }]
    }
    
    try:
        response = requests.post(teams_config.webhook_url, json=card, timeout=10)
        if response.status_code == 200:
            return {"status": "success", "mode": "LIVE", "channel": teams_config.channel_name}
        else:
            return {"status": "error", "message": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def post_simple_message(message: str, prefix_emoji: str = "ℹ️") -> Dict[str, Any]:
    """Post a simple text message to Teams."""
    
    if mock_config.use_mock_teams:
        print(f"\n📣 TEAMS: {prefix_emoji} {message}\n")
        return {"status": "success", "mode": "MOCK"}
    
    try:
        response = requests.post(
            teams_config.webhook_url,
            json={"text": f"{prefix_emoji} {message}"},
            timeout=10
        )
        return {"status": "success" if response.status_code == 200 else "error", "mode": "LIVE"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
