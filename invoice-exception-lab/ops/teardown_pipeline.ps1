param([switch]$Apply)
# B6 teardown for the Track B pipeline. Dry run by default; -Apply deletes in dependency order.
$P = "geap-ai-usecases-494501"; $R = "us-central1"; $S = "$P.iam.gserviceaccount.com"
function Exists([scriptblock]$check) { & $check *> $null; return ($LASTEXITCODE -eq 0) }
$items = @(
 @{n="Cloud Build trigger ap-consumer-deploy"; c={gcloud builds triggers describe ap-consumer-deploy --region=$R}; d={gcloud builds triggers delete ap-consumer-deploy --region=$R --quiet}},
 @{n="Pub/Sub subscription invoice-events-push"; c={gcloud pubsub subscriptions describe invoice-events-push}; d={gcloud pubsub subscriptions delete invoice-events-push --quiet}},
 @{n="Pub/Sub subscription invoice-events-dlq-inspect"; c={gcloud pubsub subscriptions describe invoice-events-dlq-inspect}; d={gcloud pubsub subscriptions delete invoice-events-dlq-inspect --quiet}},
 @{n="Pub/Sub topic invoice-events"; c={gcloud pubsub topics describe invoice-events}; d={gcloud pubsub topics delete invoice-events --quiet}},
 @{n="Pub/Sub topic invoice-events-dlq"; c={gcloud pubsub topics describe invoice-events-dlq}; d={gcloud pubsub topics delete invoice-events-dlq --quiet}},
 @{n="Cloud Run service ap-consumer"; c={gcloud run services describe ap-consumer --region=$R}; d={gcloud run services delete ap-consumer --region=$R --quiet}},
 @{n="Artifact Registry repository cloud-run-source-deploy (images and the ap-deployer binding)"; c={gcloud artifacts repositories describe cloud-run-source-deploy --location=$R}; d={gcloud artifacts repositories delete cloud-run-source-deploy --location=$R --quiet}},
 @{n="Bucket run-sources (B1 source uploads)"; c={gcloud storage buckets describe "gs://run-sources-$P-$R"}; d={gcloud storage rm --recursive "gs://run-sources-$P-$R" --quiet}},
 @{n="Cloud SQL instance ap-ledger (LEDGER DATA IS LOST)"; c={gcloud sql instances describe ap-ledger}; d={gcloud sql instances delete ap-ledger --quiet}}
)
foreach ($line in (gcloud beta monitoring policies list --format="value(name,displayName)")) {
  $name, $disp = $line -split "`t"
  if ($disp -like "AP: *") { $items += @{n="Alert policy $disp"; c=[scriptblock]::Create("gcloud beta monitoring policies describe $name"); d=[scriptblock]::Create("gcloud beta monitoring policies delete $name --quiet")} }
}
foreach ($line in (gcloud beta monitoring channels list --format="value(name,displayName)")) {
  $name, $disp = $line -split "`t"
  if ($disp -eq "AP lab alerts") { $items += @{n="Notification channel $disp"; c=[scriptblock]::Create("gcloud beta monitoring channels describe $name"); d=[scriptblock]::Create("gcloud beta monitoring channels delete $name --force --quiet")} }
}
$items += @(
 @{n="Project role cloudsql.client for ap-consumer"; c={gcloud iam service-accounts describe "ap-consumer@$S"}; d={gcloud projects remove-iam-policy-binding $P --member="serviceAccount:ap-consumer@$S" --role=roles/cloudsql.client --condition=None --quiet}},
 @{n="Project role cloudsql.instanceUser for ap-consumer"; c={gcloud iam service-accounts describe "ap-consumer@$S"}; d={gcloud projects remove-iam-policy-binding $P --member="serviceAccount:ap-consumer@$S" --role=roles/cloudsql.instanceUser --condition=None --quiet}},
 @{n="Project role logging.logWriter for ap-deployer"; c={gcloud iam service-accounts describe "ap-deployer@$S"}; d={gcloud projects remove-iam-policy-binding $P --member="serviceAccount:ap-deployer@$S" --role=roles/logging.logWriter --condition=None --quiet}},
 @{n="Service account ap-consumer"; c={gcloud iam service-accounts describe "ap-consumer@$S"}; d={gcloud iam service-accounts delete "ap-consumer@$S" --quiet}},
 @{n="Service account ap-pubsub-invoker"; c={gcloud iam service-accounts describe "ap-pubsub-invoker@$S"}; d={gcloud iam service-accounts delete "ap-pubsub-invoker@$S" --quiet}},
 @{n="Service account ap-deployer"; c={gcloud iam service-accounts describe "ap-deployer@$S"}; d={gcloud iam service-accounts delete "ap-deployer@$S" --quiet}},
 @{n="Cloud Build repository link gcp-vertex-ai"; c={gcloud builds repositories describe gcp-vertex-ai --connection=github-srini118us --region=$R}; d={gcloud builds repositories delete gcp-vertex-ai --connection=github-srini118us --region=$R --quiet}},
 @{n="Cloud Build connection github-srini118us"; c={gcloud builds connections describe github-srini118us --region=$R}; d={gcloud builds connections delete github-srini118us --region=$R --quiet}}
)
$mode = if ($Apply) { "APPLY" } else { "DRY RUN" }
Write-Host "B6 teardown, $mode, $($items.Count) items"
foreach ($i in $items) {
  if (Exists $i.c) { if ($Apply) { Write-Host "DELETE  $($i.n)"; & $i.d } else { Write-Host "EXISTS  $($i.n)" } }
  else { Write-Host "absent  $($i.n)" }
}
Write-Host "Secrets that may hold the GitHub token (delete after the connection):"
gcloud secrets list --format="value(name)" | Where-Object { $_ -match "github" }
Write-Host "Manual: uninstall the Cloud Build GitHub App in GitHub settings. Kept on purpose: budgets, the invoice-lab bucket, other labs."
