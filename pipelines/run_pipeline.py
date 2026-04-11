"""
Run Pipeline V3 on Vertex AI
Clean version without emojis
"""

from google.cloud import aiplatform

PROJECT_ID = "genai-2222026"
REGION = "us-central1"
PIPELINE_ROOT = "gs://srini118bucket/pipeline-runs"
SERVICE_ACCOUNT = "vertex-pipeline-sa@genai-2222026.iam.gserviceaccount.com"

def run_pipeline():
    aiplatform.init(
        project=PROJECT_ID,
        location=REGION
    )
    
    job = aiplatform.PipelineJob(
        display_name="my-first-pipeline-v3-run",
        template_path="my_first_pipeline_v3.json",
        pipeline_root=PIPELINE_ROOT,
        parameter_values={
            "num_samples": 100,
            "test_size": 0.2
        }
    )
    
    print("Submitting pipeline V3 to Vertex AI...")
    print("Project: {}".format(PROJECT_ID))
    print("Region: {}".format(REGION))
    print("Pipeline Root: {}".format(PIPELINE_ROOT))
    print("Service Account: {}".format(SERVICE_ACCOUNT))
    
    job.submit(service_account=SERVICE_ACCOUNT)
    
    print("")
    print("Pipeline V3 submitted!")
    print("Job Name: {}".format(job.display_name))
    print("View in Console: https://console.cloud.google.com/vertex-ai/pipelines/runs?project={}".format(PROJECT_ID))


if __name__ == "__main__":
    run_pipeline()
