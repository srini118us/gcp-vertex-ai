# Remove everything this lab creates in Google Cloud. Run at the end of the lab.
$P = "geap-ai-usecases-494501"
if (Test-Path config\processor.json) { python scripts\delete_processor.py }
bq --project_id=$P rm -r -f -d "${P}:invoice_lab"
