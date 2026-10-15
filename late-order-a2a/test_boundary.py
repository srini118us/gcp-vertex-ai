import google.auth
from google.auth import impersonated_credentials
from google.cloud import bigquery

P = "enterprise-agent-labs-1012"
src, _ = google.auth.default()
for sa, ds in [("cx-agent", "cx_data"), ("cx-agent", "logistics_data"),
               ("logistics-agent", "logistics_data"), ("logistics-agent", "cx_data")]:
    creds = impersonated_credentials.Credentials(source_credentials=src,
        target_principal=f"{sa}@{P}.iam.gserviceaccount.com",
        target_scopes=["https://www.googleapis.com/auth/cloud-platform"])
    try:
        n = list(bigquery.Client(project=P, credentials=creds).query(
            f"SELECT COUNT(*) c FROM `{P}.{ds}.INFORMATION_SCHEMA.TABLES`").result())[0].c
        print(f"{sa:16} -> {ds:15} ALLOWED ({n} tables)")
    except Exception as e:
        print(f"{sa:16} -> {ds:15} DENIED: {str(e)[:150]}")