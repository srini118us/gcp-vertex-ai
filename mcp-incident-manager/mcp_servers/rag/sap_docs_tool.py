"""
MCP_SERVERS/RAG/SAP_DOCS_TOOL.PY
RAG Integration Tool - Searches SAP Documentation
"""

from typing import Dict, Any
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from config.settings import GCP_PROJECT_ID, GCP_LOCATION, RAG_AGENT_ID

MOCK_RAG_RESPONSES = {
    "joule": """Based on SAP documentation (Joule_Onboarding.pdf):

**Troubleshooting Joule Issues:**
1. Check IAS (Identity Authentication Service) trust configuration
2. Verify BTP destination is active and correctly configured
3. Check Joule service status in BTP cockpit
4. Ensure user has correct authorizations in SAP system
5. Verify network connectivity between BTP and backend system

**Common Causes:**
- Expired certificates in IAS trust
- Misconfigured destinations
- Missing role assignments""",
    
    "authentication": """Based on SAP documentation (Identity_Authentication_en.pdf):

**Authentication Troubleshooting:**
1. Verify IAS tenant URL is correct
2. Check SAML/OIDC configuration
3. Validate certificate trust chain
4. Review authentication logs in IAS admin console
5. Ensure user exists in IAS with correct attributes""",
    
    "bdc": """Based on SAP documentation (SAP_BDC_Admin.pdf):

**BDC Integration Troubleshooting:**
1. Verify data source connections
2. Check synchronization schedules
3. Review transformation mappings
4. Validate target system availability""",
    
    "default": """Based on SAP documentation:

General troubleshooting steps:
1. Check system logs for errors
2. Verify user authorizations
3. Confirm network connectivity
4. Review recent configuration changes
5. Contact SAP Basis team if issue persists"""
}


def search_sap_documentation(query: str) -> Dict[str, Any]:
    """Search SAP documentation using mock responses."""
    
    query_lower = query.lower()
    
    for keyword, response in MOCK_RAG_RESPONSES.items():
        if keyword != "default" and keyword in query_lower:
            return {
                "status": "success",
                "mode": "MOCK_RAG",
                "query": query,
                "response": response,
                "source": "SAP Documentation Data Store"
            }
    
    return {
        "status": "success",
        "mode": "MOCK_RAG",
        "query": query,
        "response": MOCK_RAG_RESPONSES["default"],
        "source": "SAP Documentation Data Store"
    }


def get_troubleshooting_steps(issue_description: str) -> Dict[str, Any]:
    """Get troubleshooting steps for an SAP issue."""
    query = f"troubleshooting steps for: {issue_description}"
    result = search_sap_documentation(query)
    result["context"] = "troubleshooting"
    return result
