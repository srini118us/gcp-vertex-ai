GRANT `roles/bigquery.dataViewer` ON SCHEMA `enterprise-agent-labs-1012.cx_data` TO 'serviceAccount:cx-agent@enterprise-agent-labs-1012.iam.gserviceaccount.com';
GRANT `roles/bigquery.dataViewer` ON SCHEMA `enterprise-agent-labs-1012.logistics_data` TO 'serviceAccount:logistics-agent@enterprise-agent-labs-1012.iam.gserviceaccount.com';
GRANT `roles/bigquery.dataEditor` ON TABLE `enterprise-agent-labs-1012.cx_data.credits` TO 'serviceAccount:cx-agent@enterprise-agent-labs-1012.iam.gserviceaccount.com';
GRANT `roles/bigquery.dataEditor` ON TABLE `enterprise-agent-labs-1012.cx_data.credits_eval` TO 'serviceAccount:cx-agent@enterprise-agent-labs-1012.iam.gserviceaccount.com';
