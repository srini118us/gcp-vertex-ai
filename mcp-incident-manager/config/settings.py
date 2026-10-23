"""
CONFIG/SETTINGS.PY - Lab 09: MCP SAP Incident Manager

Secrets and instance details come from environment variables (or a local .env file that git
ignores), never from code. Copy .env.example to .env and fill it in. In a deployed service these
values come from Secret Manager.
"""

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# GCP Configuration
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.0-flash")
RAG_AGENT_ID = os.getenv("RAG_AGENT_ID", "")


def _flag(name, default):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


@dataclass
class ServiceNowConfig:
    instance_url: str = field(default_factory=lambda: os.getenv("SERVICENOW_INSTANCE_URL", ""))
    username: str = field(default_factory=lambda: os.getenv("SERVICENOW_USERNAME", ""))
    password: str = field(default_factory=lambda: os.getenv("SERVICENOW_PASSWORD", ""), repr=False)
    default_assignment_group: str = "SAP Basis Team"
    default_category: str = "SAP"
    default_subcategory: str = "Integration"

    @property
    def incident_api(self) -> str:
        return f"{self.instance_url}/api/now/table/incident"


@dataclass
class TeamsConfig:
    webhook_url: str = field(default_factory=lambda: os.getenv("TEAMS_WEBHOOK_URL", "https://mock-webhook.example.com"))
    channel_name: str = "sap-incidents"
    team_name: str = "SAP Operations"


@dataclass
class MockConfig:
    use_mock_servicenow: bool = field(default_factory=lambda: _flag("USE_MOCK_SERVICENOW", True))
    use_mock_teams: bool = field(default_factory=lambda: _flag("USE_MOCK_TEAMS", True))


servicenow_config = ServiceNowConfig()
teams_config = TeamsConfig()
mock_config = MockConfig()

if not mock_config.use_mock_servicenow and not all(
        (servicenow_config.instance_url, servicenow_config.username, servicenow_config.password)):
    raise RuntimeError("Live ServiceNow mode needs SERVICENOW_INSTANCE_URL, SERVICENOW_USERNAME and "
                       "SERVICENOW_PASSWORD; set them in .env or set USE_MOCK_SERVICENOW=true")
