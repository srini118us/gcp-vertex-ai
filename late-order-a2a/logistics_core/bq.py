import os
import google.auth
from google.auth import impersonated_credentials
from google.cloud import bigquery

P = "enterprise-agent-labs-1012"
DS = f"{P}.logistics_data"

def logistics_client() -> bigquery.Client:
    """BigQuery client under the logistics identity. Local: impersonate LOGISTICS_SA; Cloud Run: runtime identity."""
    src, _ = google.auth.default()
    sa = os.getenv("LOGISTICS_SA")
    creds = impersonated_credentials.Credentials(source_credentials=src, target_principal=sa,
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"]) if sa else src
    return bigquery.Client(project=P, credentials=creds)
