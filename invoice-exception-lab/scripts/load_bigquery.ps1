# Day 1: load the synthetic AP world into BigQuery (dataset invoice_lab, US).
# Run from the lab folder in PowerShell:  .\scripts\load_bigquery.ps1
$P = "geap-ai-usecases-494501"
$DS = "invoice_lab"

bq --project_id=$P mk --dataset --location=US --description "Invoice exception lab, synthetic data" "${P}:${DS}"

$tables = @{
  "vendors"             = "vendor_id:STRING,name:STRING,country:STRING,currency:STRING,bank_name:STRING,bank_account:STRING,status:STRING,payment_terms:STRING"
  "purchase_orders"     = "po_number:STRING,po_line:INTEGER,vendor_id:STRING,currency:STRING,category:STRING,material:STRING,description:STRING,quantity:INTEGER,unit_price:NUMERIC,tax_rate:NUMERIC,requester:STRING"
  "goods_receipts"      = "receipt_id:STRING,receipt_type:STRING,po_number:STRING,po_line:INTEGER,quantity:INTEGER,receipt_date:DATE"
  "invoice_history"     = "invoice_number:STRING,vendor_id:STRING,po_number:STRING,invoice_date:DATE,total:NUMERIC,status:STRING"
  "invoiced_quantities" = "po_number:STRING,po_line:INTEGER,quantity_invoiced:INTEGER"
  "approvals_log"       = "approval_id:STRING,object_id:STRING,approval_type:STRING,approver:STRING,role:STRING,approval_date:DATE,note:STRING"
}
foreach ($t in $tables.Keys) {
  bq --project_id=$P load --replace --source_format=CSV --skip_leading_rows=1 "${DS}.$t" "data\$t.csv" $tables[$t]
}
bq --project_id=$P query --use_legacy_sql=false "SELECT 'vendors' t, COUNT(*) n FROM ${DS}.vendors UNION ALL SELECT 'purchase_orders', COUNT(*) FROM ${DS}.purchase_orders UNION ALL SELECT 'goods_receipts', COUNT(*) FROM ${DS}.goods_receipts UNION ALL SELECT 'invoice_history', COUNT(*) FROM ${DS}.invoice_history UNION ALL SELECT 'invoiced_quantities', COUNT(*) FROM ${DS}.invoiced_quantities UNION ALL SELECT 'approvals_log', COUNT(*) FROM ${DS}.approvals_log"
