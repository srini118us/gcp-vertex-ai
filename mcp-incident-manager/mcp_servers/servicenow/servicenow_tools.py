"""
MCP_SERVERS/SERVICENOW/SERVICENOW_TOOLS.PY
ServiceNow MCP Tools for Incident Management
"""

import json
import requests
from typing import Dict, Any, List
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from config.settings import servicenow_config, mock_config

MOCK_INCIDENTS = [
    {
        "number": "INC0011987",
        "short_description": "Joule authentication failure - PROD",
        "description": "Users unable to authenticate to Joule.",
        "priority": "2",
        "state": "2",
        "sys_created_on": "2026-04-05 10:30:00"
    }
]


def create_incident(
    short_description: str,
    description: str,
    priority: str = "3",
    category: str = "SAP",
    subcategory: str = "Integration",
    caller_id: str = "System",
    assignment_group: str = None
) -> Dict[str, Any]:
    """Create a new incident in ServiceNow."""
    
    if assignment_group is None:
        assignment_group = servicenow_config.default_assignment_group
    
    incident_data = {
        "short_description": short_description[:160],
        "description": description,
        "priority": priority,
        "category": category,
        "subcategory": subcategory,
        "caller_id": caller_id,
        "impact": priority,
        "urgency": priority
    }
    
    if mock_config.use_mock_servicenow:
        return {
            "status": "success",
            "mode": "MOCK",
            "incident": {
                "number": "INC0012001",
                "sys_id": "mock_12001",
                "url": f"{servicenow_config.instance_url}/incident.do?sys_id=mock"
            }
        }
    
    try:
        response = requests.post(
            servicenow_config.incident_api,
            auth=(servicenow_config.username, servicenow_config.password),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            json=incident_data,
            timeout=30
        )
        
        if response.status_code in [200, 201]:
            result = response.json().get("result", {})
            return {
                "status": "success",
                "mode": "LIVE",
                "incident": {
                    "number": result.get("number"),
                    "sys_id": result.get("sys_id"),
                    "short_description": result.get("short_description"),
                    "url": f"{servicenow_config.instance_url}/nav_to.do?uri=incident.do?sys_id={result.get('sys_id')}"
                }
            }
        else:
            return {"status": "error", "message": f"HTTP {response.status_code}: {response.text[:200]}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def search_incidents(query: str, limit: int = 5, category: str = "SAP") -> Dict[str, Any]:
    """Search for existing incidents."""
    
    if mock_config.use_mock_servicenow:
        query_lower = query.lower()
        matches = [inc for inc in MOCK_INCIDENTS 
                   if query_lower in inc["short_description"].lower()]
        return {"status": "success", "mode": "MOCK", "count": len(matches), "incidents": matches}
    
    try:
        url = servicenow_config.incident_api
        params = {
            "sysparm_query": f"short_descriptionLIKE{query}^ORdescriptionLIKE{query}",
            "sysparm_limit": limit,
            "sysparm_fields": "number,short_description,priority,state,sys_created_on"
        }
        
        response = requests.get(
            url,
            auth=(servicenow_config.username, servicenow_config.password),
            headers={"Accept": "application/json"},
            params=params,
            timeout=30
        )
        
        if response.status_code == 200:
            incidents = response.json().get("result", [])
            return {"status": "success", "mode": "LIVE", "count": len(incidents), "incidents": incidents}
        else:
            return {"status": "error", "message": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_related_incidents(short_description: str, limit: int = 3) -> Dict[str, Any]:
    """Find incidents similar to a given description."""
    keywords = [w for w in short_description.lower().split() if len(w) > 4][:2]
    query = " ".join(keywords) if keywords else "SAP"
    return search_incidents(query=query, limit=limit)
