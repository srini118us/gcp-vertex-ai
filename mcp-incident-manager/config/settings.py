"""
CONFIG/SETTINGS.PY - Lab 09: MCP SAP Incident Manager
"""

import os
from dataclasses import dataclass

# GCP Configuration
GCP_PROJECT_ID = "genai-2222026"
GCP_LOCATION = "us-central1"
MODEL_NAME = "gemini-2.0-flash"
RAG_AGENT_ID = "2708361571758768128"

@dataclass
class ServiceNowConfig:
    instance_url: str = "https://dev374796.service-now.com"
    username: str = "admin"
    password: str = "Dh=Y0yy1sEC!"
    default_assignment_group: str = "SAP Basis Team"
    default_category: str = "SAP"
    default_subcategory: str = "Integration"
    
    @property
    def incident_api(self) -> str:
        return f"{self.instance_url}/api/now/table/incident"

@dataclass
class TeamsConfig:
    webhook_url: str = "https://mock-webhook.example.com"
    channel_name: str = "sap-incidents"
    team_name: str = "SAP Operations"

@dataclass
class MockConfig:
    use_mock_servicenow: bool = False  # LIVE MODE!
    use_mock_teams: bool = True

servicenow_config = ServiceNowConfig()
teams_config = TeamsConfig()
mock_config = MockConfig()
